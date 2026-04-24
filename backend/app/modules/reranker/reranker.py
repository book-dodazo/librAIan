"""
리랭커 베이스 모듈.

리랭킹을 위한 기본 클래스와 하드 필터를 제공합니다.
나중에 다양한 리랭킹 알고리즘의 기반으로 사용됩니다.
"""

from typing import List, Dict, Any
from abc import ABC, abstractmethod


class HardFilter:
    """하드 필터 클래스."""

    def __init__(self, availability_api_url: str, api_key: str) -> None:
        """필터 초기화.

        Args:
            availability_api_url: 도서관정보나루 API URL
            api_key: API 키
        """
        self.api_url = availability_api_url
        self.api_key = api_key

    def filter(self, candidates: List[Dict[str, Any]], user_location: str = None) -> List[Dict[str, Any]]:
        """대출 가능한 도서만 필터링.

        Args:
            candidates: 후보 도서 리스트
            user_location: 사용자 위치 (선택)

        Returns:
            필터링된 도서 리스트
        """
        # TODO: 도서관정보나루 API로 대출 가능 여부 확인
        return candidates  # 임시로 모두 통과


class Reranker(ABC):
    """리랭커 베이스 클래스."""

    @abstractmethod
    def rerank(self, query: str, candidates: List[Dict[str, Any]], top_k: int = 10) -> List[Dict[str, Any]]:
        """후보들을 재정렬.

        Args:
            query: 검색 쿼리
            candidates: 재정렬할 후보 리스트
            top_k: 반환할 상위 결과 수

        Returns:
            재정렬된 결과 리스트
        """
        pass