"""
데이터베이스 모델 모듈.

SQLAlchemy 모델을 정의합니다.
나중에 데이터베이스 스키마에 사용됩니다.
"""

from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime


class Book(SQLModel, table=True):
    """도서 모델."""
    isbn: str = Field(primary_key=True)
    title: str
    author: str
    description: Optional[str] = None
    published_date: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class User(SQLModel, table=True):
    """사용자 모델."""
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: str = Field(unique=True)
    preferences: str  # JSON string
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class UserReadingHistory(SQLModel, table=True):
    """사용자 독서 기록 모델."""
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: str
    isbn: str
    read_at: datetime = Field(default_factory=datetime.utcnow)


class SearchLog(SQLModel, table=True):
    """검색 로그 모델."""
    id: Optional[int] = Field(default=None, primary_key=True)
    query: str
    user_id: Optional[str] = None
    results_count: int
    searched_at: datetime = Field(default_factory=datetime.utcnow)