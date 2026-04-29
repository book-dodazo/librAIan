# -*- coding: utf-8 -*-
# ============================================================
# app/services/chat_service.py
#
# 변경 이력:
#   v0.1 - 최초 작성
#   v0.2 - [FIX] LLMCallError 를 라우터까지 전파하도록 re-raise 추가
#           (기존: except 에서 잡아서 일반 응답으로 처리 → 503 반환 안 됨)
#   v0.3 - LLMCallError 폴백 메시지를 ChatResponse 로 감싸서 반환하는 방식으로 변경
#           (프론트가 항상 동일한 응답 구조를 받을 수 있도록)
# ============================================================
"""
ChatService: 파이프라인 오케스트레이션 레이어

역할:
    API 라우터(chat.py) 와 AI 모듈(intent_extractor 등) 을 연결합니다.
    파이프라인 전체 흐름을 여기서 관리합니다.

현재 파이프라인:
    사용자 질의
      → [M1] 의도 추출 (intent_extractor)
      → 추가 질문 필요? → Yes : 질문 반환
                        → No  : RAG 필요? → Yes : search_query 반환
                                           → No  : 일반 응답 반환

나중에 추가할 단계 (TODO):
    → [Retrieval] Dense/BM25 하이브리드 검색
    → [Reranker]  결과 재순위
    → [M4]        도서 설명 생성
"""
import logging
from typing import Any

from app.core.exceptions import LLMCallError
from app.modules.llm.intent_extractor import (
    extract_intent,
    is_rag_required,
    needs_clarification,
)
from app.schemas.chat import ChatRequest, ChatResponse, ExtractedIntent, IntentType

logger = logging.getLogger(__name__)

# ── 응답 메시지 템플릿 ─────────────────────────────────────────

_TEMPLATES = {
    IntentType.book_recommendation: (
        "좋아요! '{query}' 관련 도서를 찾아볼게요. 잠시만 기다려 주세요 📚"
    ),
    IntentType.book_info: "'{query}' 에 대한 정보를 찾아볼게요!",
}

_GENERAL_RESPONSE = (
    "안녕하세요! 저는 도서관 맞춤 도서 추천 도우미입니다. "
    "읽고 싶은 책의 장르나 주제를 알려주시면 딱 맞는 책을 찾아드릴게요 📖"
)

_ERROR_RESPONSE = (
    "죄송해요, 일시적인 오류가 발생했어요. 잠시 후 다시 시도해 주세요."
)


class ChatService:
    """
    채팅 요청 하나를 처리하는 서비스 클래스.

    클래스로 만드는 이유:
        나중에 DB 세션, 캐시 클라이언트 등 의존성이 추가될 때
        __init__ 으로 주입받기 쉬움.
    """

    async def handle(self, request: ChatRequest) -> ChatResponse:
        """
        메인 파이프라인 진입점.

        Args:
            request: ChatRequest (query + history + user_profile)

        Returns:
            ChatResponse — 항상 동일한 구조로 반환 (에러 포함)
        """
        # ConversationMessage 리스트 → dict 리스트 변환 (모듈 레이어에 전달용)
        history_dicts: list[dict[str, Any]] = [
            {"role": msg.role.value, "content": msg.content}
            for msg in request.history
        ]

        # ── Step 1: 의도 추출 (M1) ────────────────────────────
        try:
            intent = await extract_intent(
                query=request.query,
                history=history_dicts,
                user_profile=request.user_profile,
            )
        except LLMCallError as e:
            # [FIX v0.3] LLM 호출 실패 시 구조화된 에러 응답 반환
            logger.error("LLM 호출 실패: %s", e)
            fallback = ExtractedIntent(
                intent_type=IntentType.general_chat,
                confidence=0.0,
            )
            return ChatResponse(
                needs_clarification=False,
                intent=fallback,
                message=_ERROR_RESPONSE,
                ready_for_rag=False,
            )

        logger.info(
            "의도 추출 완료: type=%s confidence=%.2f query='%s'",
            intent.intent_type,
            intent.confidence,
            request.query[:50],
        )

        # ── Step 2: 의도별 분기 ────────────────────────────────
        if needs_clarification(intent):
            return self._build_clarification_response(intent)

        if intent.intent_type == IntentType.general_chat:
            return self._build_general_response(intent)

        # book_recommendation / book_info → RAG 준비 완료
        return self._build_rag_ready_response(request.query, intent)

    # ── 응답 빌더 ─────────────────────────────────────────────

    def _build_clarification_response(self, intent: ExtractedIntent) -> ChatResponse:
        """추가 질문이 필요할 때의 응답을 만듭니다."""
        question = (
            intent.clarification_question
            or "어떤 종류의 책을 찾고 계신가요? 좋아하는 장르나 주제를 알려주세요!"
        )
        return ChatResponse(
            needs_clarification=True,
            clarification_question=question,
            intent=intent,
            message=question,
            ready_for_rag=False,
        )

    def _build_general_response(self, intent: ExtractedIntent) -> ChatResponse:
        """일반 대화 응답을 만듭니다."""
        return ChatResponse(
            needs_clarification=False,
            intent=intent,
            message=_GENERAL_RESPONSE,
            ready_for_rag=False,
        )

    def _build_rag_ready_response(
        self, original_query: str, intent: ExtractedIntent
    ) -> ChatResponse:
        """
        RAG 검색 준비가 완료된 응답을 만듭니다.
        M1 이 정제한 search_query 를 우선 사용하고, 없으면 원본 쿼리 사용.
        """
        search_query = intent.search_query or original_query
        template = _TEMPLATES.get(intent.intent_type, "관련 도서를 찾아볼게요!")
        message = template.format(query=search_query)

        return ChatResponse(
            needs_clarification=False,
            intent=intent,
            message=message,
            ready_for_rag=True,
            search_query=search_query,
        )


# 싱글턴 인스턴스 — 라우터에서 import 해서 재사용
chat_service = ChatService()
