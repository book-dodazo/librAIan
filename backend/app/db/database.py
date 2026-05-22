import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

# USE_POSTGRES=true 로 명시해야만 PostgreSQL 사용 — 기본값은 SQLite
if os.getenv("USE_POSTGRES", "").lower() == "true":
    from app.core.config import settings
    DATABASE_URL = (
        f"postgresql+psycopg2://{settings.DB_USER}:{settings.DB_PASSWORD}"
        f"@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"
    )
    engine = create_engine(DATABASE_URL)
else:
    DATABASE_URL = "sqlite:///./libraiian.db"
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Base(DeclarativeBase):
    pass

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
