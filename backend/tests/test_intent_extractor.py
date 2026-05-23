# -*- coding: utf-8 -*-
# ============================================================
# tests/test_intent_extractor.py
#
# 변경 이력:
#   v0.1 - 최초 작성
#   v0.2 - [FIX] pytest-asyncio 설정 방식 변경
#           pyproject.toml 에 asyncio_mode = "auto" 추가로
#           @pytest.mark.asyncio 데코레이터 없이도 동작
# ============================================================
"""
M1 의도 추출 모듈 테스트

실행 방법:
    cd backend
    pip install pytest pytest-asyncio
    pytest tests/test_intent_extractor.py -v

CLOVA API 를 실제로 호출하지 않고 mock 으로 대체하므로
API 키 없이도 테스트할 수 있습니다.
"""
import pytest
from unittest.mock import AsyncMock, patch

from app.modules.llm.intent_extractor import (
    _fallback_intent,
    _validate_and_build,
    extract_intent,
    is_rag_required,
    needs_clarification,
)
from app.schemas.chat import IntentType


# ── _validate_and_build 단위 테스트 (LLM 호출 없음) ──────────

class TestValidateAndBuild:
    def test_book_recommendation(self):
        """정상적인 book_recommendation 응답 파싱"""
        raw = {
            "intent_type": "book_recommendation",
            "search_query": "SF 소설 추천",
            "filters": {"genre": "SF"},
            "confidence": 0.9,
        }
        intent = _validate_and_build(raw)
        assert intent.intent_type == IntentType.book_recommendation
        assert intent.search_query == "SF 소설 추천"
        assert intent.filters["genre"] == "SF"
        assert intent.confidence == 0.9

    def test_unknown_intent_type_falls_back(self):
        """알 수 없는 intent_type 은 clarification_needed 로 처리"""
        raw = {"intent_type": "invalid_type", "confidence": 0.8}
        intent = _validate_and_build(raw)
        assert intent.intent_type == IntentType.clarification_needed

    def test_low_confidence_forces_clarification(self):
        """신뢰도 0.6 미만이면 clarification_needed 강제"""
        raw = {"intent_type": "book_recommendation", "confidence": 0.4}
        intent = _validate_and_build(raw)
        assert intent.intent_type == IntentType.clarification_needed

    def test_low_confidence_does_not_affect_general_chat(self):
        """general_chat 은 신뢰도 낮아도 clarification 으로 바뀌지 않음"""
        raw = {"intent_type": "general_chat", "confidence": 0.3}
        intent = _validate_and_build(raw)
        assert intent.intent_type == IntentType.general_chat

    def test_confidence_clipping_above(self):
        """confidence 가 1.0 초과이면 1.0 으로 클리핑"""
        raw = {"intent_type": "general_chat", "confidence": 99.9}
        intent = _validate_and_build(raw)
        assert intent.confidence == 1.0

    def test_confidence_as_string(self):
        """[FIX v0.3] confidence 가 문자열로 오더라도 파싱"""
        raw = {"intent_type": "general_chat", "confidence": "0.85"}
        intent = _validate_and_build(raw)
        assert intent.confidence == 0.85


# ── needs_clarification / is_rag_required 테스트 ─────────────

class TestHelperFunctions:
    def test_needs_clarification_true(self):
        intent = _validate_and_build(
            {"intent_type": "clarification_needed", "confidence": 0.9}
        )
        assert needs_clarification(intent) is True

    def test_needs_clarification_false(self):
        intent = _validate_and_build(
            {"intent_type": "book_recommendation", "confidence": 0.9}
        )
        assert needs_clarification(intent) is False

    def test_rag_required_for_recommendation(self):
        intent = _validate_and_build(
            {"intent_type": "book_recommendation", "confidence": 0.9}
        )
        assert is_rag_required(intent) is True

    def test_rag_required_for_book_info(self):
        intent = _validate_and_build(
            {"intent_type": "book_info", "confidence": 0.9}
        )
        assert is_rag_required(intent) is True

    def test_rag_not_required_for_general(self):
        intent = _validate_and_build(
            {"intent_type": "general_chat", "confidence": 0.9}
        )
        assert is_rag_required(intent) is False


# ── extract_intent 통합 테스트 (LLM mock) ────────────────────

class TestExtractIntent:
    @pytest.mark.asyncio
    @patch(
        "app.modules.llm.intent_extractor.chat_complete_json",
        new_callable=AsyncMock,
    )
    async def test_book_recommendation_intent(self, mock_llm):
        """LLM 이 book_recommendation 반환 시 올바르게 파싱"""
        mock_llm.return_value = {
            "intent_type": "book_recommendation",
            "search_query": "힐링 에세이 추천",
            "filters": {"mood": "힐링", "genre": "에세이"},
            "confidence": 0.95,
        }
        intent = await extract_intent(
            query="요즘 지쳐서 힐링되는 에세이 읽고 싶어",
            history=[],
        )
        assert intent.intent_type == IntentType.book_recommendation
        assert intent.search_query == "힐링 에세이 추천"
        assert intent.filters["mood"] == "힐링"

    @pytest.mark.asyncio
    @patch(
        "app.modules.llm.intent_extractor.chat_complete_json",
        new_callable=AsyncMock,
        side_effect=Exception("파싱 오류"),
    )
    async def test_parse_error_returns_fallback(self, mock_llm):
        """[FIX v0.2] 파싱 오류 시 LLMCallError 전파 아닌 폴백 반환"""
        intent = await extract_intent(query="뭔가", history=[])
        assert intent.intent_type == IntentType.clarification_needed
        assert intent.confidence == 0.0
