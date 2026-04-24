"""
오케스트레이터 모듈.

전체 RAG 파이프라인을 조율합니다.
나중에 시스템 실행에 사용됩니다.
"""

from typing import List, Dict, Any
from .query_understanding import QueryUnderstanding
from .explanation import ExplanationGenerator


class RAGOrchestrator:
    """RAG 오케스트레이터."""

    def __init__(self, retriever, reranker, query_understanding: QueryUnderstanding = None,
                 explanation_generator: ExplanationGenerator = None) -> None:
        """오케스트레이터 초기화.

        Args:
            retriever: 검색기 인스턴스
            reranker: 리랭커 인스턴스
            query_understanding: 쿼리 이해기 (선택)
            explanation_generator: 설명 생성기 (선택)
        """
        self.retriever = retriever
        self.reranker = reranker
        self.query_understanding = query_understanding or QueryUnderstanding()
        self.explanation_generator = explanation_generator or ExplanationGenerator()

    def process_query(self, query: str, top_k: int = 10) -> Dict[str, Any]:
        """쿼리 처리 파이프라인 실행.

        Args:
            query: 사용자 쿼리
            top_k: 반환할 상위 결과 수

        Returns:
            처리 결과
        """
        # 1. 쿼리 이해
        query_analysis = self.query_understanding.analyze_query(query)
        processed_query = query_analysis["processed_query"]

        # 2. 검색
        retrieved_results = self.retriever.retrieve(processed_query, top_k=top_k*2)  # 더 많이 검색

        # 3. 리랭킹
        reranked_results = self.reranker.rerank(processed_query, retrieved_results, top_k=top_k)

        # 4. 설명 생성
        explanation = self.explanation_generator.generate_explanation(query, reranked_results)

        return {
            "query_analysis": query_analysis,
            "results": reranked_results,
            "explanation": explanation
        }