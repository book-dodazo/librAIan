# -*- coding: utf-8 -*-
# ============================================================
# app/services/chat_service.py
#
# 변경 이력:
#   v0.1 - 최초 작성 (단순 의도 분류)
#   v0.2 - [FIX] LLMCallError 전파 방식 수정
#   v0.3 - 전면 재작성: slot 기반 파이프라인으로 변경
#          P1~P7 토론 결과 전부 반영
#   v0.4 - inferred 확인 턴 추가
#          inferred slot이 하나라도 있으면 확인 질문 후 RAG 진행
# ============================================================
"""
ChatService: slot 기반 파이프라인 오케스트레이션

파이프라인:
    사용자 질의
      → [1] slot 추출 (LLM)
      → [2] RAG 준비 여부 판단
          → 준비 완료 : RAG 쿼리 생성 → 반환
          → 준비 미완료: session question 생성 → 반환
      → [3] 사용자 답변으로 slot 업데이트 (멀티턴)
      → [4] Refinement 처리

멀티턴 처리:
    컨텍스트 객체를 매 턴 프론트에서 받아서 업데이트 후 반환
    세션 저장소 없이 stateless 로 동작 (데모 버전)
"""
import logging
from typing import Any, Optional

from app.core.exceptions import LLMCallError
from app.modules.slot.filler import extract_slots, get_slots_to_ask, is_ready_for_rag
from app.modules.slot.question_generator import (
    SessionQuestion,
    apply_choice,
    generate_question,
)
from app.modules.slot.rag_query_builder import build_rag_query
from app.modules.slot.schema import SessionContext, SlotSource
from app.schemas.chat_schema import ChatRequest, SlotChatResponse

logger = logging.getLogger(__name__)


class ChatService:

    async def handle(self, request: ChatRequest) -> SlotChatResponse:
        """
        메인 파이프라인 진입점

        매 턴마다:
            1. 컨텍스트 복원 (프론트에서 받음)
            2. 사용자 발화로 slot 업데이트
            3. 선택지 응답이면 apply_choice
            4. inferred 확인 턴 처리
            5. RAG 준비 여부 판단
            6. 응답 반환
        """
        history = [
            {"role": m.role.value, "content": m.content}
            for m in request.history
        ]

        # 컨텍스트 복원 또는 신규 생성
        context = self._restore_or_create_context(request)

        # ── inferred 확인 턴 응답 처리 ────────────────────────
        if request.confirm_inferred is not None:
            return await self._handle_inferred_confirmation(
                request, context
            )

        # ── 선택지 응답 처리 (사용자가 버튼 선택) ─────────────
        if request.selected_choice and request.pending_slots:
            context = apply_choice(
                context    = context,
                choice     = request.selected_choice,
                asked_slots= request.pending_slots,
            )
            logger.info("선택지 응답 반영: %s", request.selected_choice)

        else:
            # ── 자유 발화 → slot 추출 ──────────────────────────
            try:
                context = await extract_slots(
                    query   = request.query,
                    context = context,
                    history = history,
                )
            except LLMCallError as e:
                logger.error("slot 추출 실패: %s", e)
                return self._error_response(context, str(e))

        # ── inferred slot 있으면 확인 턴 ──────────────────────
        inferred = _get_inferred_slots(context)
        if inferred:
            logger.info("inferred slot 발견 → 확인 턴: %s", inferred)
            return self._build_confirmation_response(context, inferred)

        # ── RAG 준비 여부 판단 ────────────────────────────────
        if is_ready_for_rag(context):
            return await self._build_rag_response(context)

        # ── session question 생성 ─────────────────────────────
        slots_to_ask = get_slots_to_ask(context)

        if not slots_to_ask:
            return await self._build_rag_response(context)

        question = await generate_question(
            slots_to_ask = slots_to_ask,
            context      = context,
        )

        return self._build_question_response(context, question, slots_to_ask)

    def _restore_or_create_context(self, request: ChatRequest) -> SessionContext:
        """
        프론트에서 넘어온 컨텍스트를 복원하거나 새로 생성

        데모 버전: stateless (컨텍스트를 프론트에서 관리)
        실서비스: Redis 등 세션 저장소 사용 권장
        """
        if request.context:
            try:
                return SessionContext(**request.context)
            except Exception as e:
                logger.warning("컨텍스트 복원 실패, 신규 생성: %s", e)

        return SessionContext(original_query=request.query)

    async def _build_rag_response(self, context: SessionContext) -> SlotChatResponse:
        """RAG 준비 완료 응답"""
        rag_query = await build_rag_query(context)
        context.rag_query = rag_query

        filled  = context.slots.get_filled_slots()
        message = f"좋아요! {_describe_slots(context)} 관련 도서를 찾아볼게요 📚"

        return SlotChatResponse(
            needs_clarification = False,
            ready_for_rag       = True,
            message             = message,
            rag_query           = rag_query,
            context             = context.model_dump(),
            filled_slots        = filled,
        )

    def _build_question_response(
        self,
        context     : SessionContext,
        question    : Optional[SessionQuestion],
        slots_to_ask: list[str],
    ) -> SlotChatResponse:
        """추가 질문 응답"""
        if not question:
            return self._error_response(context, "질문 생성 실패")

        return SlotChatResponse(
            needs_clarification    = True,
            ready_for_rag          = False,
            message                = question.question,
            clarification_question = question.question,
            clarification_choices  = question.choices,
            pending_slots          = slots_to_ask,
            context                = context.model_dump(),
            filled_slots           = context.slots.get_filled_slots(),
        )

    async def _handle_inferred_confirmation(
        self, request: ChatRequest, context: SessionContext
    ) -> SlotChatResponse:
        """
        inferred 확인 턴 응답 처리

        confirm_inferred=True  → inferred 값 그대로 승인, RAG 진행
        confirm_inferred=False → pending_slots 의 slot 질문으로 이동
        """
        if request.confirm_inferred:
            # 승인 → inferred를 direct로 격상 후 RAG
            context = _promote_inferred_to_direct(context)
            logger.info("inferred 승인 → direct 격상 후 RAG")
            return await self._build_rag_response(context)

        else:
            # 수정 요청 → pending_slots 의 slot 질문 생성
            slots_to_fix = request.pending_slots or []
            if not slots_to_fix:
                # pending_slots 없으면 inferred slot 전부 재질문
                slots_to_fix = [
                    s for s, _ in _get_inferred_slots(context)
                ]

            if not slots_to_fix:
                return await self._build_rag_response(context)

            # 해당 slot을 null로 초기화 후 질문 생성
            context = _reset_slots(context, slots_to_fix)
            question = await generate_question(
                slots_to_ask = slots_to_fix[:1],  # 한 번에 하나씩
                context      = context,
            )
            return self._build_question_response(context, question, slots_to_fix[:1])

    def _build_confirmation_response(
        self,
        context : SessionContext,
        inferred: list[tuple[str, str]],  # [(slot_name, value_label), ...]
    ) -> SlotChatResponse:
        """
        확인 카드 응답 생성

        inferred_summary: inferred slot + direct slot + constraints + anchor 전부 포함
        (데모 버전 — 서비스 레벨에서는 inferred만 표시 권장)
        """
        slots = context.slots

        # inferred slot 요약
        inferred_items = [
            {"slot": slot, "value": val, "label": _SLOT_LABELS.get(slot, slot), "type": "inferred"}
            for slot, val in inferred
        ]

        # direct slot 요약
        direct_items = []
        if slots.topic.is_filled() and slots.topic.source.value == "direct":
            topic_val = ', '.join(slots.topic.fine) if slots.topic.fine else ', '.join(slots.topic.coarse)
            direct_items.append({"slot": "topic", "value": topic_val, "label": "주제", "type": "direct"})
        if slots.purpose.is_filled() and slots.purpose.source.value == "direct":
            val = slots.purpose.value.value if hasattr(slots.purpose.value, 'value') else str(slots.purpose.value)
            direct_items.append({"slot": "purpose", "value": val, "label": "목적", "type": "direct"})
        if slots.reading_level.is_filled() and slots.reading_level.source.value == "direct":
            raw_val = slots.reading_level.value.value if hasattr(slots.reading_level.value, 'value') else str(slots.reading_level.value)
            direct_items.append({"slot": "reading_level", "value": _LEVEL_KO.get(raw_val, raw_val), "label": "난이도", "type": "direct"})
        if slots.mood.is_filled() and slots.mood.source.value == "direct":
            direct_items.append({"slot": "mood", "value": str(slots.mood.value), "label": "분위기", "type": "direct"})

        # constraints 요약
        constraint_items = []
        _OP_KO = {"lte": "이하", "lt": "미만", "gte": "이상", "gt": "초과", "eq": "", "exclude": "제외"}
        for c in slots.constraints:
            if c.type == "page_range":
                op = _OP_KO.get(c.operator.value if c.operator else "", "")
                constraint_items.append({"slot": "page_range", "value": f"{c.value}{op}", "label": "페이지", "type": "constraint"})
            elif c.type == "pub_year":
                op = {"gte": "이후", "lte": "이전"}.get(c.operator.value if c.operator else "", "")
                constraint_items.append({"slot": "pub_year", "value": f"{c.value}{op}", "label": "출판연도", "type": "constraint"})
            elif c.type == "author":
                constraint_items.append({"slot": "author", "value": str(c.value), "label": "포함 작가", "type": "constraint"})
            elif c.type == "nonauthor":
                constraint_items.append({"slot": "nonauthor", "value": str(c.value), "label": "제외 작가", "type": "constraint"})
            elif c.type == "target_reader":
                constraint_items.append({"slot": "target_reader", "value": str(c.value), "label": "독자 대상", "type": "constraint"})
            elif c.type == "availability":
                constraint_items.append({"slot": "availability", "value": "필수", "label": "대출 가능", "type": "constraint"})
            elif c.type == "custom":
                constraint_items.append({"slot": "custom", "value": str(c.raw or c.value), "label": "기타", "type": "constraint"})

        # anchor 요약
        anchor_items = []
        if context.anchor:
            type_ko = {"book_title": "책", "author": "작가", "series": "시리즈", "library": "도서관"}
            anchor_items.append({
                "slot" : context.anchor.type.value,
                "value": context.anchor.value,
                "label": f"기준 {type_ko.get(context.anchor.type.value, '')}",
                "type" : "anchor",
            })

        # 전체 요약 합산
        full_summary = inferred_items + direct_items + constraint_items + anchor_items

        # 수정 가능한 slot 선택지 (inferred만)
        fix_choices = [
            {
                "label"        : f"{_SLOT_LABELS.get(s, s)} 바꿀게요",
                "confirm"      : False,
                "pending_slots": [s],
            }
            for s, _ in inferred
        ]

        message = _build_confirmation_message(inferred, context)

        return SlotChatResponse(
            needs_clarification = True,
            ready_for_rag       = False,
            is_confirmation     = True,
            message             = message,
            inferred_summary    = full_summary,
            clarification_choices = [
                {"label": "맞아요, 추천해주세요 ✓", "confirm": True, "pending_slots": []},
                *fix_choices,
            ],
            pending_slots = [s for s, _ in inferred],
            context       = context.model_dump(),
            filled_slots  = context.slots.get_filled_slots(),
        )

    def _error_response(
        self, context: SessionContext, error: str
    ) -> SlotChatResponse:
        """에러 응답"""
        return SlotChatResponse(
            needs_clarification = False,
            ready_for_rag       = False,
            message             = "죄송해요, 일시적인 오류가 발생했어요. 다시 시도해 주세요.",
            context             = context.model_dump(),
            filled_slots        = [],
            error               = error,
        )


def _describe_slots(context: SessionContext) -> str:
    """채워진 slot을 자연어로 요약"""
    parts = []
    slots = context.slots

    if slots.topic.fine:
        parts.append(', '.join(slots.topic.fine))
    elif slots.topic.coarse:
        parts.append(', '.join(slots.topic.coarse))

    if slots.purpose.is_filled():
        parts.append(str(slots.purpose.value))

    if slots.reading_level.is_filled():
        from app.modules.slot.rag_query_builder import _LEVEL_LABEL
        label = _LEVEL_LABEL.get(slots.reading_level.value, "")
        if label:
            parts.append(label)

    if context.anchor:
        parts.append(f"{context.anchor.value} 관련")

    return " · ".join(parts) if parts else "요청하신 조건"


# 싱글턴
chat_service = ChatService()


# ── 헬퍼 함수 ──────────────────────────────────────────────────

_SLOT_LABELS = {
    "topic"        : "주제",
    "purpose"      : "목적",
    "reading_level": "난이도",
    "mood"         : "분위기",
}

_LEVEL_KO = {
    "easy"  : "가볍고 쉽게",
    "medium": "적당한 깊이로",
    "hard"  : "깊이 있게",
}


def _get_inferred_slots(context: SessionContext) -> list[tuple[str, str]]:
    slots  = context.slots
    result = []
    if slots.purpose.source == SlotSource.inferred and slots.purpose.is_filled():
        # [FIX] PurposeValue.교양 → 교양: Enum이면 .value로 꺼내기
        val = slots.purpose.value.value if hasattr(slots.purpose.value, 'value') else str(slots.purpose.value)
        result.append(("purpose", val))
    if slots.reading_level.source == SlotSource.inferred and slots.reading_level.is_filled():
        # [FIX] ReadingLevelValue.easy → 가볍고 쉽게
        raw_val = slots.reading_level.value.value if hasattr(slots.reading_level.value, 'value') else str(slots.reading_level.value)
        label = _LEVEL_KO.get(raw_val, raw_val)
        result.append(("reading_level", label))
    if slots.mood.source == SlotSource.inferred and slots.mood.is_filled():
        result.append(("mood", str(slots.mood.value)))
    return result


def _build_confirmation_message(
    inferred: list[tuple[str, str]],
    context : "SessionContext",
) -> str:
    """
    확인 메시지 생성 — inferred slot + direct slot + constraints + anchor 전부 표시
    데모 버전: 최대한 다 출력 (서비스 레벨에서는 inferred만 표시 권장)
    """
    lines = ["이렇게 파악했어요:"]

    # inferred slot (확인 필요)
    if inferred:
        lines.append("  [추론된 값 — 확인 필요]")
        for slot, val in inferred:
            label = _SLOT_LABELS.get(slot, slot)
            lines.append(f"  • {label}: {val}")

    # direct slot (명시된 값)
    slots = context.slots
    direct_lines = []
    if slots.topic.is_filled() and slots.topic.source.value == "direct":
        topic_val = ', '.join(slots.topic.fine) if slots.topic.fine else ', '.join(slots.topic.coarse)
        direct_lines.append(f"  • 주제: {topic_val}")
    if slots.purpose.is_filled() and slots.purpose.source.value == "direct":
        val = slots.purpose.value.value if hasattr(slots.purpose.value, 'value') else str(slots.purpose.value)
        direct_lines.append(f"  • 목적: {val}")
    if slots.reading_level.is_filled() and slots.reading_level.source.value == "direct":
        raw_val = slots.reading_level.value.value if hasattr(slots.reading_level.value, 'value') else str(slots.reading_level.value)
        direct_lines.append(f"  • 난이도: {_LEVEL_KO.get(raw_val, raw_val)}")
    if slots.mood.is_filled() and slots.mood.source.value == "direct":
        direct_lines.append(f"  • 분위기: {slots.mood.value}")
    if direct_lines:
        lines.append("  [명시된 값]")
        lines.extend(direct_lines)

    # constraints
    if slots.constraints:
        lines.append("  [제약 조건]")
        for c in slots.constraints:
            if c.type == "page_range":
                op_ko = {"lte": "이하", "lt": "미만", "gte": "이상", "gt": "초과"}.get(
                    c.operator.value if c.operator else "", "")
                lines.append(f"  • 페이지: {c.value}{op_ko}")
            elif c.type == "pub_year":
                op_ko = {"gte": "이후", "lte": "이전"}.get(
                    c.operator.value if c.operator else "", "")
                lines.append(f"  • 출판연도: {c.value}{op_ko}")
            elif c.type == "author":
                lines.append(f"  • 포함 작가: {c.value}")
            elif c.type == "nonauthor":
                lines.append(f"  • 제외 작가: {c.value}")
            elif c.type == "target_reader":
                lines.append(f"  • 독자 대상: {c.value}")
            elif c.type == "availability":
                lines.append(f"  • 대출 가능 필수")
            elif c.type == "custom":
                lines.append(f"  • 기타: {c.raw or c.value}")

    # anchor
    if context.anchor:
        type_ko = {"book_title": "책", "author": "작가", "series": "시리즈", "library": "도서관"}
        lines.append(f"  • 기준 {type_ko.get(context.anchor.type.value, '')}: {context.anchor.value}")

    lines.append("\n바꾸실 내용이 있으면 알려주세요!")
    return "\n".join(lines)


def _promote_inferred_to_direct(context: SessionContext) -> SessionContext:
    slots = context.slots
    if slots.purpose.source == SlotSource.inferred:
        slots.purpose.source = SlotSource.direct
    if slots.reading_level.source == SlotSource.inferred:
        slots.reading_level.source = SlotSource.direct
    if slots.mood.source == SlotSource.inferred:
        slots.mood.source = SlotSource.direct
    context.slots = slots
    return context


def _reset_slots(context: SessionContext, slot_names: list[str]) -> SessionContext:
    from app.modules.slot.schema import SlotValue, TopicSlot
    slots = context.slots
    for name in slot_names:
        if name == "purpose":
            slots.purpose = SlotValue()
        elif name == "reading_level":
            slots.reading_level = SlotValue()
        elif name == "mood":
            slots.mood = SlotValue()
        elif name == "topic":
            slots.topic = TopicSlot()
    context.slots = slots
    return context
