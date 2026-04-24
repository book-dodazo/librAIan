"""
평가자 모듈.

전체 평가 파이프라인을 실행합니다.
나중에 배치 평가에 사용됩니다.
"""

from typing import List, Dict, Any
from .metrics import evaluate_all


class Evaluator:
    """평가자 클래스."""

    def __init__(self, eval_data: List[Dict[str, Any]]) -> None:
        """평가자 초기화.

        Args:
            eval_data: 평가 데이터 리스트
        """
        self.eval_data = eval_data

    def evaluate_retriever(self, retriever, k: int = 10) -> Dict[str, float]:
        """검색기 평가.

        Args:
            retriever: 평가할 검색기 인스턴스
            k: 평가할 상위 k개

        Returns:
            평균 메트릭 결과
        """
        total_metrics = {"hit_rate": 0.0, "ndcg": 0.0, "mrr": 0.0}

        for eval_item in self.eval_data:
            query = eval_item["query"]
            # 검색 수행 (retriever.retrieve 구현 필요)
            retrieved_ids = [result.get("isbn", "") for result in retriever.retrieve(query, top_k=k)]

            metrics = evaluate_all(retrieved_ids, eval_item, k)

            for key in total_metrics:
                total_metrics[key] += metrics[key]

        # 평균 계산
        num_queries = len(self.eval_data)
        return {key: value / num_queries for key, value in total_metrics.items()}