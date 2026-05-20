# -*- coding: utf-8 -*-
# ============================================================
# app/modules/slot/filler.py
#
# 변경 이력:
#   v0.1 - 최초 작성
#          slot 추출 (LLM), 우선순위 결정, 멀티턴 누적 업데이트
#   v0.2 - mood: SlotValue(자유형) → MoodSlot(MoodCategory Enum) 타입 변경
#          comparison_basis: ComparisonBasisSlot 파싱 추가
#          is_ready_for_rag: anchor + 유사도 질의 시 comparison_basis 미결이면
#          RAG 직전에 세션 질문 발동하도록 수정
#   v0.3 - signal 모듈 통합
#          extract_slots: LLM 호출 전에 휴리스틱 신호 감지 실행
#          SignalResult를 LLM 프롬프트에 importance 힌트로 전달
# ============================================================
"""
Slot Filler: slot 추출 및 우선순위 결정

역할:
    1. LLM 호출로 사용자 발화에서 slot을 추출해 SessionContext에 반영
    2. 현재 채워진 slot 패턴을 분석해 다음에 물어볼 slot 우선순위 결정
    3. 멀티턴에서 slot을 누적 업데이트 (이미 채워진 slot은 보존)

처리 흐름:
    쿼리
    → signal.detect() — 휴리스틱 신호 감지 + importance/uncertainty 계산
    → LLM 호출 — signal 결과를 힌트로 넘겨 슬롯 값 추출
    → _apply_extraction() — LLM 결과를 SessionContext에 반영

슬롯 채움 정책:
    - direct로 채워진 slot은 덮어쓰지 않음 (_is_locked)
    - inferred/ambiguous는 더 나은 정보로 업데이트 가능
    - mood는 한 번 채워지면 같은 세션에서 업데이트하지 않음
    - comparison_basis는 LLM 추출 또는 세션 질문 버튼으로 채울 수 있음

우선순위 결정 원칙:
    - 추천 실패를 가장 크게 줄이는 slot을 먼저 질문
    - 채워진 slot 패턴으로 매 턴 재평가 (_PRIORITY_CONDITIONS)
    - 연관성 높은 slot끼리 묶어서 한 질문으로 처리 (_group_slots)
"""
import logging
import re
from typing import Optional

from app.core.exceptions import IntentParseError, LLMCallError
from app.modules.llm.category_mapper import get_canonical_fine, get_coarse_category
from app.modules.llm.clova_client import chat_complete_json
from app.modules.signal.detector import SignalResult, detect
from app.prompts.extraction import (
    SLOT_EXTRACTION_SYSTEM_PROMPT,
    build_slot_extraction_messages,
)
from app.prompts.clarification import (
    SUFFICIENCY_JUDGMENT_PROMPT,
    build_sufficiency_messages,
)
from app.modules.slot.schema import (
    Anchor,
    AnchorType,
    AvoidMoodSlot,
    ComparisonBasisSlot,
    ComparisonDimension,
    Constraint,
    ConstraintOperator,
    LengthLevel,
    LengthSlot,
    LocationSlot,
    MoodCategory,
    MoodSlot,
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

    처리 흐름:
        1. signal.detect() — 휴리스틱으로 쿼리 특성 미리 파악
        2. build_slot_extraction_messages() — signal 결과를 힌트로 포함
        3. LLM 호출 — 슬롯 값 추출
        4. _apply_extraction() — 결과를 SessionContext에 반영

    멀티턴에서 현재 slot 상태를 컨텍스트로 넘겨
    이미 채워진 slot을 다시 추출하는 낭비를 줄입니다.

    Args:
        query  : 현재 사용자 발화
        context: 현재 세션 컨텍스트
        history: 이전 대화 목록

    Returns:
        업데이트된 SessionContext
    """
    # 1. 휴리스틱 신호 감지
    signal_result: SignalResult = detect(query)
    logger.info(
        "signal 감지 완료: needs_llm_fallback=%s",
        signal_result.needs_llm_fallback,
    )

    # 첫 턴에만 slot_importance/uncertainty를 설정
    # 멀티턴에서는 첫 턴 값을 유지 (쿼리 맥락이 변하지 않으므로)
    if context.turn_count == 0:
        imp, unc = _signal_to_scores(signal_result)
        context.slot_importance  = imp
        context.slot_uncertainty = unc

    # 2. 현재 slot 상태 + signal 결과를 LLM 컨텍스트로 변환
    current_slots = _slots_to_dict(context.slots)

    messages = build_slot_extraction_messages(
        query         = query,
        history       = history,
        current_slots = current_slots,
        signal_result = signal_result,
    )

    try:
        raw = await chat_complete_json(
            system_prompt = SLOT_EXTRACTION_SYSTEM_PROMPT,
            messages      = messages,
            temperature   = 0.1,
            max_tokens    = 900,
        )
    except (LLMCallError, IntentParseError) as e:
        logger.error("slot 추출 실패: %s", e)
        return context

    # 3. 추출 결과를 컨텍스트에 반영
    context = _apply_extraction(context, raw)

    # 4. holistic sufficiency judgment (매 턴 실행)
    #    슬롯 내용까지 평가해서 RAG 진행 가능 여부 + 다음 질문 + 수정 필요 슬롯 결정
    slots_full = _slots_to_dict_full(context)
    suf_messages = build_sufficiency_messages(
        query       = query,
        slots_state = slots_full,
        turn        = context.turn_count,
    )
    try:
        suf_raw = await chat_complete_json(
            system_prompt = SUFFICIENCY_JUDGMENT_PROMPT,
            messages      = suf_messages,
            temperature   = 0.1,
            max_tokens    = 300,
            model         = "HCX-007",
        )
        context.rag_ready_from_llm  = bool(suf_raw.get("rag_ready", False))
        context.llm_confidence      = int(suf_raw.get("confidence", 100))
        context.llm_slots_to_ask    = list(suf_raw.get("slots_to_ask") or [])
        context.slot_revision_hints = dict(suf_raw.get("slot_revisions") or {})
        context.llm_reasoning       = suf_raw.get("reasoning")

        # confidence < 70 + rag_ready=true → hallucination 가능성, 보수적으로 차단
        _CONFIDENCE_THRESHOLD = 70
        if context.rag_ready_from_llm and context.llm_confidence < _CONFIDENCE_THRESHOLD:
            logger.info(
                "confidence=%d < %d — rag_ready=true override to false",
                context.llm_confidence, _CONFIDENCE_THRESHOLD,
            )
            context.rag_ready_from_llm = False

        # 하위 호환 플래그 파생 (question_generator가 참조하는 경우 대비)
        context.needs_subject_clarification      = "topic_subject"  in context.llm_slots_to_ask
        context.needs_purpose_clarification      = "purpose" in context.llm_slots_to_ask
        context.needs_reading_level_clarification= "reading_level"  in context.llm_slots_to_ask

        logger.info(
            "충분도 판단: rag_ready=%s confidence=%d slots_to_ask=%s revisions=%s | %s",
            context.rag_ready_from_llm,
            context.llm_confidence,
            context.llm_slots_to_ask,
            list(context.slot_revision_hints.keys()),
            context.llm_reasoning,
        )
    except (LLMCallError, IntentParseError) as e:
        logger.warning("충분도 판단 실패 (rule-based fallback): %s", e)
        context.rag_ready_from_llm = False  # 보수적으로: 더 물어보는 쪽

    context.turn_count += 1
    return context


def _apply_extraction(context: SessionContext, raw: dict) -> SessionContext:
    """
    LLM 추출 결과를 SessionContext에 반영합니다.

    기존에 direct로 채워진 slot은 덮어쓰지 않습니다.
    단, is_refinement=True이고 새 값도 direct인 경우 (사용자가 명시적으로 변경 요청)에는 덮어씁니다.
    (멀티턴에서 앞 턴의 정보가 유실되는 것을 방지)
    """
    slots = context.slots
    is_refinement = bool(raw.get("is_refinement"))

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
        # 이미 direct로 채워진 경우 유지 (단, is_refinement=True이고 새 값도 direct이면 덮어씀)
        if not (slots.topic.is_filled() and slots.topic.source == SlotSource.direct) or (is_refinement and source == SlotSource.direct):
            # 중분류: 트리 canonical 값으로 정규화 (매칭 실패 시 원본 유지)
            canonical_fine = [get_canonical_fine(f) or f for f in fine_list]
            # 대분류: canonical fine에서 역방향 매핑
            coarse_list = list(dict.fromkeys(
                filter(None, [get_coarse_category(f) for f in canonical_fine])
            ))
            slots.topic = TopicSlot(
                coarse  = coarse_list,
                fine    = canonical_fine,
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

    if purpose_val and (not _is_locked(slots.purpose) or (is_refinement and purpose_src == SlotSource.direct)):
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

    if level_val and (not _is_locked(slots.reading_level) or (is_refinement and level_src == SlotSource.direct)):
        try:
            slots.reading_level = SlotValue(
                value  = ReadingLevelValue(level_val),
                source = level_src,
            )
            logger.info("reading_level 채움: %s (%s)", level_val, level_src)
        except ValueError:
            logger.warning("알 수 없는 reading_level 값: %s", level_val)

    # ── mood ──────────────────────────────────────────────────
    # MoodSlot: category(MoodCategory Enum) + raw + source
    # LLM 응답 형태:
    #   {"category": "negative_exhausted", "raw": "지쳐서", "source": "direct"}
    #   또는 멀티턴 방어: "negative_exhausted" (str)
    raw_mood = raw.get("mood", {}) or {}
    if isinstance(raw_mood, str):
        raw_mood = {"categories": [raw_mood], "source": "direct"}
    mood_cats_raw = _to_list(raw_mood.get("categories") or raw_mood.get("category"))
    mood_raw_str  = raw_mood.get("raw")
    mood_src      = _parse_source(raw_mood.get("source"))

    if mood_cats_raw and not slots.mood.is_filled():
        parsed_cats = []
        for mc in mood_cats_raw:
            try:
                parsed_cats.append(MoodCategory(mc))
            except ValueError:
                logger.warning("알 수 없는 MoodCategory 값: %s", mc)
        if parsed_cats:
            slots.mood = MoodSlot(
                categories = parsed_cats,
                raw        = mood_raw_str,
                source     = mood_src,
            )
            logger.info("mood 채움: %s / raw=%s (%s)", parsed_cats, mood_raw_str, mood_src)

    # ── comparison_basis ──────────────────────────────────────
    # ComparisonBasisSlot: dimensions(list) + raw + source
    # 카테고리 8 (레퍼런스 신호) 감지 시 활성화
    # LLM 응답 형태:
    #   {"dimensions": ["mood", "difficulty"], "raw": "따뜻하고 쉬운", "source": "direct"}
    #   또는 dimensions 없으면 세션 질문 필요
    raw_cb = raw.get("comparison_basis", {}) or {}
    if isinstance(raw_cb, str):
        raw_cb = {"dimensions": [raw_cb], "source": "direct"}
    cb_dims_raw = raw_cb.get("dimensions", []) or []
    cb_raw_str  = raw_cb.get("raw")
    cb_src      = _parse_source(raw_cb.get("source"))

    if (cb_dims_raw or cb_raw_str) and not slots.comparison_basis.is_filled():
        parsed_dims = []
        for d in _to_list(cb_dims_raw):
            try:
                parsed_dims.append(ComparisonDimension(d))
            except ValueError:
                logger.warning("알 수 없는 ComparisonDimension 값: %s", d)

        slots.comparison_basis = ComparisonBasisSlot(
            dimensions = parsed_dims,
            raw        = cb_raw_str,
            source     = cb_src,
        )
        logger.info(
            "comparison_basis 채움: dims=%s raw=%s (%s)",
            [d.value for d in parsed_dims], cb_raw_str, cb_src,
        )

    # ── avoid_mood ────────────────────────────────────────────
    # LLM 응답 형태:
    #   {"keywords": ["너무 무거운", "너무 잔인한"], "source": "direct"}
    #   또는 멀티턴 방어: ["너무 무거운"] (list)
    raw_avoid = raw.get("avoid_mood", {}) or {}
    if isinstance(raw_avoid, list):
        raw_avoid = {"keywords": raw_avoid, "source": "direct"}
    avoid_keywords = _to_list(raw_avoid.get("keywords"))
    avoid_src      = _parse_source(raw_avoid.get("source"))

    if avoid_keywords and not slots.avoid_mood.is_filled():
        slots.avoid_mood = AvoidMoodSlot(
            keywords = avoid_keywords,
            source   = avoid_src,
        )
        logger.info("avoid_mood 채움: %s (%s)", avoid_keywords, avoid_src)

    # ── location ─────────────────────────────────────────────
    # LLM 응답 형태:
    #   {"region": "서울 마포구", "library": "마포중앙도서관", "source": "direct"}
    #   또는 메모리 방어: "마포중앙도서관" / "서울 마포구"
    raw_location = raw.get("location", {}) or {}
    if isinstance(raw_location, str):
        raw_location = (
            {"library": raw_location, "source": "direct"}
            if "도서관" in raw_location
            else {"region": raw_location, "source": "direct"}
        )
    location_region  = raw_location.get("region")
    location_library = raw_location.get("library")
    location_src     = _parse_source(raw_location.get("source"))

    if (location_region or location_library) and not slots.location.is_filled():
        slots.location = LocationSlot(
            region  = location_region,
            library = location_library,
            source  = location_src,
        )
        logger.info(
            "location 채움: region=%s library=%s (%s)",
            location_region, location_library, location_src,
        )

    # ── length ────────────────────────────────────────────────
    # LLM 응답 형태:
    #   {"level": "short", "source": "direct"}
    #   또는 멀티턴 방어: "short" (str)
    raw_length = raw.get("length", {}) or {}
    if isinstance(raw_length, str):
        raw_length = {"level": raw_length, "source": "direct"}
    length_level_raw = raw_length.get("level")
    length_src       = _parse_source(raw_length.get("source"))

    if length_level_raw and not slots.length.is_filled():
        try:
            slots.length = LengthSlot(
                level  = LengthLevel(length_level_raw),
                source = length_src,
            )
            logger.info("length 채움: %s (%s)", length_level_raw, length_src)
        except ValueError:
            logger.warning("알 수 없는 LengthLevel 값: %s", length_level_raw)

    # ── anchor ────────────────────────────────────────────────
    # [FIX] LLM이 멀티턴에서 str로 반환하는 경우 방어
    raw_anchor = raw.get("anchor", {}) or {}
    if isinstance(raw_anchor, str):
        raw_anchor = {"value": raw_anchor, "type": "book_title"}
    anchor_val  = raw_anchor.get("value")
    anchor_type = raw_anchor.get("type")

    if anchor_val and anchor_type:
        try:
            new_anchor = Anchor(value=anchor_val, type=AnchorType(anchor_type))
            if not any(a.value == anchor_val for a in context.anchors):
                context.anchors.append(new_anchor)
                logger.info("anchor 추가: %s (%s)", anchor_val, anchor_type)
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

    # ── 사후 검증: comparison_basis는 anchor 없이 유효하지 않음 ──
    # LLM이 comparison_basis만 채우고 anchor를 빠뜨린 경우:
    # 1) raw 텍스트에서 책 제목/저자를 역방향 추출 시도
    # 2) 추출 실패 시 comparison_basis 초기화
    if slots.comparison_basis.is_filled() and not context.anchors:
        extracted = _extract_anchor_from_raw(slots.comparison_basis.raw)
        if extracted:
            context.anchors.append(extracted)
            logger.info(
                "comparison_basis.raw에서 anchor 역추출: %s (%s)",
                extracted.value, extracted.type.value,
            )
        else:
            logger.warning(
                "comparison_basis 추출됐으나 anchor 역추출 실패 — comparison_basis 초기화"
            )
            slots.comparison_basis = ComparisonBasisSlot()

    context.slots = slots
    return context


# ── 우선순위 결정 ─────────────────────────────────────────────

# fine이 category_tree에 매핑됐지만 의미상 여전히 대분류 수준인 값들
# Rule [3]에서 topic_subject 강제 질문 트리거로 사용
STILL_BROAD_FINES: frozenset[str] = frozenset({
    # 소설 계열 — 장르/국적 불명확
    "장르소설",          # SF/추리/판타지/로맨스 혼재
    "세계문학전집",      # 포맷 기반, 주제 없음
    "고전소설/문학선",   # 고전 전반
    "그외유럽소설", "기타나라소설",
    # 인문 계열
    "인문학일반", "인문고전총서", "인문교양총서",
    # 역사/문화 계열
    "역사일반", "문화일반",
    # 경제/경영 계열
    "경제일반", "경영일반", "경제이론", "경영이론", "각국경제",
    # 과학 계열
    "교양과학", "과학이론", "과학문고",
    # 자기계발 계열
    "성공/처세", "자기능력계발", "비즈니스능력계발",
    # 건강 계열
    "건강일반", "건강문고",
    # 취미/실용/스포츠 계열
    "취미일반", "스포츠", "체육", "레크레이션/게임", "취미관련상품",
    # 컴퓨터/IT 계열
    "IT일반",
    # 종교 계열
    "종교일반", "그외종교",
    # 어린이 계열
    "어린이교양", "어린이문학",
    # 취업/수험서 계열
    "국가자격증", "전문직자격증", "취업",
    # 시/에세이 계열
    "나라별 에세이", "시/에세이문고", "테마에세이",
    # 유아 계열
    "유아교양",
    # 예술/대중문화 계열
    "예술일반", "예술문고",
    # 기술/공학 계열
    "공학일반",
    # 만화 계열
    "캐릭터상품",
})

# purpose 질문을 생략할 coarse 집합
# 조건: 해당 카테고리에서 독서 목적이 자명하여 purpose 값이 추천을 실질적으로 바꾸지 않는 경우
_SKIP_PURPOSE_COARSE: frozenset[str] = frozenset({
    # 재미/힐링이 전제
    "소설", "시/에세이", "만화",
    # 실용이 전제
    "여행", "요리", "가정/육아", "취미/실용/스포츠",
    # 학습이 전제 (reading_level이 더 유의미한 구분자)
    "외국어", "취업/수험서", "ELT/수험서", "대학교재",
    "초등참고서", "중/고등참고서",
    # 아동/유아 (목적이 카테고리에 내포됨)
    "어린이(초등)", "어린이ELT", "유아(0~7세)", "유아/아동/청소년", "청소년",
    # 목적 구분이 추천 변화를 주지 않는 카테고리
    "잡지",
})


# priority_conditions 정의 (P3 토론 결과 — slot 패턴 기반)
# 형식: (조건 딕셔너리, 우선순위 숫자)
# 숫자가 낮을수록 먼저 질문

_PRIORITY_CONDITIONS: list[tuple[dict, str, int]] = [
    # 아무 신호 없음 → topic 1순위
    # purpose/mood가 트리거 조건에 포함되지만 타겟은 topic만
    ({"topic": "empty", "purpose": "empty", "mood": "empty"}, "topic", 1),

    # purpose만 있고 topic 없음 → topic 1순위
    # purpose 단독으론 검색 불가 → 구조적 조건
    ({"purpose": "filled", "topic": "empty"}, "topic", 1),

    # topic 없음 (일반) → topic 2순위
    ({"topic": "empty"}, "topic", 2),
]


def get_slots_to_ask(context: SessionContext) -> list[str]:
    """
    다음에 질문할 슬롯 목록을 반환합니다.

    LLM holistic judgment 결과(llm_slots_to_ask)를 우선 사용.
    LLM 판단이 없으면 rule-based fallback.

    Returns:
        질문할 slot 이름 목록 (이미 질문한 것 제외)
        빈 리스트 = 추가 질문 불필요, RAG로 전송
    """
    asked = set(context.asked_slots)

    # ── Rule-based 선행 체크: LLM 판단보다 먼저 실행 ──────────

    fine_set = set(context.slots.topic.fine or [])

    # [1] topic이 채워졌지만 coarse 매핑 실패 → 카테고리 방향 미정
    # 단, fine이 구체적인 값(STILL_BROAD_FINES 밖)이면 coarse 없이 시맨틱 RAG 가능 → 통과
    # comparison_basis 또는 anchor가 있으면 raw 자체가 RAG 시맨틱 쿼리로 사용 가능 → 통과
    if (
        context.slots.topic.is_filled()
        and not context.slots.topic.coarse
        and (not fine_set or fine_set.issubset(STILL_BROAD_FINES))
        and not context.slots.comparison_basis.is_filled()
        and not context.anchors
        and "topic_subject" not in asked
    ):
        logger.info("topic.coarse=[] + fine 불명확 — topic_subject 강제 질문 (LLM 판단 무시)")
        return ["topic_subject"]

    # [2] 기술/학습 계열 topic + reading_level 완전 미채움 (null)
    # inferred는 슬롯 추출 LLM이 이미 문맥 판단한 값 → rule이 다시 묻지 않음
    # ("파이썬 기초" → reading_level=easy inferred → 질문 불필요)
    # 소설/에세이/시는 난이도 편차가 작아 제외
    # fine이 STILL_BROAD_FINES에 속하면 topic을 먼저 좁혀야 하므로 Rule [3-A]에 위임
    _SKIP_RL = {"소설", "시/에세이"}
    coarse_set = set(context.slots.topic.coarse or [])
    if (
        coarse_set
        and not coarse_set.issubset(_SKIP_RL)
        and not fine_set.issubset(STILL_BROAD_FINES)
        and not context.slots.reading_level.is_filled()
        and "reading_level" not in asked
    ):
        logger.info("기술/학습 계열 topic + reading_level null — reading_level 강제 질문")
        return ["reading_level"]

    # [3] fine이 매핑됐지만 의미상 여전히 대분류 수준
    # mood/anchor가 있으면 보완 신호로 RAG 가능하므로 통과
    if (
        fine_set
        and fine_set.issubset(STILL_BROAD_FINES)
        and not context.slots.mood.is_filled()
        and not context.anchors
        and "topic_subject" not in asked
    ):
        logger.info("fine ⊆ STILL_BROAD_FINES 감지 — topic_subject 강제 질문 (LLM 판단 무시)")
        return ["topic_subject"]

    # [3-B] fine이 specific하게 매핑됐지만 보완 슬롯이 전부 null
    # purpose null 상태에서 purpose(목적 선택)를 물어야 함
    # 소설/시·에세이 계열은 "재미"가 기본 전제이므로 purpose 질문 생략
    # 비소설 계열은 Rule [2]가 reading_level을 먼저 물으므로 이후에 발동
    if (
        context.slots.topic.is_filled()
        and context.slots.topic.coarse
        and not coarse_set.issubset(_SKIP_PURPOSE_COARSE)
        and not context.slots.mood.is_filled()
        and not context.slots.purpose.is_filled()
        and not context.slots.reading_level.is_filled()
        and not context.anchors
        and "purpose" not in asked
        and "mood" not in asked
    ):
        logger.info("fine specific + 보완 슬롯 전부 null — purpose 질문")
        return ["purpose"]

    # [4] anchor 있음 + comparison_basis가 LLM에 의해 채워졌지만 사용자에게 물어본 적 없음
    # → "어떤 점이 좋으셨나요?" 로 비교 기준 확인/보강
    if (
        context.anchors
        and context.slots.comparison_basis.is_filled()
        and "comparison_basis" not in asked
    ):
        logger.info("anchor + comparison_basis(미확인) 감지 — 비교 기준 확인 질문")
        return ["comparison_basis"]

    # LLM holistic judgment: rag_ready=True면 추가 질문 불필요
    if context.rag_ready_from_llm:
        return []

    # LLM이 명시한 슬롯 목록 우선 사용 (이미 질문한 슬롯 제외)
    if context.llm_slots_to_ask:
        to_ask = [s for s in context.llm_slots_to_ask if s not in asked]
        if to_ask:
            return to_ask

    # LLM 판단 실패 시 rule-based fallback
    return _get_slots_to_ask_fallback(context)


def _get_slots_to_ask_fallback(context: SessionContext) -> list[str]:
    """Rule-based fallback — LLM 충분도 판단 실패 시 사용"""
    slots       = context.slots
    filled      = set(slots.get_filled_slots())
    empty       = set(slots.get_empty_core_slots())
    asked       = set(context.asked_slots)
    importance  = context.slot_importance
    uncertainty = context.slot_uncertainty

    # inferred 슬롯 재검토
    _core_sources = {
        "topic"        : slots.topic.source         if slots.topic.is_filled()         else None,
        "purpose"      : slots.purpose.source       if slots.purpose.is_filled()       else None,
        "reading_level": slots.reading_level.source if slots.reading_level.is_filled() else None,
    }
    for _slot, _src in _core_sources.items():
        if _src == SlotSource.inferred and _slot not in asked:
            if uncertainty.get(_slot, "high") != "low":
                empty.add(_slot)
                filled.discard(_slot)

    if context.needs_subject_clarification and "topic_subject" not in asked:
        empty.add("topic_subject")
    if context.needs_purpose_clarification and "purpose" not in asked:
        empty.add("purpose")
    if (
        context.needs_reading_level_clarification
        and not slots.reading_level.is_filled()
        and "reading_level" not in asked
    ):
        empty.add("reading_level")

    if any(a.type in (AnchorType.book_title, AnchorType.author) for a in context.anchors):
        empty.discard("topic")
    if context.anchors and not slots.comparison_basis.is_filled():
        empty.add("comparison_basis")
    if slots.availability_required and not slots.location.is_filled():
        empty.add("location")

    empty = empty - asked

    if uncertainty:
        empty = {s for s in empty if uncertainty.get(s, "high") != "low"}

    if not empty:
        return []

    slot_priorities: dict[str, int] = {}

    filled_set = set(slots.get_filled_slots())

    def _check_pattern(condition: dict) -> bool:
        for slot_name, state in condition.items():
            if state == "filled" and slot_name not in filled_set:
                return False
            if state == "empty" and slot_name in filled_set:
                return False
        return True

    for condition, target_slot, priority in _PRIORITY_CONDITIONS:
        if _check_pattern(condition) and target_slot in empty:
            slot_priorities[target_slot] = min(slot_priorities.get(target_slot, 999), priority)

    if "comparison_basis" in empty:
        slot_priorities["comparison_basis"] = 1
    if "topic_subject" in empty:
        slot_priorities["topic_subject"] = 1

    for slot_name in empty:
        if slot_name not in slot_priorities:
            slot_priorities[slot_name] = 5

    if importance:
        for slot_name in list(slot_priorities.keys()):
            if importance.get(slot_name) == "high":
                slot_priorities[slot_name] = min(slot_priorities[slot_name], 1)

    sorted_slots = sorted(slot_priorities.items(), key=lambda x: x[1])
    return _group_slots(sorted_slots)


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

    LLM holistic sufficiency judgment 결과만 사용.
    """
    return context.rag_ready_from_llm


# ── 헬퍼 함수 ─────────────────────────────────────────────────

# "드래곤 라자 같은", "기억 전달자처럼", "무라카미 하루키와 비슷한" 패턴에서 앞부분 추출
_ANCHOR_FROM_CB_PATTERN = re.compile(
    r'^(.+?)\s*(?:와|과|이랑|랑)?\s*(?:같은|비슷한|유사한|처럼)',
    re.UNICODE,
)


def _extract_anchor_from_raw(raw: Optional[str]) -> Optional[Anchor]:
    """comparison_basis.raw에서 anchor(책 제목/작가명)를 역방향으로 추출."""
    if not raw:
        return None
    m = _ANCHOR_FROM_CB_PATTERN.match(raw.strip())
    if not m:
        return None
    candidate = m.group(1).strip()
    if len(candidate) < 2:
        return None
    return Anchor(value=candidate, type=AnchorType.book_title)


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


def _is_locked(slot_value) -> bool:
    """
    이미 direct로 채워진 slot은 덮어쓰지 않습니다.
    inferred/ambiguous는 더 나은 정보로 업데이트 가능.

    SlotValue, MoodSlot, ComparisonBasisSlot 모두 지원.
    """
    return slot_value.is_filled() and slot_value.source == SlotSource.direct


def _slots_to_dict(slots) -> dict:
    """SlotState → LLM 컨텍스트용 dict 변환 (채워진 슬롯만)"""
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
        result["mood"] = {
            "categories": [c.value for c in slots.mood.categories],
            "raw"       : slots.mood.raw,
        }
    if slots.comparison_basis.is_filled():
        result["comparison_basis"] = {
            "dimensions": [d.value for d in slots.comparison_basis.dimensions],
            "raw"       : slots.comparison_basis.raw,
        }
    return result


def _slots_to_dict_full(context: SessionContext) -> dict:
    """
    전체 슬롯 상태를 정규화된 dict로 변환 (충분도 판단용).

    편차 감소를 위해:
    - 필드 순서 고정
    - 빈 슬롯도 null로 명시 (LLM이 '없음'을 인식)
    - source 정보 포함 (inferred인지 direct인지 판단에 필요)
    """
    slots  = context.slots
    result = {}

    # topic
    if slots.topic.is_filled():
        result["topic"] = {
            "fine"   : slots.topic.fine,
            "coarse" : slots.topic.coarse,
            "subject": slots.topic.subject or None,
            "source" : slots.topic.source.value,
        }
    else:
        result["topic"] = None

    # purpose
    if slots.purpose.is_filled():
        val = slots.purpose.value
        result["purpose"] = {
            "value" : val.value if hasattr(val, "value") else str(val),
            "source": slots.purpose.source.value,
        }
    else:
        result["purpose"] = None

    # reading_level
    if slots.reading_level.is_filled():
        val = slots.reading_level.value
        result["reading_level"] = {
            "value" : val.value if hasattr(val, "value") else str(val),
            "source": slots.reading_level.source.value,
        }
    else:
        result["reading_level"] = None

    # mood
    if slots.mood.is_filled():
        result["mood"] = {
            "categories": [c.value for c in slots.mood.categories],
            "raw"        : slots.mood.raw,
        }
    else:
        result["mood"] = None

    # anchors
    result["anchors"] = [
        {"value": a.value, "type": a.type.value} for a in context.anchors
    ] or None

    # comparison_basis
    if slots.comparison_basis.is_filled():
        result["comparison_basis"] = {
            "dimensions": [d.value for d in slots.comparison_basis.dimensions],
            "raw"       : slots.comparison_basis.raw,
        }
    else:
        result["comparison_basis"] = None

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


def _signal_to_scores(signal_result: SignalResult) -> tuple[dict[str, str], dict[str, str]]:
    """
    SignalResult → (slot_importance, slot_uncertainty) 변환

    반환:
        importance: {"topic": "high", "purpose": "medium", ...}
            → get_slots_to_ask()에서 우선순위 결정에 사용
        uncertainty: {"topic": "low", "purpose": "high", ...}
            → get_slots_to_ask()에서 세션 질문 여부 결정에 사용
            LOW  = 방향 명확 → 질문 생략
            HIGH = 방향 불명확 → 질문 필요

    needs_llm_fallback=True이면 둘 다 빈 dict 반환
        → get_slots_to_ask()에서 필터링 비활성화
        → 모든 슬롯을 질문 대상으로 유지 (Broad/Ambiguous형)
    """
    if signal_result.needs_llm_fallback:
        return {}, {}

    scores = signal_result.scores

    slot_map = {
        "topic"           : scores.topic,
        "purpose"         : scores.purpose,
        "reading_level"   : scores.difficulty,
        "mood"            : scores.mood,
        "comparison_basis": scores.comparison_basis,
        "location"        : scores.location,
        "avoid_mood"      : scores.avoid_mood,
        "length"          : scores.length,
    }

    importance  = {k: v.importance.value  for k, v in slot_map.items()}
    uncertainty = {k: v.uncertainty.value for k, v in slot_map.items()}

    return importance, uncertainty
