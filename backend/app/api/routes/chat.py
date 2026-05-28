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
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.auth import get_optional_user_id
from app.core.exceptions import LLMCallError
from app.db.database import get_db
from app.models.chat_session import ChatSession
from app.schemas.chat_schema import ChatRequest, SlotChatResponse
from app.services.chat_service import chat_service

_REQUEST_TIMEOUT = 90  # 초 — 요청 전체 타임아웃

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["chat"])


def _save_session(
    db          : Session,
    user_id     : int,
    session_id  : Optional[int],
    request     : ChatRequest,
    response    : SlotChatResponse,
) -> int:
    """교환 후 세션 저장/업데이트 — session_id 반환"""
    # UI 메시지 누적 (user + assistant)
    new_messages = list(request.context.get("_ui_messages", []) if request.context else [])
    new_messages.append({"role": "user", "text": request.query})
    new_messages.append({
        "role"                : "assistant",
        "text"                : response.message,
        "isConfirmation"      : response.is_confirmation,
        "inferred_summary"    : response.inferred_summary,
        "isClarification"     : response.needs_clarification,
        "clarification_question": response.clarification_question,
        "choices"             : response.clarification_choices,
        "pending_slots"       : response.pending_slots,
        "hasResults"          : response.ready_for_rag and bool(response.search_results),
        "search_results"      : response.search_results,
        "also_results"        : response.also_results,
        "availability_index"  : response.availability_index,
    })

    # context에 UI 메시지 목록 첨부 (다음 턴에 전달)
    ctx = dict(response.context or {})
    ctx["_ui_messages"] = new_messages

    if session_id:
        row = db.query(ChatSession).filter(ChatSession.id == session_id, ChatSession.user_id == user_id).first()
        if row:
            row.messages      = new_messages
            row.context       = ctx
            row.history       = request.history + [
                {"role": "user",      "content": request.query},
                {"role": "assistant", "content": response.message},
            ]
            row.pending_slots = response.pending_slots
            row.updated_at    = datetime.now(timezone.utc)
            db.commit()
            return row.id

    # 신규 세션 생성 — 제목은 첫 질의에서 자동 생성
    title = request.query[:50] + ("..." if len(request.query) > 50 else "")
    row = ChatSession(
        user_id      = user_id,
        title        = title,
        messages     = new_messages,
        context      = ctx,
        history      = [
            {"role": "user",      "content": request.query},
            {"role": "assistant", "content": response.message},
        ],
        pending_slots = response.pending_slots,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row.id


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
async def chat_endpoint(
    request : ChatRequest,
    user_id : Optional[int] = Depends(get_optional_user_id),
    db      : Session       = Depends(get_db),
) -> SlotChatResponse:
    try:
        response = await asyncio.wait_for(
            chat_service.handle(request),
            timeout=_REQUEST_TIMEOUT,
        )

        # 로그인된 유저면 세션 자동 저장
        if user_id:
            try:
                sid = _save_session(db, user_id, request.session_id, request, response)
                response.session_id = sid
                # context에도 _ui_messages 반영된 버전으로 교체
                if response.context:
                    response.context["_ui_messages"] = response.context.get("_ui_messages", [])
            except Exception as e:
                logger.warning("세션 저장 실패 (non-critical): %s", e)

        return response
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
