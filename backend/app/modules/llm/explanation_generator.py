"""
설명 생성 모듈.

검색 결과를 바탕으로 자연어 설명을 생성합니다.
나중에 사용자 응답 생성에 사용됩니다.
"""

from typing import List, Dict, Any


class ExplanationGenerator:
    """설명 생성기."""

    def __init__(self) -> None:
        """초기화."""
        pass

    def generate_explanation(self, query: str, results: List[Dict[str, Any]]) -> str:
        """결과에 대한 설명 생성.

        Args:
            query: 검색 쿼리
            results: 검색 결과

        Returns:
            생성된 설명
        """
        if not results:
            return "검색 결과가 없습니다."

        # TODO: LLM API 호출로 설명 생성 구현
        top_result = results[0]
        title = top_result.get("title", "알 수 없음")
        return f"'{query}'에 대한 추천 도서: {title}"