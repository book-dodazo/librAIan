"""
Qdrant 벡터 데이터베이스 클라이언트 모듈.

Qdrant에 벡터를 저장하고 검색하는 기능을 제공합니다.
나중에 도서 벡터 데이터베이스 관리에 사용됩니다.
"""

from typing import List, Dict, Any
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams


class QdrantVectorDB:
    """Qdrant 벡터 데이터베이스 클라이언트."""

    def __init__(self, host: str = "localhost", port: int = 6333, api_key: str = None) -> None:
        """클라이언트 초기화.

        Args:
            host: Qdrant 호스트
            port: Qdrant 포트
            api_key: API 키 (선택)
        """
        self.client = QdrantClient(host=host, port=port, api_key=api_key)

    def create_collection(self, collection_name: str, vector_size: int) -> None:
        """컬렉션 생성.

        Args:
            collection_name: 컬렉션 이름
            vector_size: 벡터 차원 수
        """
        self.client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE)
        )

    def insert_vectors(self, collection_name: str, vectors: List[List[float]], payloads: List[Dict[str, Any]]) -> None:
        """벡터 삽입.

        Args:
            collection_name: 컬렉션 이름
            vectors: 벡터 리스트
            payloads: 메타데이터 리스트
        """
        points = [
            {"id": i, "vector": vector, "payload": payload}
            for i, (vector, payload) in enumerate(zip(vectors, payloads))
        ]
        self.client.upsert(collection_name=collection_name, points=points)

    def search(self, collection_name: str, query_vector: List[float], limit: int = 10) -> List[Dict[str, Any]]:
        """벡터 검색.

        Args:
            collection_name: 컬렉션 이름
            query_vector: 쿼리 벡터
            limit: 반환할 결과 수

        Returns:
            검색 결과
        """
        results = self.client.search(
            collection_name=collection_name,
            query_vector=query_vector,
            limit=limit
        )
        return [{"score": hit.score, "payload": hit.payload} for hit in results]