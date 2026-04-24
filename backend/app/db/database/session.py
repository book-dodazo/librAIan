"""
데이터베이스 세션 모듈.

데이터베이스 연결과 세션을 관리합니다.
나중에 DB 작업에 사용됩니다.
"""

from sqlmodel import create_engine, Session
from typing import Generator
import os


DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@localhost:5432/libraian")

engine = create_engine(DATABASE_URL, echo=False)


def get_session() -> Generator[Session, None, None]:
    """데이터베이스 세션 생성기.

    Yields:
        데이터베이스 세션
    """
    with Session(engine) as session:
        yield session


def create_tables():
    """데이터베이스 테이블 생성."""
    from .models import SQLModel
    SQLModel.metadata.create_all(engine)