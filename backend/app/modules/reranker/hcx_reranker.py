"""
HCX 리랭커 모듈.

HyperCLOVA X를 사용한 리랭킹을 수행합니다.
나중에 고품질 리랭킹을 위해 사용됩니다.
"""

from typing import List, Dict, Any
from .reranker import Reranker


class HCXReranker(Reranker):
    """HCX 기반 리랭커."""

    def __init__(self, api_key: str, api_url: str) -> None:
        """리랭커 초기화.

        Args:
            api_key: HCX API 키
            api_url: HCX API URL
        """
        self.api_key = api_key
        self.api_url = api_url

    def rerank(self, query: str, candidates: List[Dict[str, Any]], top_k: int = 10) -> List[Dict[str, Any]]:
        """HCX를 사용한 리랭킹.

        Args:
            query: 검색 쿼리
            candidates: 재정렬할 후보 리스트
            top_k: 반환할 상위 결과 수

        Returns:
            재정렬된 결과 리스트
        """
        # TODO: HCX API 호출로 리랭킹 구현
        # 임시로 원래 순서 유지
        return candidates[:top_k]