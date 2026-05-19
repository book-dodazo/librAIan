from datetime import datetime, timezone
from sqlalchemy import Integer, String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.database import Base

class User(Base):
    __tablename__ = "users"

    id           : Mapped[int]      = mapped_column(Integer, primary_key=True, index=True)
    name         : Mapped[str]      = mapped_column(String, nullable=False)
    email        : Mapped[str]      = mapped_column(String, unique=True, index=True, nullable=False)
    password_hash: Mapped[str]      = mapped_column(String, nullable=False)
    created_at   : Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    profile: Mapped["UserProfile"] = relationship("UserProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")


class UserProfile(Base):
    __tablename__ = "user_profiles"

    user_id          : Mapped[int]      = mapped_column(Integer, ForeignKey("users.id"), primary_key=True)
    onboarding_data  : Mapped[dict]     = mapped_column(JSONB, default=dict)
    feedback_history : Mapped[list]     = mapped_column(JSONB, default=list)
    updated_at       : Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    user: Mapped["User"] = relationship("User", back_populates="profile")
