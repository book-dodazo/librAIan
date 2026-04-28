# -*- coding: utf-8 -*-
import logging

from fastapi import APIRouter, HTTPException, status

from app.core.exceptions import LLMCallError
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chat_service import chat_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest) -> ChatResponse:
    try:
        return await chat_service.handle(request)
    except LLMCallError as e:
        logger.error("라우터에서 처리되지 않은 LLM 오류: %s", e)
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


@router.get("/health")
async def health_check():
    return {"status": "ok"}
