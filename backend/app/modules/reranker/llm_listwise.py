"""
LLM 리스트와이즈 리랭커 모듈.

LLM을 사용하여 전체 리스트를 한 번에 재정렬합니다.
나중에 복잡한 리랭킹 로직에 사용됩니다.
"""

from typing import List, Dict, Any
from .reranker import Reranker


class LLMListwiseReranker(Reranker):
    """LLM 리스트와이즈 리랭커."""

    def __init__(self, model_name: str = "gpt-3.5-turbo") -> None:
        """리랭커 초기화.

        Args:
            model_name: 사용할 LLM 모델 이름
        """
        self.model_name = model_name

    def rerank(self, query: str, candidates: List[Dict[str, Any]], top_k: int = 10) -> List[Dict[str, Any]]:
        """LLM을 사용한 리스트와이즈 리랭킹.

        Args:
            query: 검색 쿼리
            candidates: 재정렬할 후보 리스트
            top_k: 반환할 상위 결과 수

        Returns:
            재정렬된 결과 리스트
        """
        # TODO: LLM API 호출로 리스트와이즈 리랭킹 구현
        # 임시로 원래 순서 유지
        return candidates[:top_k]