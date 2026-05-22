# -*- coding: utf-8 -*-
# ============================================================
# app/main.py
#
# 변경 이력:
#   v0.1 - 최초 작성
#   v0.2 - [FIX] 로깅 설정을 app 생성 전에 먼저 실행하도록 순서 변경
#           (기존: 일부 모듈 임포트 로그가 설정 전에 출력됨)
# ============================================================
"""
FastAPI 앱 진입점

실행 방법:
    # conda 환경 활성화 후 backend 폴더에서
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

접속:
    API 문서 (Swagger UI) : http://localhost:8000/docs
    ReDoc                 : http://localhost:8000/redoc
    헬스 체크             : http://localhost:8000/api/health
"""
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from fastapi import Request
from pathlib import Path

from app.core.config import settings
from app.api.routes.chat import router as chat_router
from app.api.routes.auth import router as auth_router
from app.api.routes.profile import router as profile_router
from app.api.routes.onboarding import router as onboarding_router
from app.api.routes.eval import router as eval_router
from app.db.database import engine, Base
import app.models.user  # noqa: F401 — 테이블 생성을 위해 import

# [FIX v0.2] 로깅 설정을 가장 먼저 실행
logging.basicConfig(
    level=settings.LOG_LEVEL,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)

# ── 키 로드 확인 ──────────────────────────────────────────────
_log = logging.getLogger("app.startup")
_key = settings.CLOVA_API_KEY
if _key:
    _log.info("CLOVA_API_KEY 로드됨: %s...%s (len=%d)", _key[:6], _key[-4:], len(_key))
else:
    _log.error("CLOVA_API_KEY 비어 있음 — .env 파일 위치·내용 확인 필요")

# ── FastAPI 앱 생성 ───────────────────────────────────────────
app = FastAPI(
    title="📚 AI 도서 큐레이션 API",
    description="도서관 맥락 기반 개인화 도서 추천 시스템 — C파트 백엔드",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS 설정 ─────────────────────────────────────────────────
# 개발 환경: 프론트(3000)에서 백엔드(8000)로 요청 허용
# 프로덕션에서는 allow_origins 를 실제 도메인으로 좁혀야 합니다.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",   # Next.js 개발 서버
        "http://localhost:3001",
        "null",                    # 로컬 HTML 파일(demo.html)을 file:// 로 열 때
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── DB 테이블 생성 ────────────────────────────────────────────
Base.metadata.create_all(bind=engine)

# ── 라우터 등록 ───────────────────────────────────────────────
app.include_router(chat_router)
app.include_router(auth_router)
app.include_router(profile_router)
app.include_router(onboarding_router)
app.include_router(eval_router)

# ── 템플릿 설정 ───────────────────────────────────────────────
templates = Jinja2Templates(directory="app/templates")


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    api_base = (
        f"http://{settings.AWS_PUBLIC_IP}:8000"
        if settings.AWS_PUBLIC_IP
        else "http://localhost:8000"
    )
    return templates.TemplateResponse(
        name = "index.html", 
        request = request,
        context = {"apiBase": api_base}
    )