"""
LLM 심사관 모듈.

LLM을 사용하여 검색 결과를 평가합니다.
나중에 주관적 평가에 사용됩니다.
"""

from typing import List, Dict, Any


class LLMJudge:
    """LLM 기반 심사관."""

    def __init__(self, model_name: str = "gpt-3.5-turbo") -> None:
        """심사관 초기화.

        Args:
            model_name: 사용할 LLM 모델 이름
        """
        self.model_name = model_name

    def judge_relevance(self, query: str, document: str) -> float:
        """쿼리-문서 관련성 평가.

        Args:
            query: 검색 쿼리
            document: 평가할 문서

        Returns:
            관련성 점수 (0-1)
        """
        # TODO: LLM API 호출로 관련성 평가
        return 0.5  # 임시 값

    def evaluate_results(self, query: str, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """검색 결과 평가.

        Args:
            query: 검색 쿼리
            results: 평가할 결과 리스트

        Returns:
            평가 점수가 추가된 결과 리스트
        """
        evaluated_results = []
        for result in results:
            doc_text = result.get("title", "") + " " + result.get("description", "")
            score = self.judge_relevance(query, doc_text)
            result["llm_score"] = score
            evaluated_results.append(result)

        return evaluated_results