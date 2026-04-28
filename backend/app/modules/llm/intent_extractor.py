# -*- coding: utf-8 -*-
# ============================================================
# app/modules/llm/intent_extractor.py
#
# 변경 이력:
#   v0.1 - 최초 작성
#   v0.2 - [FIX] IntentParseError 발생 시 LLMCallError 로 잘못 전파되던 버그 수정
#           (기존: except IntentParseError 가 except Exception 에 흡수됨)
#   v0.3 - [FIX] _validate_and_build 에서 confidence 가 문자열로 올 경우 처리 추가
# ============================================================
"""
M1 모듈: 의도 추출기 (Intent Extractor)

역할:
    사용자의 자연어 질의를 받아
    1) 무엇을 원하는지 (intent_type) 분류
    2) 추가 질문이 필요한지 판단
    3) RAG 검색에 넘길 정제 쿼리 생성

설계 원칙:
    - FastAPI Request/Response 를 전혀 모름 → 단독 테스트 가능
    - LLM 호출은 clova_client 에 위임 → 교체 용이
    - 분류 결과 검증은 _validate_and_build 에서 방어적으로 처리

공개 함수:
    extract_intent      : 메인 진입점
    needs_clarification : 추가 질문 필요 여부 판단
    is_rag_required     : RAG 검색 필요 여부 판단
"""
import logging
from typing import Any

from app.core.exceptions import IntentParseError, LLMCallError
from app.modules.llm.clova_client import chat_complete_json
from app.modules.llm.prompts import INTENT_SYSTEM_PROMPT, build_intent_messages
from app.schemas.chat import ExtractedIntent, IntentType

logger = logging.getLogger(__name__)

# 신뢰도가 이 값 미만이면 clarification_needed 로 강제 처리
CONFIDENCE_THRESHOLD = 0.6

# RAG 검색이 필요한 의도 유형 집합
_RAG_REQUIRED_TYPES = {
    IntentType.book_recommendation,
    IntentType.book_info,
}

# 추가 질문이 필요한 의도 유형 집합
_CLARIFICATION_TYPES = {IntentType.clarification_needed}


async def extract_intent(
    query: str,
    history: list[dict[str, Any]],
    user_profile: dict[str, Any] | None = None,
) -> ExtractedIntent:
    """
    사용자 질의에서 의도를 추출합니다.

    Args:
        query       : 현재 사용자 발화 문자열
        history     : 이전 대화 목록 [{"role": "user"|"assistant", "content": str}]
        user_profile: 온보딩에서 파악한 사용자 선호 정보 (없어도 됨)

    Returns:
        ExtractedIntent 인스턴스

    Raises:
        LLMCallError: CLOVA API 호출 실패 (상위로 전파)
    """
    messages = build_intent_messages(query, history, user_profile)

    try:
        raw_json = await chat_complete_json(
            system_prompt=INTENT_SYSTEM_PROMPT,
            messages=messages,
            temperature=0.2,   # 낮게 → 분류 일관성 높임
            max_tokens=300,    # 의도 분류용 JSON 은 짧아도 충분
        )
    except LLMCallError:
        # API 호출 실패는 상위(서비스 레이어)로 전파
        raise

    except IntentParseError:
        # [FIX v0.2] JSON 파싱 실패는 폴백 처리 (LLMCallError 로 전파하지 않음)
        logger.warning(
            "의도 분류 JSON 파싱 실패 (query='%s'). 폴백 처리합니다.", query[:50]
        )
        return _fallback_intent()

    except Exception as e:
        # 예상치 못한 오류 — 폴백 처리 후 로그 기록
        logger.error("의도 추출 중 예상치 못한 오류: %s", e, exc_info=True)
        return _fallback_intent()

    return _validate_and_build(raw_json)


def _validate_and_build(raw: dict) -> ExtractedIntent:
    """
    LLM 이 반환한 딕셔너리를 검증하고 ExtractedIntent 로 변환합니다.

    LLM 은 가끔 잘못된 값을 반환할 수 있으므로 모든 필드를 방어적으로 처리합니다.

    검증 항목:
        - intent_type: 알 수 없는 값 → clarification_needed
        - confidence : 문자열로 올 경우 float 변환, 0~1 범위 클리핑
        - 신뢰도 낮음: clarification_needed 강제 (general_chat 제외)
    """
    # intent_type 검증
    raw_type = raw.get("intent_type", "clarification_needed")
    try:
        intent_type = IntentType(raw_type)
    except ValueError:
        logger.warning("알 수 없는 intent_type '%s' → clarification_needed 처리", raw_type)
        intent_type = IntentType.clarification_needed

    # [FIX v0.3] confidence 가 문자열로 올 경우 float 변환
    try:
        confidence = float(raw.get("confidence", 1.0))
    except (TypeError, ValueError):
        logger.warning("confidence 파싱 실패, 기본값 1.0 사용")
        confidence = 1.0
    confidence = max(0.0, min(1.0, confidence))  # 0~1 클리핑

    # 신뢰도 낮으면 clarification 으로 강제 변환 (general_chat 은 제외)
    if confidence < CONFIDENCE_THRESHOLD and intent_type != IntentType.general_chat:
        logger.info(
            "신뢰도 낮음 (%.2f < %.2f) → clarification_needed 강제 처리",
            confidence,
            CONFIDENCE_THRESHOLD,
        )
        intent_type = IntentType.clarification_needed

    return ExtractedIntent(
        intent_type=intent_type,
        search_query=raw.get("search_query"),
        clarification_question=raw.get("clarification_question"),
        filters=raw.get("filters") or {},
        confidence=confidence,
    )


def _fallback_intent() -> ExtractedIntent:
    """파싱 실패 등 예외 상황에서 사용하는 안전한 기본 응답"""
    return ExtractedIntent(
        intent_type=IntentType.clarification_needed,
        clarification_question=(
            "죄송해요, 말씀하신 내용을 정확히 이해하지 못했어요. "
            "어떤 종류의 책을 찾고 계신가요?"
        ),
        confidence=0.0,
    )


def needs_clarification(intent: ExtractedIntent) -> bool:
    """
    추가 질문이 필요한 의도인지 판단합니다.

    if/else 대신 함수로 만드는 이유:
        조건이 바뀌어도 서비스 레이어는 수정 불필요.
    """
    return intent.intent_type in _CLARIFICATION_TYPES


def is_rag_required(intent: ExtractedIntent) -> bool:
    """RAG 검색이 필요한 의도인지 판단합니다."""
    return intent.intent_type in _RAG_REQUIRED_TYPES
