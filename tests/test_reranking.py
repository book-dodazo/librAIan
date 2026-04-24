"""
리랭킹 모듈 테스트.

리랭킹 기능의 단위 테스트를 수행합니다.
나중에 리랭킹 모듈 검증에 사용됩니다.
"""

import pytest
from src.reranking.reranker import HardFilter


def test_hard_filter():
    """하드 필터 테스트."""
    filter_instance = HardFilter("http://test.api", "test_key")
    candidates = [
        {"title": "테스트 도서", "isbn": "1234567890"}
    ]
    filtered = filter_instance.filter(candidates)
    assert len(filtered) == len(candidates)  # 현재는 모두 통과


def test_reranker_interface():
    """리랭커 인터페이스 테스트."""
    # Reranker는 추상 클래스이므로 직접 테스트 불가
    # 구체적인 구현체 테스트 필요
    assert True  # Placeholder