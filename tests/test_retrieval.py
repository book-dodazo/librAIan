"""
검색 모듈 테스트.

벡터 검색 기능의 단위 테스트를 수행합니다.
나중에 검색 모듈 검증에 사용됩니다.
"""

import pytest
from src.retrieval.dense import DenseRetriever
from src.retrieval.embedder import Embedder


def test_embedder_initialization():
    """임베더 초기화 테스트."""
    embedder = Embedder()
    assert embedder.model is not None


def test_dense_retriever():
    """밀집 검색기 테스트."""
    embedder = Embedder()
    # Mock vector DB for testing
    # retriever = DenseRetriever(embedder, mock_vector_db, "test_collection")
    # 실제 구현 시 모킹 필요
    assert True  # Placeholder


def test_embedding_shape():
    """임베딩 벡터 차원 테스트."""
    embedder = Embedder()
    texts = ["테스트 문장"]
    vectors = embedder.encode(texts)
    assert len(vectors) == 1
    assert len(vectors[0]) > 0  # 벡터 차원 확인