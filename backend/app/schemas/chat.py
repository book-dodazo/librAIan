# -*- coding: utf-8 -*-
# ============================================================
# app/schemas/chat.py
#
# 변경 이력:
#   v0.1 - 최초 작성
#   v0.2 - [FIX] pydantic v2 문법으로 통일
#           class Config → model_config 방식은 여기선 불필요,
#           그냥 BaseModel 그대로 사용
# ============================================================
"""
API 입출력 검증용 Pydantic 스키마 (DTO)

DTO(Data Transfer Object): 계층 간 데이터를 주고받는 계약서 역할.
타입이 맞지 않으면 FastAPI가 422 에러를 자동으로 반환합니다.

파일 구조:
    요청 스키마: MessageRole, ConversationMessage, ChatRequest
    응답 스키마: IntentType, ExtractedIntent, ChatResponse
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ── 요청 스키마 ───────────────────────────────────────────────

class MessageRole(str, Enum):
    """대화 메시지의 발화자 구분"""
    user = "user"
    assistant = "assistant"
    system = "system"


class ConversationMessage(BaseModel):
    """대화 히스토리 한 턴"""
    role: MessageRole
    content: str


class ChatRequest(BaseModel):
    """
    POST /api/chat 요청 바디

    필드:
        query       : 현재 사용자 발화 (필수)
        history     : 이전 대화 내역, 첫 턴이면 빈 리스트
        user_profile: 온보딩에서 파악한 사용자 선호 (없어도 됨)

    예시:
        {
            "query": "SF 소설 추천해줘",
            "history": [],
            "user_profile": {"preferred_genres": ["SF"]}
        }
    """
    query: str = Field(..., min_length=1, max_length=2000, description="사용자 질의")
    history: list[ConversationMessage] = Field(default_factory=list)
    user_profile: Optional[dict[str, Any]] = Field(default=None)


# ── 응답 스키마 ───────────────────────────────────────────────

class IntentType(str, Enum):
    """
    M1(의도 추출) 모듈이 분류하는 의도 유형

    book_recommendation : 책 추천 요청 → RAG 검색으로 넘김
    book_info           : 특정 책/저자 정보 문의 → RAG 검색으로 넘김
    general_chat        : 일반 대화 (인사, 잡담 등)
    clarification_needed: 의도 불분명 → 추가 질문 필요
    """
    book_recommendation  = "book_recommendation"
    book_info            = "book_info"
    general_chat         = "general_chat"
    clarification_needed = "clarification_needed"


class ExtractedIntent(BaseModel):
    """
    M1 모듈 출력: 의도 분류 결과

    필드:
        intent_type           : 분류된 의도 유형
        search_query          : RAG 검색에 넘길 정제 쿼리 (RAG 불필요 시 None)
        clarification_question: 추가 질문 문장 (clarification_needed 일 때만)
        filters               : 추출된 선호 조건 (장르, 분위기 등)
        confidence            : LLM 분류 신뢰도 (0.0 ~ 1.0)
    """
    intent_type: IntentType
    search_query: Optional[str] = None
    clarification_question: Optional[str] = None
    filters: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class ChatResponse(BaseModel):
    """
    POST /api/chat 응답 바디

    프론트엔드 분기 로직:
        needs_clarification=True  → clarification_question 을 사용자에게 표시
        ready_for_rag=True        → search_query 를 검색 엔진에 전달
        둘 다 False               → message 를 그대로 표시 (일반 대화)

    필드:
        needs_clarification  : 추가 질문 필요 여부
        clarification_question: 사용자에게 보여줄 추가 질문
        intent               : 파악된 의도 정보 (디버깅·로깅용)
        message              : 사용자에게 바로 보여줄 텍스트
        ready_for_rag        : RAG 검색 준비 완료 여부
        search_query         : RAG 에 넘길 검색 쿼리
    """
    needs_clarification: bool
    clarification_question: Optional[str] = None
    intent: ExtractedIntent
    message: str
    ready_for_rag: bool
    search_query: Optional[str] = None
