"""
평가 메트릭 모듈.

검색 성능 평가를 위한 다양한 메트릭을 제공합니다.
나중에 실험 결과 분석에 사용됩니다.
"""

from typing import List, Dict, Any
import math


def hit_rate_at_k(retrieved: List[str], relevant: List[str], k: int) -> float:
    """Hit@K 메트릭 계산.

    Args:
        retrieved: 검색된 항목 ID 리스트
        relevant: 관련 항목 ID 리스트
        k: 평가할 상위 k개

    Returns:
        Hit@K 점수
    """
    retrieved_at_k = retrieved[:k]
    hits = len(set(retrieved_at_k) & set(relevant))
    return 1.0 if hits > 0 else 0.0


def ndcg_at_k(retrieved: List[str], relevant: List[str], k: int) -> float:
    """NDCG@K 메트릭 계산.

    Args:
        retrieved: 검색된 항목 ID 리스트
        relevant: 관련 항목 ID 리스트
        k: 평가할 상위 k개

    Returns:
        NDCG@K 점수
    """
    retrieved_at_k = retrieved[:k]
    dcg = 0.0
    for i, item in enumerate(retrieved_at_k):
        if item in relevant:
            dcg += 1.0 / math.log2(i + 2)

    # IDCG 계산
    idcg = sum(1.0 / math.log2(i + 2) for i in range(min(len(relevant), k)))

    return dcg / idcg if idcg > 0 else 0.0


def mean_reciprocal_rank(retrieved: List[str], relevant: List[str]) -> float:
    """MRR 메트릭 계산.

    Args:
        retrieved: 검색된 항목 ID 리스트
        relevant: 관련 항목 ID 리스트

    Returns:
        MRR 점수
    """
    for i, item in enumerate(retrieved):
        if item in relevant:
            return 1.0 / (i + 1)
    return 0.0


def evaluate_all(retrieved: List[str], eval_set: Dict[str, Any], k: int = 10) -> Dict[str, float]:
    """모든 메트릭 평가.

    Args:
        retrieved: 검색된 항목 ID 리스트
        eval_set: 평가 데이터 (relevant_isbns 포함)
        k: 평가할 상위 k개

    Returns:
        메트릭 결과 딕셔너리
    """
    relevant = eval_set.get("relevant_isbns", [])

    return {
        "hit_rate": hit_rate_at_k(retrieved, relevant, k),
        "ndcg": ndcg_at_k(retrieved, relevant, k),
        "mrr": mean_reciprocal_rank(retrieved, relevant)
    }