"""
채팅 서비스 모듈.

API 라우터와 AI 모듈을 연결하는 오케스트레이션 계층입니다.
나중에 채팅 기능 통합에 사용됩니다.
"""

from typing import Dict, Any
from ..modules.llm.intent_extractor import IntentExtractor
from ..modules.llm.explanation_generator import ExplanationGenerator


class ChatService:
    """채팅 서비스."""

    def __init__(self, retriever, reranker) -> None:
        """서비스 초기화.

        Args:
            retriever: 검색기 인스턴스
            reranker: 리랭커 인스턴스
        """
        self.retriever = retriever
        self.reranker = reranker
        self.intent_extractor = IntentExtractor()
        self.explanation_generator = ExplanationGenerator()

    def process_query(self, query: str, top_k: int = 10) -> Dict[str, Any]:
        """쿼리 처리 파이프라인.

        Args:
            query: 사용자 쿼리
            top_k: 반환할 결과 수

        Returns:
            처리 결과
        """
        # M1: 의도 추출
        intent = self.intent_extractor.extract_intent(query)

        # 검색
        retrieved = self.retriever.retrieve(query, top_k=top_k*2)

        # 리랭킹
        reranked = self.reranker.rerank(query, retrieved, top_k=top_k)

        # M4: 설명 생성
        explanation = self.explanation_generator.generate_explanation(query, reranked)

        return {
            "intent": intent,
            "results": reranked,
            "explanation": explanation
        }