"""Compatibility exports for intent prompt helpers.

New code should import from ``app.prompts.intent``.
"""

from app.prompts.intent import INTENT_SYSTEM_PROMPT, build_intent_messages

__all__ = [
    "INTENT_SYSTEM_PROMPT",
    "build_intent_messages",
]

