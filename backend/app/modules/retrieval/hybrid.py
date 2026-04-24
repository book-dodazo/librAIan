"""
하이브리드 검색 모듈.

밀집 벡터 검색과 BM25를 결합한 검색을 수행합니다.
나중에 최적의 검색 성능을 위해 사용됩니다.
"""

from typing import List, Dict, Any
from .dense import DenseRetriever
from .bm25 import BM25Retriever


class HybridRetriever:
    """하이브리드 검색기."""

    def __init__(self, dense_retriever: DenseRetriever, bm25_retriever: BM25Retriever, alpha: float = 0.5) -> None:
        """검색기 초기화.

        Args:
            dense_retriever: 밀집 검색기
            bm25_retriever: BM25 검색기
            alpha: 밀집 검색 가중치 (0-1)
        """
        self.dense_retriever = dense_retriever
        self.bm25_retriever = bm25_retriever
        self.alpha = alpha

    def retrieve(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """하이브리드 검색 수행.

        Args:
            query: 검색 쿼리
            top_k: 반환할 상위 결과 수

        Returns:
            검색 결과 리스트
        """
        # 밀집 검색 결과
        dense_results = self.dense_retriever.retrieve(query, top_k=top_k*2)  # 더 많이 가져와서 결합

        # BM25 검색 결과
        bm25_results = self.bm25_retriever.retrieve(query, top_k=top_k*2)

        # 결과 결합 (간단한 구현 - 실제로는 더 정교한 방법 필요)
        combined_results = {}

        # 밀집 결과 추가
        for result in dense_results:
            doc_id = result.get("payload", {}).get("id", str(id(result)))
            combined_results[doc_id] = {
                "score": result["score"] * self.alpha,
                "payload": result.get("payload", {})
            }

        # BM25 결과 추가
        for result in bm25_results:
            doc_id = result["doc_id"]
            if doc_id in combined_results:
                combined_results[doc_id]["score"] += result["score"] * (1 - self.alpha)
            else:
                combined_results[doc_id] = {
                    "score": result["score"] * (1 - self.alpha),
                    "payload": {"id": doc_id}
                }

        # 정렬 및 상위 k개 반환
        sorted_results = sorted(combined_results.values(), key=lambda x: x["score"], reverse=True)
        return sorted_results[:top_k]