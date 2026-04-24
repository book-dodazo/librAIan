"""
메인 API 모듈.

FastAPI 애플리케이션의 진입점입니다.
나중에 서버 실행에 사용됩니다.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routes import chat, recommend, profile, library


def create_app() -> FastAPI:
    """FastAPI 애플리케이션 생성.

    Returns:
        FastAPI 앱 인스턴스
    """
    app = FastAPI(
        title="librAIan API",
        description="도서관 맥락 기반 AI 도서 큐레이션 시스템 API",
        version="1.0.0"
    )

    # CORS 미들웨어 추가
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # 개발용 - 프로덕션에서는 특정 도메인으로 제한
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 라우터 등록
    app.include_router(chat.router, prefix="/api/v1", tags=["chat"])
    app.include_router(recommend.router, prefix="/api/v1", tags=["recommend"])
    app.include_router(profile.router, prefix="/api/v1", tags=["profile"])
    app.include_router(library.router, prefix="/api/v1", tags=["library"])

    @app.get("/health", tags=["health"])
    async def health_check():
        """헬스 체크 엔드포인트.

        Returns:
            헬스 상태
        """
        return {"status": "healthy"}

    return app


# 앱 인스턴스 생성
app = create_app()