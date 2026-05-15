"""Compatibility shim — 기존 import 경로 유지용.

새 코드는 아래 모듈에서 직접 import하세요:
  app.prompts.extraction        — slot 값 추출 프롬프트
  app.prompts.clarification     — clarification 판단 프롬프트
  app.prompts.rag               — RAG 쿼리 생성 프롬프트
  app.prompts.question_generation — 질문 생성 프롬프트
"""

from app.prompts.extraction import (
    SLOT_EXTRACTION_SYSTEM_PROMPT,
    build_slot_extraction_messages,
    _build_signal_hint,
)
from app.prompts.clarification import (
    CLARIFICATION_JUDGMENT_PROMPT,
    build_clarification_messages,
)
from app.prompts.rag import RAG_QUERY_GENERATION_PROMPT
from app.prompts.question_generation import build_question_generation_messages

__all__ = [
    "SLOT_EXTRACTION_SYSTEM_PROMPT",
    "CLARIFICATION_JUDGMENT_PROMPT",
    "RAG_QUERY_GENERATION_PROMPT",
    "build_slot_extraction_messages",
    "build_clarification_messages",
    "build_question_generation_messages",
    "_build_signal_hint",
]
