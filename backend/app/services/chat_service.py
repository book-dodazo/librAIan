# -*- coding: utf-8 -*-
# ============================================================
# app/services/chat_service.py
#
# 변경 이력:
#   v0.1 - 최초 작성 (단순 의도 분류)
#   v0.2 - [FIX] LLMCallError 전파 방식 수정
#   v0.3 - 전면 재작성: slot 기반 파이프라인으로 변경
#   v0.4 - inferred 확인 턴 추가
#   v0.5 - 파이프라인 단계 분리 (pipeline.py)
#   v0.6 - mood: SlotValue → MoodSlot 타입 변경 대응
#          comparison_basis: 확인 카드 표시, inferred 처리, reset 추가
#   v0.7 - 온보딩 데이터 로드 추가
#          _restore_or_create_context에서 user_metadata.json 로드
#          SessionContext.onboarding에 저장
#   v0.8 - 개인화 체크인 턴 추가
#          _needs_personalization_turn(): 대분류 요청 + 프로파일 있을 때 mood 질문 발동
#          generate_personalization_question(): mood 체크인용 경량 질문 생성
#        - profile 기반 RAG override 추가
#          _profile_covers_request(): topic/mood/anchor null + recent_liked_books 2권 이상
#          → rag_ready_from_llm=True override (LLM 판단 우선순위 낮춤)
#        - SessionLogger 통합: 세션별 추론 흐름 로깅 (session_logger.py)
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
import json
import logging
import os
from typing import Optional

from app.core.exceptions import LLMCallError
from app.core.session_logger import SessionLogger
from app.modules.slot.filler import extract_slots, get_slots_to_ask
from app.modules.slot.question_generator import (
    SessionQuestion,
    apply_choice,
    generate_personalization_question,
    generate_question,
)
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

        # 다음 질문에 버튼 표시 여부:
        #   첫 질문이거나 버튼 클릭으로 답한 턴 → 버튼 O
        #   자유 발화로 답한 턴 → 버튼 X (같은 버튼이 반복되는 것 방지)
        show_choices_next = bool(request.selected_choice) or not context.asked_slots

        # ── 세션 로거 초기화 ──────────────────────────────────
        user_id    = (request.user_profile or {}).get("user_id")
        session_id = getattr(context, "session_id", None) or str(context.turn_count)
        sl = SessionLogger(
            session_id    = session_id,
            user_id       = user_id,
            original_query= context.original_query,
        )
        slots_before = context.slots.model_copy(deep=True) if hasattr(context.slots, "model_copy") else context.slots

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
            sl.update_turn(
                user_choice = request.selected_choice,
                slots_asked = request.pending_slots,
            )
            logger.info("선택지 응답 반영: %s", request.selected_choice)

            # 개인화 체크인 답변(mood 선택) → RAG 준비 완료로 표시
            # fallback이 purpose/reading_level 재질문하는 것을 방지
            if "mood" in request.pending_slots:
                context.rag_ready_from_llm = True

        else:
            # ── 자유 발화 → slot 추출 ──────────────────────────
            # signal 결과 접근을 위해 detect() 별도 호출
            from app.modules.signal.detector import detect as signal_detect
            signal_result = signal_detect(request.query)

            sl.start_turn(
                turn          = context.turn_count + 1,
                query         = request.query,
                signal_result = signal_result,
                slots_before  = slots_before,
            )

            try:
                context = await extract_slots(
                    query   = request.query,
                    context = context,
                    history = history,
                )
            except LLMCallError as e:
                logger.error("slot 추출 실패: %s", e)
                sl.finalize(slots=context.slots, completed=False)
                return self._error_response(context, str(e))

            sl.update_turn(slots_after=context.slots)

        # ── Refinement: 이전 추천 결과 있고 수정 요청이면 슬롯 질문 스킵 → 바로 RAG ──
        if context.modification_request and context.previous_result:
            logger.info("refinement 감지 (%s) — 이전 ISBN %d개 제외 후 RAG 재실행",
                        context.modification_request, len(context.previous_result))
            return await self._build_rag_response(context, sl)

        # ── 개인화 체크인 턴 (Rule-based — LLM 게이트 앞에서 실행) ─────
        # 대분류 요청 + 관련 프로파일 있고 mood 없을 때 → LLM 판단 무관하게 먼저 물어봄
        # (LLM이 rag_ready=false를 반환해도 fallback이 개인화 질문을 막는 것 방지)
        if _needs_personalization_turn(context):
            question = generate_personalization_question()
            context.personalization_turn_done = True
            context.asked_slots.append("mood")
            sl.update_turn(slots_asked=["mood"])
            sl._flush_turn()
            return self._build_question_response(context, question, ["mood"], show_choices=True)

        # ── Profile 기반 RAG override (Rule-based) ────────────────────
        # Clarification LLM은 슬롯만 판단하므로, 슬롯이 없어도 프로파일로
        # 방향이 명확한 경우 rule로 override.
        # 조건: topic/mood/anchor 모두 null + recent_liked_books 2권 이상
        if _profile_covers_request(context):
            context.rag_ready_from_llm = True
            logger.info("profile 기반 RAG override: recent_liked_books 패턴으로 방향 결정")

        # ── 메인 게이트: LLM 충분도 판단 ─────────────────────────
        # slots_to_ask 있음              → 질문 emit 후 중단
        # slots_to_ask=[] + rag_ready=false → 질문 소진, RAG 강행
        # slots_to_ask=[] + rag_ready=true  → 후처리 → RAG
        slots_to_ask = get_slots_to_ask(context)

        if slots_to_ask:
            question = await generate_question(
                slots_to_ask = slots_to_ask,
                context      = context,
            )
            context.asked_slots.extend(slots_to_ask)
            sl.update_turn(slots_asked=slots_to_ask)
            sl._flush_turn()
            return self._build_question_response(context, question, slots_to_ask, show_choices=show_choices_next)

        if not context.rag_ready_from_llm:
            # slots_to_ask=[] 이고 rag_ready=false → 질문 소진, RAG 강행
            logger.info("질문 소진 (rag_ready=false, slots_to_ask=[]) — RAG 강행")
            return await self._build_rag_response(context, sl)

        # ── rag_ready=true AND slots_to_ask=[] 이후 처리 ──────
        # inferred 확인 턴 (LOW uncertainty만 — HIGH는 LLM이 rag_ready 판단 시 반영했어야 함)
        inferred = _get_inferred_slots(context)
        if inferred:
            inferred = [
                (s, v) for s, v in inferred
                if context.slot_uncertainty.get(s, "high") != "high"
            ]
            if inferred:
                logger.info("inferred slot 확인 턴: %s", inferred)
                sl.update_turn(slots_asked=["inferred_confirmation"])
                sl._flush_turn()
                return self._build_confirmation_response(context, inferred)

        # RAG
        return await self._build_rag_response(context, sl)

    def _restore_or_create_context(self, request: ChatRequest) -> SessionContext:
        """
        프론트에서 넘어온 컨텍스트를 복원하거나 새로 생성.
        온보딩 데이터(user_metadata.json)를 로드해서 context.onboarding에 저장.

        데모 버전:
            - 컨텍스트는 stateless (프론트에서 관리)
            - 온보딩은 user_metadata.json에서 user_id로 조회
            - request.user_profile에 {"user_id": "P001-A"} 형태로 전달
        실서비스:
            - Redis 등 세션 저장소 사용 권장
            - 온보딩은 DB에서 user_id로 조회
        """
        if request.context:
            try:
                context = SessionContext(**request.context)
                # 컨텍스트 복원 시에도 onboarding이 없으면 다시 로드
                if context.onboarding is None:
                    context.onboarding = _load_onboarding(request.user_profile)
                return context
            except Exception as e:
                logger.warning("컨텍스트 복원 실패, 신규 생성: %s", e)

        context = SessionContext(original_query=request.query)
        context.onboarding = _load_onboarding(request.user_profile)
        return context

    async def _build_rag_response(
        self,
        context: SessionContext,
        sl     : Optional["SessionLogger"] = None,
    ) -> SlotChatResponse:
        """
        전체 파이프라인 실행 후 검색 결과 카드 반환

        RAG 쿼리 생성 → Anchor rewrite → BM25 검색 → Reranking
        → 대출 가능 여부 조회 → 표지/소개 조회 → 추천 이유 생성
        """
        import time
        from app.services.pipeline import run_full_pipeline
        from app.modules.response.generator import generate_result_cards
        from app.core.session_logger import PipelineLog
        from app.db.database import SessionLocal

        # 온보딩 도서관 코드 추출 (첫 번째 도서관 우선)
        ob_lib_code: Optional[str] = None
        if context.onboarding:
            libs = context.onboarding.get("frequent_libraries") or []
            for lib in libs:
                code = lib.get("code") if isinstance(lib, dict) else None
                if code:
                    ob_lib_code = code
                    break

        start    = time.time()
        pipeline = await run_full_pipeline(context, lib_code=ob_lib_code)
        elapsed  = int((time.time() - start) * 1000)

        context.rag_query = pipeline.rag_query
        final_results     = pipeline.final_results

        # Refinement를 위해 이번 추천 ISBN 목록 저장
        # 다음 턴에 "다른거 추천해줘" 등의 요청이 오면 exclude_isbns로 활용
        if final_results:
            context.previous_result = [
                r.get("isbn", "") for r in final_results if r.get("isbn")
            ]

        # ── 결과 카드 생성 (표지/소개 DB 조회 + 추천 이유 LLM 생성) ──
        result_cards: list[dict] = []
        if final_results:
            db = SessionLocal()
            try:
                result_cards = await generate_result_cards(
                    final_results  = final_results,
                    rag_query      = pipeline.rag_query or {},
                    original_query = context.original_query or "",
                    onboarding     = context.onboarding,
                    db             = db,
                )
            finally:
                db.close()

        filled  = context.slots.get_filled_slots()
        message = (
            f"좋아요! {_describe_slots(context)} 관련 도서 {len(result_cards)}권을 찾았어요."
            if result_cards
            else f"죄송해요, {_describe_slots(context)} 관련 도서를 찾지 못했어요. 조건을 바꿔서 다시 시도해보세요."
        )

        # ── 세션 로그 기록 ────────────────────────────────────
        if sl:
            sl.log_recommendation(
                rag_query    = pipeline.rag_query or {},
                pipeline_log = PipelineLog(
                    bm25_count        = len(pipeline.hybrid_results),
                    reranker_count    = len(pipeline.reranked_results),
                    availability_count= len(pipeline.availability_index),
                    elapsed_ms        = {"rag_query": 0, "bm25": 0, "reranker": 0,
                                         "availability": 0, "total": elapsed},
                ),
                result = result_cards[0] if result_cards else None,
            )
            sl.finalize(slots=context.slots, completed=True,
                        result=result_cards[0] if result_cards else None)

        return SlotChatResponse(
            needs_clarification = False,
            ready_for_rag       = True,
            message             = message,
            rag_query           = pipeline.rag_query,
            search_results      = result_cards if result_cards else None,
            availability_index  = pipeline.availability_index if pipeline.availability_index else None,
            context             = context.model_dump(),
            filled_slots        = filled,
        )

    def _build_question_response(
        self,
        context     : SessionContext,
        question    : Optional[SessionQuestion],
        slots_to_ask: list[str],
        show_choices: bool = True,
    ) -> SlotChatResponse:
        """추가 질문 응답"""
        if not question:
            return self._error_response(context, "질문 생성 실패")

        logger.info(
            "생성된 질문: %s | slots_to_ask=%s | 선택지=%s",
            question.question,
            slots_to_ask,
            [c.get("label") for c in (question.choices or [])],
        )

        return SlotChatResponse(
            needs_clarification    = True,
            ready_for_rag          = False,
            message                = question.question,
            clarification_question = question.question,
            clarification_choices  = question.choices if show_choices else None,
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
            context = _promote_inferred_to_direct(context)
            logger.info("inferred 확인 → direct 격상")

            # 확인 후에도 남은 세션 질문 재확인
            slots_to_ask = get_slots_to_ask(context)
            if slots_to_ask:
                question = await generate_question(
                    slots_to_ask = slots_to_ask,
                    context      = context,
                )
                context.asked_slots.extend(slots_to_ask)
                return self._build_question_response(context, question, slots_to_ask, show_choices=True)

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
            mood_label = slots.mood.raw or ", ".join(c.value for c in slots.mood.categories)
            direct_items.append({"slot": "mood", "value": mood_label, "label": "분위기", "type": "direct"})

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
        type_ko = {"book_title": "책", "author": "작가", "series": "시리즈", "library": "도서관"}
        anchor_items = [
            {
                "slot" : a.type.value,
                "value": a.value,
                "label": f"기준 {type_ko.get(a.type.value, '')}",
                "type" : "anchor",
            }
            for a in context.anchors
        ]

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
        _pv = slots.purpose.value
        parts.append(_pv.value if hasattr(_pv, 'value') else str(_pv))

    if slots.reading_level.is_filled():
        from app.modules.slot.rag_query_builder import _LEVEL_LABEL
        label = _LEVEL_LABEL.get(slots.reading_level.value, "")
        if label:
            parts.append(label)

    for a in context.anchors:
        parts.append(f"{a.value} 관련")

    return " · ".join(parts) if parts else "요청하신 조건"


# 싱글턴
chat_service = ChatService()


# ── 헬퍼 함수 ──────────────────────────────────────────────────

_SLOT_LABELS = {
    "topic"            : "주제",
    "purpose"          : "목적",
    "reading_level"    : "난이도",
    "mood"             : "분위기",
    "comparison_basis" : "비교 기준",
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
        val = slots.purpose.value.value if hasattr(slots.purpose.value, 'value') else str(slots.purpose.value)
        result.append(("purpose", val))
    if slots.reading_level.source == SlotSource.inferred and slots.reading_level.is_filled():
        raw_val = slots.reading_level.value.value if hasattr(slots.reading_level.value, 'value') else str(slots.reading_level.value)
        label = _LEVEL_KO.get(raw_val, raw_val)
        result.append(("reading_level", label))
    if slots.mood.source == SlotSource.inferred and slots.mood.is_filled():
        mood_label = slots.mood.raw or ", ".join(c.value for c in slots.mood.categories)
        result.append(("mood", mood_label))
    if slots.comparison_basis.source == SlotSource.inferred and slots.comparison_basis.is_filled():
        dims_label = ", ".join(d.name for d in slots.comparison_basis.dimensions)
        label = dims_label or slots.comparison_basis.raw or ""
        result.append(("comparison_basis", label))
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
        mood_label = slots.mood.raw or ", ".join(c.value for c in slots.mood.categories)
        direct_lines.append(f"  • 분위기: {mood_label}")
    if slots.comparison_basis.is_filled() and slots.comparison_basis.source.value == "direct":
        dims_label = ", ".join(d.name for d in slots.comparison_basis.dimensions)
        cb_label = dims_label or slots.comparison_basis.raw or ""
        direct_lines.append(f"  • 비교 기준: {cb_label}")
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
    if context.anchors:
        type_ko = {"book_title": "책", "author": "작가", "series": "시리즈", "library": "도서관"}
        for a in context.anchors:
            lines.append(f"  • 기준 {type_ko.get(a.type.value, '')}: {a.value}")

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
    if slots.comparison_basis.source == SlotSource.inferred:
        slots.comparison_basis.source = SlotSource.direct
    context.slots = slots
    return context


def _reset_slots(context: SessionContext, slot_names: list[str]) -> SessionContext:
    from app.modules.slot.schema import MoodSlot, ComparisonBasisSlot, SlotValue, TopicSlot
    slots = context.slots
    for name in slot_names:
        if name == "purpose":
            slots.purpose = SlotValue()
        elif name == "reading_level":
            slots.reading_level = SlotValue()
        elif name == "mood":
            slots.mood = MoodSlot()
        elif name == "comparison_basis":
            slots.comparison_basis = ComparisonBasisSlot()
        elif name == "topic":
            slots.topic = TopicSlot()
    context.slots = slots
    return context


# ── 온보딩 로드 ───────────────────────────────────────────────

# user_metadata.json 경로
# 데모: 프로젝트 루트 기준 상대 경로
# 실서비스: 환경변수 USER_METADATA_PATH 또는 DB 연결로 교체
_USER_METADATA_PATH = os.path.join(
    os.path.dirname(__file__),   # app/services/
    "..", "..", "..",             # 프로젝트 루트
    "user_metadata.json",
)

# 메모리 캐시 — 서버 기동 시 한 번만 로드
_user_metadata_cache: dict[str, dict] = {}


def _profile_covers_request(context: SessionContext) -> bool:
    """
    슬롯 없이도 프로파일만으로 RAG 방향이 충분한지 판단.

    조건 (전부 만족해야 True):
    - topic/mood/anchor 모두 null (슬롯 신호 없음)
    - recent_liked_books 2권 이상 (구체적 독서 패턴 존재)
    - Clarification LLM이 rag_ready=False로 판단한 상태 (override 필요한 경우만)
    """
    if context.rag_ready_from_llm:
        return False
    if context.slots.topic.is_filled():
        return False
    if context.slots.mood.is_filled():
        return False
    if context.anchors:
        return False
    recent = (context.onboarding or {}).get("recent_liked_books") or []
    return len(recent) >= 2


def _needs_personalization_turn(context: SessionContext) -> bool:
    """
    개인화 체크인 턴이 필요한지 판단 (Rule-based — LLM 무관).

    조건 (전부 만족해야 True):
    - 아직 체크인 안 함 (personalization_turn_done=False)
    - 온보딩 프로파일 있음
    - mood 미채움
    - topic이 대분류 수준
    - preferred_categories가 있으면, 현재 topic의 coarse 카테고리와 일치하는 항목 존재
      (profile이 현재 요청과 무관하면 mood 물어봐도 개인화 효과 없음)
    """
    if context.personalization_turn_done:
        return False
    if not context.onboarding:
        return False
    if context.slots.mood.is_filled():
        return False

    from app.modules.slot.filler import STILL_BROAD_FINES
    fine_set   = set(context.slots.topic.fine   or [])
    coarse_set = set(context.slots.topic.coarse or [])

    if not fine_set and not coarse_set:
        return False

    is_broad = (fine_set and fine_set.issubset(STILL_BROAD_FINES)) or (not fine_set and coarse_set)
    if not is_broad:
        return False

    # preferred_categories가 있으면 현재 topic과 관련된 카테고리가 있어야 함
    # (없으면 프로파일이 무관 → 개인화 질문이 의미 없음)
    preferred = (context.onboarding or {}).get("preferred_categories") or []
    if preferred:
        topic_cats = coarse_set | fine_set
        relevant = any(p.get("main") in topic_cats for p in preferred)
        if not relevant:
            return False

    return True


def _load_user_metadata() -> dict[str, dict]:
    """user_metadata.json을 로드해서 user_id 기반 dict로 반환 (캐시)"""
    global _user_metadata_cache
    if _user_metadata_cache:
        return _user_metadata_cache

    path = os.path.abspath(_USER_METADATA_PATH)
    if not os.path.exists(path):
        logger.warning("user_metadata.json 없음: %s", path)
        return {}

    try:
        with open(path, encoding="utf-8") as f:
            records = json.load(f)
        _user_metadata_cache = {r["user_id"]: r for r in records}
        logger.info("user_metadata 로드 완료: %d명", len(_user_metadata_cache))
    except Exception as e:
        logger.error("user_metadata 로드 실패: %s", e)

    return _user_metadata_cache


def _load_onboarding(user_profile: Optional[dict]) -> Optional[dict]:
    """
    user_profile에서 user_id를 읽어 온보딩 데이터를 반환.

    데모 버전: user_metadata.json에서 조회
    실서비스: DB 조회로 교체

    Args:
        user_profile: ChatRequest.user_profile
                      {"user_id": "P001-A"} 형태
                      없으면 None 반환 (온보딩 미사용)

    Returns:
        온보딩 데이터 dict 또는 None
        {
            "preferred_categories": [{"main": "소설", "sub": "한국소설"}, ...],
            "preferred_length": "300p 이내",
            "disliked_keywords": ["dark", "tense"],
            "frequent_libraries": ["마포구립서강도서관"],
            ...
        }
    """
    if not user_profile:
        return None

    user_id = user_profile.get("user_id")
    if not user_id:
        return None

    metadata = _load_user_metadata()
    record   = metadata.get(user_id)

    if not record:
        logger.warning("user_id 없음: %s", user_id)
        return None

    logger.info("온보딩 로드: user_id=%s", user_id)
    return record
