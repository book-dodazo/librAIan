"""Compatibility exports for slot prompt helpers.

New code should import from ``app.prompts.slot``.
"""

from app.prompts.slot import (
    RAG_QUERY_GENERATION_PROMPT,
    SLOT_EXTRACTION_SYSTEM_PROMPT,
    build_question_generation_messages,
    build_slot_extraction_messages,
)

__all__ = [
    "RAG_QUERY_GENERATION_PROMPT",
    "SLOT_EXTRACTION_SYSTEM_PROMPT",
    "build_question_generation_messages",
    "build_slot_extraction_messages",
]

