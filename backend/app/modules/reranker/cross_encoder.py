"""
크로스 인코더 리랭커 모듈.

크로스 인코더 모델을 사용한 쿼리-문서 쌍의 관련성 점수 계산.
나중에 정확한 리랭킹에 사용됩니다.
"""

from typing import List, Dict, Any
from .reranker import Reranker
from FlagEmbedding import FlagReranker


class CrossEncoderReranker(Reranker):
    """크로스 인코더 리랭커."""

    def __init__(self, model_name: str = "BAAI/bge-reranker-base") -> None:
        """리랭커 초기화.

        Args:
            model_name: 크로스 인코더 모델 이름
        """
        self.reranker = FlagReranker(model_name)

    def rerank(self, query: str, candidates: List[Dict[str, Any]], top_k: int = 10) -> List[Dict[str, Any]]:
        """크로스 인코더를 사용한 리랭킹.

        Args:
            query: 검색 쿼리
            candidates: 재정렬할 후보 리스트
            top_k: 반환할 상위 결과 수

        Returns:
            재정렬된 결과 리스트
        """
        # 쿼리-문서 쌍 생성
        docs = [candidate.get("title", "") + " " + candidate.get("description", "") for candidate in candidates]
        query_doc_pairs = [[query, doc] for doc in docs]

        # 점수 계산
        scores = self.reranker.compute_score(query_doc_pairs)

        # 점수와 후보 결합
        scored_candidates = [
            {**candidate, "rerank_score": score}
            for candidate, score in zip(candidates, scores)
        ]

        # 점수로 정렬
        scored_candidates.sort(key=lambda x: x["rerank_score"], reverse=True)

        return scored_candidates[:top_k]