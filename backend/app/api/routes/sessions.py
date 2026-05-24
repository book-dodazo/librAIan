# -*- coding: utf-8 -*-
"""
/api/sessions 라우터

엔드포인트:
    GET    /api/sessions         : 내 세션 목록
    GET    /api/sessions/{id}    : 세션 상세 (대화 복원용)
    DELETE /api/sessions/{id}    : 세션 삭제
    PATCH  /api/sessions/{id}    : 세션 제목 수정
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_current_user_id
from app.db.database import get_db
from app.models.chat_session import ChatSession

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/sessions", tags=["sessions"])


class SessionSummary(BaseModel):
    id        : int
    title     : str
    created_at: str
    updated_at: str


class SessionDetail(BaseModel):
    id           : int
    title        : str
    messages     : list
    context      : Optional[dict]
    history      : list
    pending_slots: Optional[list]
    created_at   : str
    updated_at   : str


class PatchTitleRequest(BaseModel):
    title: str


@router.get("", response_model=list[SessionSummary])
def list_sessions(
    user_id: int = Depends(get_current_user_id),
    db     : Session = Depends(get_db),
):
    """내 세션 목록 — 최신순 20개"""
    rows = (
        db.query(ChatSession)
        .filter(ChatSession.user_id == user_id)
        .order_by(ChatSession.updated_at.desc())
        .limit(20)
        .all()
    )
    return [
        SessionSummary(
            id         = r.id,
            title      = r.title,
            created_at = r.created_at.isoformat(),
            updated_at = r.updated_at.isoformat(),
        )
        for r in rows
    ]


@router.get("/{session_id}", response_model=SessionDetail)
def get_session(
    session_id: int,
    user_id   : int = Depends(get_current_user_id),
    db        : Session = Depends(get_db),
):
    """세션 상세 조회 — 대화 복원에 필요한 모든 상태 반환"""
    row = db.query(ChatSession).filter(
        ChatSession.id == session_id,
        ChatSession.user_id == user_id,
    ).first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="세션을 찾을 수 없습니다.")
    return SessionDetail(
        id            = row.id,
        title         = row.title,
        messages      = row.messages or [],
        context       = row.context,
        history       = row.history or [],
        pending_slots = row.pending_slots,
        created_at    = row.created_at.isoformat(),
        updated_at    = row.updated_at.isoformat(),
    )


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(
    session_id: int,
    user_id   : int = Depends(get_current_user_id),
    db        : Session = Depends(get_db),
):
    """세션 삭제"""
    row = db.query(ChatSession).filter(
        ChatSession.id == session_id,
        ChatSession.user_id == user_id,
    ).first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="세션을 찾을 수 없습니다.")
    db.delete(row)
    db.commit()


@router.patch("/{session_id}", response_model=SessionSummary)
def rename_session(
    session_id: int,
    body      : PatchTitleRequest,
    user_id   : int = Depends(get_current_user_id),
    db        : Session = Depends(get_db),
):
    """세션 제목 수정"""
    row = db.query(ChatSession).filter(
        ChatSession.id == session_id,
        ChatSession.user_id == user_id,
    ).first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="세션을 찾을 수 없습니다.")
    row.title = body.title[:200]
    db.commit()
    db.refresh(row)
    return SessionSummary(
        id         = row.id,
        title      = row.title,
        created_at = row.created_at.isoformat(),
        updated_at = row.updated_at.isoformat(),
    )
