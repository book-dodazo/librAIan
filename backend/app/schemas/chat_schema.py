# -*- coding: utf-8 -*-
# ============================================================
# app/schemas/chat.py
#
# 변경 이력:
#   v0.1 - 최초 작성
#   v0.2 - [FIX] pydantic v2 문법으로 통일
#   v0.3 - slot 기반 파이프라인으로 전면 변경
#          SlotChatResponse 추가, 멀티턴 컨텍스트 필드 추가
# ============================================================
"""
API 입출력 스키마 (DTO)

변경 사항 (v0.3):
    - ChatRequest: context, selected_choice, pending_slots 필드 추가
    - SlotChatResponse: slot 기반 응답 구조로 변경
      - clarification_choices: 선택지 목록
      - pending_slots        : 이 질문이 채우려는 slot 목록
      - rag_query            : RAG 검색 쿼리 객체
      - context              : 다음 턴에 넘길 컨텍스트
      - filled_slots         : 현재까지 채워진 slot 목록
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ── 공통 ─────────────────────────────────────────────────────

class MessageRole(str, Enum):
    user      = "user"
    assistant = "assistant"
    system    = "system"


class ConversationMessage(BaseModel):
    role   : MessageRole
    content: str


# ── 요청 ─────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    """
    POST /api/chat 요청 바디

    멀티턴 필드:
        context        : 이전 턴에서 받은 컨텍스트 (첫 턴은 null)
        selected_choice: 사용자가 선택한 선택지 (버튼 선택 시)
        pending_slots  : 선택지 질문이 채우려던 slot 목록

    예시 (첫 턴):
        {"query": "SF 소설 추천해줘", "history": [], "context": null}

    예시 (선택지 응답):
        {
            "query": "재미있게 읽고 싶어요",
            "history": [...],
            "context": {...},
            "selected_choice": {"label": "재미있게", "slots": {"purpose": "재미"}},
            "pending_slots": ["purpose"]
        }
    """
    query          : str = Field(..., min_length=1, max_length=2000)
    history        : list[ConversationMessage]  = Field(default_factory=list)
    user_profile   : Optional[dict[str, Any]]   = Field(default=None)

    # 멀티턴 관련
    context        : Optional[dict[str, Any]]   = Field(default=None)
    selected_choice: Optional[dict[str, Any]]   = Field(default=None)
    pending_slots  : Optional[list[str]]        = Field(default=None)


# ── 응답 ─────────────────────────────────────────────────────

class SlotChatResponse(BaseModel):
    """
    POST /api/chat 응답 바디

    프론트엔드 분기 로직:
        needs_clarification=True
            → clarification_question 표시
            → clarification_choices 버튼으로 렌더링
            → 사용자 선택 후 selected_choice + pending_slots 담아서 재요청

        ready_for_rag=True
            → rag_query를 검색 엔진에 전달
            → 검색 결과를 다음 단계로

        둘 다 False
            → message 그대로 표시 (에러 또는 일반 응답)

    멀티턴:
        매 응답마다 context를 저장해두었다가
        다음 요청 시 ChatRequest.context로 전달
    """
    needs_clarification   : bool
    ready_for_rag         : bool
    message               : str

    # 추가 질문 관련
    clarification_question: Optional[str]           = None
    clarification_choices : Optional[list[dict]]    = None
    pending_slots         : Optional[list[str]]     = None

    # RAG 쿼리
    rag_query             : Optional[dict[str, Any]]= None

    # 멀티턴 컨텍스트 (프론트에서 보관 후 다음 턴에 전달)
    context               : Optional[dict[str, Any]]= None

    # 디버깅용
    filled_slots          : list[str]               = Field(default_factory=list)
    error                 : Optional[str]           = None
