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
        """inferred slot 확인 카드 응답 생성"""
        # 요약 목록 생성
        summary = [
            {"slot": slot, "value": val, "label": _SLOT_LABELS.get(slot, slot)}
            for slot, val in inferred
        ]

        # 수정 가능한 slot 선택지 생성
        fix_choices = [
            {
                "label"        : f"{_SLOT_LABELS.get(s, s)} 바꿀게요",
                "confirm"      : False,
                "pending_slots": [s],
            }
            for s, _ in inferred
        ]

        message = _build_confirmation_message(inferred)

        return SlotChatResponse(
            needs_clarification = True,
            ready_for_rag       = False,
            is_confirmation     = True,
            message             = message,
            inferred_summary    = summary,
            clarification_choices = [
                {"label": "맞아요, 추천해주세요 ✓", "confirm": True,  "pending_slots": []},
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
        result.append(("purpose", str(slots.purpose.value)))
    if slots.reading_level.source == SlotSource.inferred and slots.reading_level.is_filled():
        label = _LEVEL_KO.get(slots.reading_level.value, str(slots.reading_level.value))
        result.append(("reading_level", label))
    if slots.mood.source == SlotSource.inferred and slots.mood.is_filled():
        result.append(("mood", str(slots.mood.value)))
    return result


def _build_confirmation_message(inferred: list[tuple[str, str]]) -> str:
    lines = ["이렇게 파악했어요:"]
    for slot, val in inferred:
        label = _SLOT_LABELS.get(slot, slot)
        lines.append(f"  \u2022 {label}: {val}")
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
