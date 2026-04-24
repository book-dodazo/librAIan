"""
설명 생성 모듈.

검색 결과를 바탕으로 사용자에게 설명을 생성합니다.
나중에 결과 해석에 사용됩니다.
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

        # 간단한 설명 생성
        top_result = results[0]
        title = top_result.get("title", "알 수 없음")
        reason = f"'{query}'와 관련된 도서 '{title}'을 추천합니다."

        if len(results) > 1:
            reason += f" 외 {len(results)-1}개의 관련 도서가 더 있습니다."

        return reason

    def generate_detailed_explanation(self, query: str, result: Dict[str, Any]) -> str:
        """단일 결과에 대한 상세 설명.

        Args:
            query: 검색 쿼리
            result: 단일 검색 결과

        Returns:
            상세 설명
        """
        # TODO: 더 정교한 설명 생성 로직
        return self.generate_explanation(query, [result])