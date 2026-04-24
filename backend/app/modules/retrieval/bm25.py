"""
BM25 검색 모듈.

키워드 기반의 전통적 검색을 수행합니다.
나중에 하이브리드 검색의 일부로 사용됩니다.
"""

from typing import List, Dict, Any
from rank_bm25 import BM25Okapi
import numpy as np


class BM25Retriever:
    """BM25 검색기."""

    def __init__(self, documents: List[str], doc_ids: List[str]) -> None:
        """검색기 초기화.

        Args:
            documents: 문서 리스트
            doc_ids: 문서 ID 리스트
        """
        self.doc_ids = doc_ids
        tokenized_docs = [doc.split() for doc in documents]
        self.bm25 = BM25Okapi(tokenized_docs)

    def retrieve(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """쿼리에 대한 BM25 검색.

        Args:
            query: 검색 쿼리
            top_k: 반환할 상위 결과 수

        Returns:
            검색 결과 리스트
        """
        tokenized_query = query.split()
        scores = self.bm25.get_scores(tokenized_query)

        # 상위 k개 인덱스 가져오기
        top_indices = np.argsort(scores)[::-1][:top_k]

        results = []
        for idx in top_indices:
            results.append({
                "doc_id": self.doc_ids[idx],
                "score": float(scores[idx])
            })

        return results