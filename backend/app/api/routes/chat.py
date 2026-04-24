"""
채팅 라우트 모듈.

사용자와의 채팅 인터페이스를 제공합니다.
나중에 챗봇 기능에 사용됩니다.
"""

from fastapi import APIRouter, Depends
from ..schemas import QueryRequest, SearchResponse


router = APIRouter()


@router.post("/chat", response_model=SearchResponse)
async def chat_with_ai(request: QueryRequest):
    """AI와 채팅하여 도서 추천.

    Args:
        request: 쿼리 요청

    Returns:
        검색 응답
    """
    # TODO: RAG 파이프라인 호출 구현
    return SearchResponse(
        results=[],
        explanation="채팅 기능이 곧 제공됩니다.",
        query_analysis={"intent": "chat"}
    )