# -*- coding: utf-8 -*-
import os
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base

if os.getenv("USE_POSTGRES", "").lower() == "true":
    from sqlalchemy.dialects.postgresql import JSONB as _JsonType
else:
    from sqlalchemy import JSON as _JsonType


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id          : Mapped[int]      = mapped_column(Integer, primary_key=True, index=True)
    user_id     : Mapped[int]      = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title       : Mapped[str]      = mapped_column(String(200), nullable=False, default="새 대화")

    # 대화 복원에 필요한 상태
    messages    : Mapped[list]     = mapped_column(_JsonType, default=list)   # UI 메시지 목록
    context     : Mapped[dict]     = mapped_column(_JsonType, nullable=True)  # 마지막 SessionContext
    history     : Mapped[list]     = mapped_column(_JsonType, default=list)   # LLM 대화 히스토리
    pending_slots: Mapped[list]    = mapped_column(_JsonType, nullable=True)  # 마지막 pending_slots

    created_at  : Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at  : Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
