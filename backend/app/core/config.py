# -*- coding: utf-8 -*-
# ============================================================
# app/core/config.py
#
# 변경 이력:
#   v0.1 - 최초 작성
#   v0.2 - [FIX] conda 환경에서 .env 파일 못 읽는 경우 대비,
#           CLOVA_API_KEY 미설정 시 경고 로그 추가
# ============================================================
"""
전역 설정 및 환경변수 관리

pydantic-settings 가 .env 파일을 자동으로 읽어서
Settings 클래스의 필드에 주입해줍니다.

사용법:
    from app.core.config import settings
    print(settings.CLOVA_API_KEY)
"""
import logging

from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    # ── CLOVA Studio ─────────────────────────────────────────
    # OpenAI 호환 엔드포인트를 사용하므로 openai SDK를 그대로 재활용합니다.
    # HCX-DASH-002 : 빠른 경량 모델 — 의도 분류처럼 짧은 작업에 적합
    CLOVA_API_KEY: str = ""
    CLOVA_MODEL: str = "HCX-DASH-002"
    CLOVA_BASE_URL: str = "https://clovastudio.stream.ntruss.com/v1/openai"

    NARU_API_KEY : str = ""
    NARU_API_URL : str = "http://data4library.kr/api"
    NARU_LIB_CODE: str = ""

    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"

    # ── Elasticsearch ───────────────────────────────────────
    ELASTIC_URL: str
    ELASTIC_USER: str
    ELASTIC_PASSWORD: str

    # ── PostgreSQL ───────────────────────────────────────
    DB_HOST: str
    DB_PORT: str
    DB_NAME: str
    DB_USER: str
    DB_PASSWORD: str

    # ── AWS ──────────────────────────────────────────────
    AWS_PUBLIC_IP: str

    # ── 앱 일반 ──────────────────────────────────────────────
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"

    model_config = {
        # [FIX] pydantic v2 에서는 class Config 대신 model_config 사용
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }



# 모듈 레벨 싱글턴 — 앱 전체에서 import해서 재사용
settings = Settings()

# API 키 미설정 시 서버 시작 단계에서 바로 알 수 있도록 경고 출력
if not settings.CLOVA_API_KEY:
    logger.warning(
        "[config] CLOVA_API_KEY 가 설정되지 않았습니다. "
        ".env 파일에 CLOVA_API_KEY=... 를 추가해주세요."
    )

