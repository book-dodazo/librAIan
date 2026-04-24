"""
도서관 라우트 모듈.

도서관 정보 및 대출 상태를 제공합니다.
나중에 도서 이용 지원에 사용됩니다.
"""

from fastapi import APIRouter
from typing import List
from ..schemas import LibraryInfo


router = APIRouter()


@router.get("/libraries", response_model=List[LibraryInfo])
async def get_libraries():
    """도서관 목록 조회.

    Returns:
        도서관 목록
    """
    # TODO: 도서관 목록 조회 구현
    return []


@router.get("/libraries/{library_code}/availability/{isbn}")
async def check_book_availability(library_code: str, isbn: str):
    """도서 대출 가능 여부 확인.

    Args:
        library_code: 도서관 코드
        isbn: ISBN

    Returns:
        대출 가능 정보
    """
    # TODO: 도서관정보나루 API 호출 구현
    return {"available": True, "due_date": None}