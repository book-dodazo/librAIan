"""
도서 이용 가능성 리랭커 모듈.

도서의 대출 가능성에 따라 결과를 재정렬합니다.
나중에 사용자 경험 향상에 사용됩니다.
"""

from typing import List, Dict, Any
from .reranker import Reranker


class AvailabilityReranker(Reranker):
    """이용 가능성 기반 리랭커."""

    def __init__(self, naru_api_url: str, api_key: str) -> None:
        """리랭커 초기화.

        Args:
            naru_api_url: 도서관정보나루 API URL
            api_key: API 키
        """
        self.api_url = naru_api_url
        self.api_key = api_key

    def rerank(self, query: str, candidates: List[Dict[str, Any]], top_k: int = 10) -> List[Dict[str, Any]]:
        """이용 가능성에 따른 리랭킹.

        Args:
            query: 검색 쿼리
            candidates: 재정렬할 후보 리스트
            top_k: 반환할 상위 결과 수

        Returns:
            재정렬된 결과 리스트
        """
        # TODO: 도서관정보나루 API로 이용 가능성 확인 및 점수 부여
        # 임시로 원래 순서 유지
        return candidates[:top_k]