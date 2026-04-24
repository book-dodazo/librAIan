"""
밀집 벡터 검색 모듈.

임베딩 기반의 의미론적 검색을 수행합니다.
나중에 도서 검색의 기본 방법으로 사용됩니다.
"""

from typing import List, Dict, Any
from .embedder import Embedder
from .qdrant_client import QdrantVectorDB


class DenseRetriever:
    """밀집 벡터 검색기."""

    def __init__(self, embedder: Embedder, vector_db: QdrantVectorDB, collection_name: str) -> None:
        """검색기 초기화.

        Args:
            embedder: 임베더 인스턴스
            vector_db: 벡터 DB 인스턴스
            collection_name: 컬렉션 이름
        """
        self.embedder = embedder
        self.vector_db = vector_db
        self.collection_name = collection_name

    def retrieve(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """쿼리에 대한 도서 검색.

        Args:
            query: 검색 쿼리
            top_k: 반환할 상위 결과 수

        Returns:
            검색 결과 리스트
        """
        query_vector = self.embedder.encode_single(query)
        return self.vector_db.search(self.collection_name, query_vector, limit=top_k)