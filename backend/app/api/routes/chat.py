# -*- coding: utf-8 -*-
# ============================================================
# app/api/routes/chat.py
#
# 변경 이력:
#   v0.1 - 최초 작성
#   v0.2 - [FIX] router 모듈 최상단 선언
#   v0.3 - slot 기반 파이프라인 응답 구조로 변경
# ============================================================
"""
/api/chat 라우터

엔드포인트:
    POST /api/chat   : 사용자 질의 처리 (slot filling + RAG 쿼리 생성)
    GET  /api/health : 서버 상태 확인
"""
import asyncio
import logging

from fastapi import APIRouter, HTTPException, status

from app.core.exceptions import LLMCallError
from app.schemas.chat_schema import ChatRequest, SlotChatResponse
from app.services.chat_service import chat_service

_REQUEST_TIMEOUT = 90  # 초 — 요청 전체 타임아웃

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["chat"])


@router.post(
    "/chat",
    response_model=SlotChatResponse,
    summary="사용자 질의 처리 및 slot filling",
    description="""
사용자 질의를 받아 slot을 채우고 RAG 검색 쿼리를 생성합니다.

**멀티턴 흐름:**
1. 첫 요청: `query` 전송, `context=null`
2. 추가 질문 응답: `selected_choice` + `pending_slots` + `context` 전송
3. RAG 준비 완료: `ready_for_rag=true` + `rag_query` 반환

**주의:** 매 응답의 `context`를 저장해두었다가 다음 요청에 포함해야 합니다.
    """,
)
async def chat_endpoint(request: ChatRequest) -> SlotChatResponse:
    try:
        return await asyncio.wait_for(
            chat_service.handle(request),
            timeout=_REQUEST_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.error("요청 타임아웃: %ds 초과", _REQUEST_TIMEOUT)
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=f"응답 시간이 {_REQUEST_TIMEOUT}초를 초과했습니다. 잠시 후 다시 시도해 주세요.",
        )
    except LLMCallError as e:
        logger.error("처리되지 않은 LLM 오류: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI 서비스에 일시적인 문제가 발생했습니다.",
        )
    except Exception as e:
        logger.exception("예상치 못한 오류: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="서버 내부 오류가 발생했습니다.",
        )


@router.get("/health", summary="헬스 체크")
async def health_check():
    """서버 상태 확인 (데모 프론트 연결 확인용)"""
    return {"status": "ok"}
