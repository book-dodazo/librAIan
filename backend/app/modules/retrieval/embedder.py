"""
임베딩 모듈.

텍스트를 벡터로 변환하는 기능을 제공합니다.
나중에 도서 텍스트를 벡터화하여 검색에 사용됩니다.
"""

from typing import List
from sentence_transformers import SentenceTransformer


class Embedder:
    """텍스트 임베딩 클래스."""

    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2") -> None:
        """임베더 초기화.

        Args:
            model_name: 사용할 임베딩 모델 이름
        """
        self.model = SentenceTransformer(model_name)

    def encode(self, texts: List[str]) -> List[List[float]]:
        """텍스트를 벡터로 변환.

        Args:
            texts: 인코딩할 텍스트 리스트

        Returns:
            벡터 리스트
        """
        return self.model.encode(texts).tolist()

    def encode_single(self, text: str) -> List[float]:
        """단일 텍스트를 벡터로 변환.

        Args:
            text: 인코딩할 텍스트

        Returns:
            벡터
        """
        return self.encode([text])[0]