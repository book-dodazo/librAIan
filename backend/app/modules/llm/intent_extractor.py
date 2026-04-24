"""
의도 추출 모듈.

사용자 쿼리로부터 의도를 추출합니다.
나중에 쿼리 이해에 사용됩니다.
"""

from typing import Dict, Any


class IntentExtractor:
    """의도 추출기."""

    def __init__(self) -> None:
        """초기화."""
        pass

    def extract_intent(self, query: str) -> Dict[str, Any]:
        """쿼리로부터 의도 추출.

        Args:
            query: 사용자 쿼리

        Returns:
            의도 정보
        """
        # TODO: LLM API 호출로 의도 추출 구현
        return {
            "intent": "book_search",
            "entities": [],
            "confidence": 0.9
        }