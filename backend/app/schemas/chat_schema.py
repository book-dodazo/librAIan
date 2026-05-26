# -*- coding: utf-8 -*-
# ============================================================
# app/schemas/chat_schema.py
#
# 변경 이력:
#   v0.1 - 최초 작성
#   v0.2 - [FIX] pydantic v2 문법으로 통일
#   v0.3 - slot 기반 파이프라인으로 전면 변경
#   v0.4 - inferred 확인 턴 추가
#          SlotChatResponse: is_confirmation, inferred_summary 필드 추가
#          ChatRequest: confirm_inferred 필드 추가
# ============================================================
from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class MessageRole(str, Enum):
    user      = "user"
    assistant = "assistant"
    system    = "system"


class ConversationMessage(BaseModel):
    role   : MessageRole
    content: str


class ChatRequest(BaseModel):
    """
    POST /api/chat 요청 바디

    멀티턴 필드:
        context         : 이전 턴 컨텍스트 (첫 턴은 null)
        selected_choice : 선택지 응답 (버튼 선택 시)
        pending_slots   : 선택지가 채우려던 slot 목록
        confirm_inferred: inferred 확인 턴 응답
            True  → 파악 내용 맞음, RAG로 진행
            False → 수정하겠음 (pending_slots 에 수정할 slot 목록)
    """
    query           : str = Field(..., min_length=1, max_length=2000)
    history         : list[ConversationMessage] = Field(default_factory=list)
    user_profile    : Optional[dict[str, Any]]  = Field(default=None)

    # 멀티턴
    context         : Optional[dict[str, Any]]  = Field(default=None)
    selected_choice : Optional[dict[str, Any]]  = Field(default=None)
    pending_slots   : Optional[list[str]]       = Field(default=None)

    # inferred 확인 턴
    confirm_inferred: Optional[bool]            = Field(default=None)

    # 세션 ID (이전 대화 이어가기)
    session_id      : Optional[int]             = Field(default=None)



class SlotChatResponse(BaseModel):
    """
    POST /api/chat 응답 바디

    프론트엔드 분기 로직:
        is_confirmation=True
            → inferred_summary 를 확인 카드로 렌더링
            → "맞아요" → confirm_inferred=True 로 재요청
            → "수정" → confirm_inferred=False + pending_slots 로 재요청

        needs_clarification=True
            → clarification_choices 버튼으로 렌더링

        ready_for_rag=True
            → rag_query 를 검색 엔진에 전달
    """
    needs_clarification   : bool
    ready_for_rag         : bool
    message               : str

    # inferred 확인 턴
    is_confirmation       : bool                    = False
    inferred_summary      : Optional[list[dict]]    = None  # [{"slot": "purpose", "value": "실용", "label": "목적"}]

    # 추가 질문
    clarification_question: Optional[str]           = None
    clarification_choices : Optional[list[dict]]    = None
    pending_slots         : Optional[list[str]]     = None

    # RAG
    rag_query             : Optional[dict[str, Any]]= None

    # 멀티턴 컨텍스트
    context               : Optional[dict[str, Any]]= None

    # 검색 결과 (BM25 + Reranking 완료 후 채워짐)
    # 형태: [{"rank": 1, "isbn": "...", "score": 1.23}, ...]
    search_results        : Optional[list[dict]]    = None

    # 대출 가능 여부 조회 결과
    # 형태: {"isbn": {"has_book": "Y", "loan_available": "Y"}, ...}
    availability_index    : Optional[dict[str, Any]]= None

    # 세션
    session_id            : Optional[int]           = None

    # 디버깅
    filled_slots          : list[str]               = Field(default_factory=list)
    error                 : Optional[str]           = None
