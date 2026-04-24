"""
API 스키마 모듈.

요청/응답 데이터 모델을 정의합니다.
나중에 API 데이터 검증에 사용됩니다.
"""

from pydantic import BaseModel
from typing import List, Optional, Dict, Any


class QueryRequest(BaseModel):
    """쿼리 요청 스키마."""
    query: str
    user_id: Optional[str] = None
    preferences: Optional[Dict[str, Any]] = None


class BookResult(BaseModel):
    """도서 결과 스키마."""
    isbn: str
    title: str
    author: str
    description: Optional[str] = None
    score: float
    availability: Optional[bool] = None


class SearchResponse(BaseModel):
    """검색 응답 스키마."""
    results: List[BookResult]
    explanation: str
    query_analysis: Optional[Dict[str, Any]] = None


class RecommendationRequest(BaseModel):
    """추천 요청 스키마."""
    user_id: str
    limit: Optional[int] = 10


class UserProfile(BaseModel):
    """사용자 프로필 스키마."""
    user_id: str
    preferences: Dict[str, Any]
    reading_history: List[str]  # ISBN 리스트


class LibraryInfo(BaseModel):
    """도서관 정보 스키마."""
    library_code: str
    name: str
    location: str