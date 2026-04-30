# -*- coding: utf-8 -*-
# ============================================================
# app/modules/slot/filler.py
#
# 변경 이력:
#   v0.1 - 최초 작성
#          P1~P3 토론 결과 기반 slot 추출 및 우선순위 로직
# ============================================================
"""
Slot Filler: slot 추출 및 우선순위 결정

역할:
    1. LLM 호출로 질의에서 slot 추출
    2. 추출 결과를 SessionContext에 반영
    3. 비어있는 slot 중 우선순위 결정 (priority_conditions)
    4. 멀티턴에서 누적 업데이트

P3 결론 (slot 패턴 기반 우선순위):
    - 추천 실패를 가장 크게 줄이는 slot 먼저
    - 채워진 slot 패턴으로 매 턴 재평가
    - 연관성 높은 slot끼리 묶어서 한 질문으로
"""
import logging
from typing import Optional

from app.core.exceptions import IntentParseError, LLMCallError
from app.modules.llm.category_mapper import get_coarse_category
from app.modules.llm.clova_client import chat_complete_json
from app.modules.slot.prompts import (
    SLOT_EXTRACTION_SYSTEM_PROMPT,
    build_slot_extraction_messages,
)
from app.modules.slot.schema import (
    Anchor,
    AnchorType,
    Constraint,
    ConstraintOperator,
    PurposeValue,
    ReadingLevelValue,
    SessionContext,
    SlotSource,
    SlotValue,
    TopicSlot,
)

logger = logging.getLogger(__name__)


# ── Slot 추출 ─────────────────────────────────────────────────

async def extract_slots(
    query  : str,
    context: SessionContext,
    history: list[dict],
) -> SessionContext:
    """
    LLM으로 질의에서 slot을 추출하고 컨텍스트를 업데이트합니다.

    멀티턴에서 현재 slot 상태를 컨텍스트로 넘겨
    이미 채워진 slot을 다시 추출하는 낭비를 줄입니다.

    Args:
        query  : 현재 사용자 발화
        context: 현재 세션 컨텍스트
        history: 이전 대화 목록

    Returns:
        업데이트된 SessionContext
    """
    # 현재 slot 상태를 LLM 컨텍스트로 변환
    current_slots = _slots_to_dict(context.slots)

    messages = build_slot_extraction_messages(
        query         = query,
        history       = history,
        current_slots = current_slots,
    )

    try:
        raw = await chat_complete_json(
            system_prompt = SLOT_EXTRACTION_SYSTEM_PROMPT,
            messages      = messages,
            temperature   = 0.1,   # 낮게 → 일관성 중요
            max_tokens    = 600,
        )
    except (LLMCallError, IntentParseError) as e:
        logger.error("slot 추출 실패: %s", e)
        # 실패해도 기존 컨텍스트 유지
        return context

    # 추출 결과를 컨텍스트에 반영
    context = _apply_extraction(context, raw)
    context.turn_count += 1
    return context


def _apply_extraction(context: SessionContext, raw: dict) -> SessionContext:
    """
    LLM 추출 결과를 SessionContext에 반영합니다.

    기존에 direct로 채워진 slot은 덮어쓰지 않습니다.
    (멀티턴에서 앞 턴의 정보가 유실되는 것을 방지)
    """
    slots = context.slots

    # ── topic ─────────────────────────────────────────────────
    # [FIX] LLM이 멀티턴에서 str로 반환하는 경우 방어 처리
    # fine/subject 가 단일 str 또는 list 로 올 수 있으므로 항상 리스트로 정규화
    raw_topic = raw.get("topic", {}) or {}
    if isinstance(raw_topic, str):
        raw_topic = {"fine": [raw_topic], "source": "direct"}
    fine_raw    = raw_topic.get("fine")
    subject_raw = raw_topic.get("subject")
    source      = _parse_source(raw_topic.get("source"))

    fine_list   = _to_list(fine_raw)
    subject_list= _to_list(subject_raw)

    if fine_list or subject_list:
        # 이미 direct로 채워진 경우 유지
        if not (slots.topic.is_filled() and slots.topic.source == SlotSource.direct):
            # 각 fine 값에 대해 coarse 매핑 후 중복 제거
            coarse_list = list(dict.fromkeys(
                filter(None, [get_coarse_category(f) for f in fine_list])
            ))
            slots.topic = TopicSlot(
                coarse  = coarse_list,
                fine    = fine_list,
                subject = subject_list,
                source  = source,
            )
            logger.info(
                "topic 채움: coarse=%s fine=%s subject=%s source=%s",
                coarse_list, fine_list, subject_list, source,
            )

    # ── purpose ───────────────────────────────────────────────
    # [FIX] LLM이 멀티턴에서 {"value":..,"source":..} 대신 "실용" 같은 str로 반환하는 경우 방어
    raw_purpose = raw.get("purpose", {}) or {}
    if isinstance(raw_purpose, str):
        raw_purpose = {"value": raw_purpose, "source": "direct"}
    purpose_val = raw_purpose.get("value")
    purpose_src = _parse_source(raw_purpose.get("source"))

    if purpose_val and not _is_locked(slots.purpose):
        try:
            slots.purpose = SlotValue(
                value  = PurposeValue(purpose_val),
                source = purpose_src,
            )
            logger.info("purpose 채움: %s (%s)", purpose_val, purpose_src)
        except ValueError:
            logger.warning("알 수 없는 purpose 값: %s", purpose_val)

    # ── reading_level ─────────────────────────────────────────
    # [FIX] LLM이 멀티턴에서 str로 반환하는 경우 방어
    raw_level = raw.get("reading_level", {}) or {}
    if isinstance(raw_level, str):
        raw_level = {"value": raw_level, "source": "direct"}
    level_val = raw_level.get("value")
    level_src = _parse_source(raw_level.get("source"))

    if level_val and not _is_locked(slots.reading_level):
        try:
            slots.reading_level = SlotValue(
                value  = ReadingLevelValue(level_val),
                source = level_src,
            )
            logger.info("reading_level 채움: %s (%s)", level_val, level_src)
        except ValueError:
            logger.warning("알 수 없는 reading_level 값: %s", level_val)

    # ── mood ──────────────────────────────────────────────────
    # [FIX] LLM이 멀티턴에서 str로 반환하는 경우 방어
    raw_mood = raw.get("mood", {}) or {}
    if isinstance(raw_mood, str):
        raw_mood = {"value": raw_mood, "source": "direct"}
    mood_val = raw_mood.get("value")
    mood_src = _parse_source(raw_mood.get("source"))

    if mood_val and not _is_locked(slots.mood):
        slots.mood = SlotValue(value=mood_val, source=mood_src)
        logger.info("mood 채움: %s (%s)", mood_val, mood_src)

    # ── anchor ────────────────────────────────────────────────
    # [FIX] LLM이 멀티턴에서 str로 반환하는 경우 방어
    raw_anchor = raw.get("anchor", {}) or {}
    if isinstance(raw_anchor, str):
        raw_anchor = {"value": raw_anchor, "type": "book_title"}
    anchor_val  = raw_anchor.get("value")
    anchor_type = raw_anchor.get("type")

    if anchor_val and anchor_type and context.anchor is None:
        try:
            context.anchor = Anchor(
                value = anchor_val,
                type  = AnchorType(anchor_type),
            )
            logger.info("anchor 채움: %s (%s)", anchor_val, anchor_type)
        except ValueError:
            logger.warning("알 수 없는 anchor type: %s", anchor_type)

    # ── constraints ───────────────────────────────────────────
    raw_constraints = raw.get("constraints", []) or []
    for rc in raw_constraints:
        constraint = _parse_constraint(rc)
        if constraint:
            # availability는 플래그로 별도 처리
            if constraint.type == "availability" and constraint.value is True:
                slots.availability_required = True
                logger.info("availability_required = True")
            else:
                # 중복 방지
                if not any(c.raw == constraint.raw for c in slots.constraints):
                    slots.constraints.append(constraint)
                    logger.info("constraint 추가: %s", constraint)

    # ── is_refinement ─────────────────────────────────────────
    if raw.get("is_refinement") and context.modification_request is None:
        context.modification_request = "refinement_requested"

    context.slots = slots
    return context


# ── 우선순위 결정 ─────────────────────────────────────────────

# priority_conditions 정의 (P3 토론 결과 — slot 패턴 기반)
# 형식: (조건 딕셔너리, 우선순위 숫자)
# 숫자가 낮을수록 먼저 질문

_PRIORITY_CONDITIONS: list[tuple[dict, int]] = [
    # topic + purpose 둘 다 채워짐 → reading_level 1순위
    ({"topic": "filled", "purpose": "filled", "reading_level": "empty"}, 1),

    # topic만 채워짐 → purpose 1순위
    ({"topic": "filled", "purpose": "empty"}, 1),

    # mood만 채워짐 → reading_level 1순위 (정서형)
    ({"mood": "filled", "topic": "empty", "reading_level": "empty"}, 1),

    # mood + topic 채워짐 → purpose 2순위
    ({"mood": "filled", "topic": "filled", "purpose": "empty"}, 2),

    # purpose만 채워짐 → topic 1순위
    ({"purpose": "filled", "topic": "empty"}, 1),

    # 아무것도 채워지지 않음 → topic 1순위 (Broad/Ambiguous)
    ({"topic": "empty", "purpose": "empty", "mood": "empty"}, 1),

    # reading_level 기본 우선순위
    ({"reading_level": "empty"}, 3),

    # topic 기본 우선순위
    ({"topic": "empty"}, 2),

    # purpose 기본 우선순위
    ({"purpose": "empty"}, 2),
]


def get_slots_to_ask(context: SessionContext) -> list[str]:
    """
    현재 slot 패턴을 분석해서 질문할 slot 목록을 우선순위 순으로 반환합니다.

    P3 결론:
        - 채워진 slot 패턴으로 우선순위 결정
        - 이미 질문한 slot은 제외
        - anchor가 있으면 특정 slot 불필요

    Returns:
        질문할 slot 이름 목록 (우선순위 순)
        빈 리스트 = 추가 질문 불필요, RAG로 전송
    """
    slots  = context.slots
    filled = set(slots.get_filled_slots())
    empty  = set(slots.get_empty_core_slots())
    asked  = set(context.asked_slots)

    # anchor가 있으면 topic 불필요
    if context.anchor and context.anchor.type in (
        AnchorType.book_title, AnchorType.author
    ):
        empty.discard("topic")

    # 이미 질문한 slot 제외
    empty = empty - asked

    if not empty:
        return []

    # slot 패턴 기반 우선순위 계산
    slot_priorities: dict[str, int] = {}

    def _check_pattern(condition: dict) -> bool:
        """조건 딕셔너리가 현재 패턴과 일치하는지 확인"""
        for slot_name, state in condition.items():
            if state == "filled" and slot_name not in filled:
                return False
            if state == "empty" and slot_name in filled:
                return False
        return True

    for condition, priority in _PRIORITY_CONDITIONS:
        if _check_pattern(condition):
            for slot_name, state in condition.items():
                if state == "empty" and slot_name in empty:
                    # 더 낮은 우선순위(높은 숫자)가 이미 있으면 유지
                    current = slot_priorities.get(slot_name, 999)
                    slot_priorities[slot_name] = min(current, priority)

    # 우선순위 없는 slot은 기본값 5
    for slot_name in empty:
        if slot_name not in slot_priorities:
            slot_priorities[slot_name] = 5

    # 우선순위 순으로 정렬
    sorted_slots = sorted(slot_priorities.items(), key=lambda x: x[1])

    # 동일 우선순위 slot 묶기 (한 질문으로 처리 가능한 것들)
    result = _group_slots(sorted_slots)

    logger.info(
        "질문할 slot 결정: %s (패턴: filled=%s, empty=%s)",
        result, list(filled), list(empty)
    )
    return result


def _group_slots(sorted_slots: list[tuple[str, int]]) -> list[str]:
    """
    동일 우선순위 slot을 묶어서 반환합니다.

    P3 결론: 연관성 높은 slot끼리 묶어서 한 질문으로 동시에 좁힘

    현재는 같은 우선순위 1~2개만 묶고 나머지는 다음 턴으로 넘김.
    한 번에 너무 많은 slot을 묶으면 질문이 복잡해지기 때문.
    """
    if not sorted_slots:
        return []

    # 묶을 수 있는 조합 정의
    _COMBINABLE = {
        ("purpose", "reading_level"),
        ("topic", "purpose"),
    }

    first_priority = sorted_slots[0][1]
    same_priority  = [s for s, p in sorted_slots if p == first_priority]

    # 같은 우선순위가 2개이고 묶을 수 있는 조합이면 묶기
    if len(same_priority) == 2:
        pair = tuple(sorted(same_priority))
        if pair in _COMBINABLE:
            return list(same_priority)  # 2개 동시 질문

    # 그 외에는 1순위만 단독 질문
    return [sorted_slots[0][0]]


def is_ready_for_rag(context: SessionContext) -> bool:
    """
    RAG 검색을 시작할 수 있는지 판단합니다.

    조건:
        - 핵심 slot 중 최소 1개 이상 채워짐
        - anchor가 있으면 바로 RAG 가능
        - 더 이상 물어볼 slot이 없음
    """
    # anchor가 있으면 바로 RAG
    if context.anchor:
        return True

    # 핵심 slot이 하나도 없으면 아직 불가
    if not context.slots.get_filled_slots():
        return False

    # 더 이상 물어볼 slot이 없으면 RAG
    return len(get_slots_to_ask(context)) == 0


# ── 헬퍼 함수 ─────────────────────────────────────────────────

def _parse_source(raw: Optional[str]) -> SlotSource:
    """문자열 → SlotSource 변환 (실패 시 null)"""
    if not raw:
        return SlotSource.null
    try:
        return SlotSource(raw)
    except ValueError:
        return SlotSource.null


def _parse_constraint(rc: dict) -> Optional[Constraint]:
    """raw dict → Constraint 변환"""
    try:
        operator_raw = rc.get("operator")
        operator = ConstraintOperator(operator_raw) if operator_raw else None
        return Constraint(
            type     = rc.get("type", "custom"),
            value    = rc.get("value"),
            operator = operator,
            raw      = rc.get("raw"),
        )
    except (ValueError, Exception) as e:
        logger.warning("constraint 파싱 실패: %s (%s)", rc, e)
        return None


def _is_locked(slot_value: SlotValue) -> bool:
    """
    이미 direct로 채워진 slot은 덮어쓰지 않습니다.
    inferred/ambiguous는 더 나은 정보로 업데이트 가능.
    """
    return slot_value.is_filled() and slot_value.source == SlotSource.direct


def _slots_to_dict(slots) -> dict:
    """SlotState → LLM 컨텍스트용 dict 변환"""
    result = {}
    if slots.topic.is_filled():
        result["topic"] = {
            "coarse": slots.topic.coarse,
            "fine"  : slots.topic.fine,
        }
    if slots.purpose.is_filled():
        result["purpose"] = slots.purpose.value
    if slots.reading_level.is_filled():
        result["reading_level"] = slots.reading_level.value
    if slots.mood.is_filled():
        result["mood"] = slots.mood.value
    return result


def _to_list(val) -> list[str]:
    """
    LLM 응답이 단일 str 또는 list로 올 수 있으므로 항상 list로 정규화합니다.

    예)
        "SF"          → ["SF"]
        ["SF", "추리"] → ["SF", "추리"]
        None           → []
    """
    if val is None:
        return []
    if isinstance(val, list):
        return [str(v) for v in val if v]
    return [str(val)]