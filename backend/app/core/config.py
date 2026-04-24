"""
설정 모듈.

애플리케이션 설정을 관리합니다.
나중에 환경 변수와 설정 파일에서 로드됩니다.
"""

from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    """애플리케이션 설정."""

    # 데이터베이스
    database_url: str = "postgresql://user:password@localhost:5432/libraian"

    # 벡터 DB
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333

    # API 키들
    hcx_api_key: str = ""
    hcx_api_url: str = "https://clovastudio.stream.naver.com"
    naru_api_key: str = ""
    naru_api_url: str = "http://data4library.kr/api"

    # 앱 설정
    debug: bool = True
    secret_key: str = "your-secret-key-change-in-production"
    cors_origins: List[str] = ["http://localhost:5173", "http://localhost:3000"]

    class Config:
        env_file = ".env"
        case_sensitive = False


# 설정 인스턴스
settings = Settings()