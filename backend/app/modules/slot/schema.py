# -*- coding: utf-8 -*-
# ============================================================
# app/modules/slot/schema.py
#
# 변경 이력:
#   v0.1 - 최초 작성
#          P1~P5 토론 결과 기반 slot 스키마 정의
#          source 기반 신뢰도, priority_conditions 기반 우선순위
# ============================================================
"""
Slot 스키마 정의

토론 결과 요약:
    - slot = 추천을 만들기 위해 시스템이 채워야 하는 정보 칸
    - anchor = 질의 파싱 결과 (slot 아님)
    - source = direct/inferred/ambiguous/null (신뢰도 등급)
    - priority_conditions = 채워진 slot 패턴 기반 우선순위

데모 구현 범위:
    핵심 slot : topic, purpose, reading_level
    조건부 slot: mood
    제약 slot  : constraints (availability 포함)
    파싱 결과  : anchor
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ── Source 등급 ───────────────────────────────────────────────

class SlotSource(str, Enum):
    """
    slot 값의 추출 근거 등급 (P2 결론)

    direct   : 질의에 직접 명시 → 채워진 것으로 판단
    inferred : 문맥으로 추론 가능 → slot 중요도에 따라 조건부 판단
    ambiguous: 해석이 여러 개 가능 → 질문 생성
    null     : 언급 없음 → 필수 slot이면 질문 생성
    """
    direct    = "direct"
    inferred  = "inferred"
    ambiguous = "ambiguous"
    null      = "null"


# ── Slot 값 래퍼 ──────────────────────────────────────────────

class SlotValue(BaseModel):
    """
    slot 값과 추출 근거를 함께 저장하는 래퍼

    예시:
        SlotValue(value="재미", source=SlotSource.direct)
        SlotValue(value=None, source=SlotSource.null)
    """
    value : Optional[Any]        = None
    source: SlotSource           = SlotSource.null

    def is_filled(self) -> bool:
        """채워진 slot인지 판단"""
        return self.value is not None and self.source != SlotSource.null

    def is_reliable(self) -> bool:
        """
        RAG에 쓸만한 신뢰도인지 판단
        direct는 항상 신뢰, inferred는 조건부 신뢰
        """
        return self.source in (SlotSource.direct, SlotSource.inferred)


# ── Topic Slot ────────────────────────────────────────────────

class TopicSlot(BaseModel):
    """
    주제 slot (P5 토론 결과)

    coarse : 대분류 리스트 (category_tree.json key) → RAG 메타데이터 필터
    fine   : 중분류 리스트 (category_tree.json value) → RAG score_boost
    subject: 세부 주제 리스트 (자유형) → Dense 쿼리에 포함
    source : 추출 근거 등급

    여러 주제가 동시에 언급될 수 있으므로 전부 리스트로 관리합니다.

    예시:
        "심리학이랑 철학 책 추천해줘"
        → coarse=["인문"], fine=["심리학", "철학"], subject=[]

        "SF랑 추리소설 추천해줘"
        → coarse=["과학/기술", "소설"], fine=["SF", "장르소설"], subject=[]

        "한국 근현대사 책 추천해줘"
        → coarse=["역사/문화"], fine=["한국사"], subject=["한국 근현대사"]
    """
    coarse : list[str]  = Field(default_factory=list)  # 대분류 리스트
    fine   : list[str]  = Field(default_factory=list)  # 중분류 리스트
    subject: list[str]  = Field(default_factory=list)  # 세부 주제 리스트
    source : SlotSource = SlotSource.null

    def is_filled(self) -> bool:
        return any([self.coarse, self.fine, self.subject])


# ── Purpose Slot ──────────────────────────────────────────────

class PurposeValue(str, Enum):
    """목적 slot 가능한 값 (P5 확정)"""
    학습 = "학습"
    교양 = "교양"
    재미 = "재미"
    실용 = "실용"


# ── Reading Level Slot ────────────────────────────────────────

class ReadingLevelValue(str, Enum):
    """읽기 부담 slot 가능한 값 (P5 확정)"""
    easy   = "easy"    # 가볍고 쉽게 읽히는
    medium = "medium"  # 적당히 생각할 거리
    hard   = "hard"    # 깊이 있는


# ── Constraint ────────────────────────────────────────────────

class ConstraintOperator(str, Enum):
    """제약 조건 연산자"""
    eq  = "eq"   # 같음
    gte = "gte"  # 이상
    lte = "lte"  # 이하
    gt  = "gt"   # 초과
    lt  = "lt"   # 미만
    exclude = "exclude"  # 제외


class Constraint(BaseModel):
    """
    제약 조건 단일 항목 (P6 토론 결과)

    type    : 제약 종류 (page_range, pub_year, availability, custom 등)
    value   : 제약 값
    operator: 연산자 (규칙 레이어가 결정)
    raw     : 원문 보존 (디버깅용)

    예시:
        {"type": "page_range", "value": 300, "operator": "lte", "raw": "300페이지 이하"}
        {"type": "availability", "value": True, "operator": "eq", "raw": "지금 바로"}
        {"type": "custom", "value": "번역서 제외", "operator": None, "raw": "번역서 제외"}
    """
    type    : str
    value   : Any
    operator: Optional[ConstraintOperator] = None
    raw     : Optional[str]               = None


# ── Anchor ────────────────────────────────────────────────────

class AnchorType(str, Enum):
    """anchor 유형"""
    book_title = "book_title"  # 책 제목
    author     = "author"      # 저자명
    series     = "series"      # 시리즈명
    library    = "library"     # 도서관명


class Anchor(BaseModel):
    """
    질의 파싱 결과 — slot 아님 (P5 토론 결과)

    slot과 달리 비어있어도 질문으로 채우지 않음.
    있으면 쓰고, 없으면 없는 것으로 처리.
    """
    value: str
    type : AnchorType


# ── 전체 Slot 상태 ────────────────────────────────────────────

class SlotState(BaseModel):
    """
    현재 세션의 전체 slot 상태

    컨텍스트 객체의 핵심 구성 요소.
    LLM 추출 → session question 응답 → Refinement 순으로 업데이트됨.
    """
    # 핵심 slot
    topic        : TopicSlot                    = Field(default_factory=TopicSlot)
    purpose      : SlotValue                    = Field(default_factory=SlotValue)
    reading_level: SlotValue                    = Field(default_factory=SlotValue)

    # 조건부 slot
    mood         : SlotValue                    = Field(default_factory=SlotValue)

    # 제약 slot
    constraints  : list[Constraint]             = Field(default_factory=list)

    # availability 플래그 (도서관 API 처리용)
    availability_required: bool                 = False

    def get_filled_slots(self) -> list[str]:
        """채워진 slot 이름 목록 반환"""
        filled = []
        if self.topic.is_filled():
            filled.append("topic")
        if self.purpose.is_filled():
            filled.append("purpose")
        if self.reading_level.is_filled():
            filled.append("reading_level")
        if self.mood.is_filled():
            filled.append("mood")
        return filled

    def get_empty_core_slots(self) -> list[str]:
        """비어있는 핵심 slot 이름 목록 반환"""
        empty = []
        if not self.topic.is_filled():
            empty.append("topic")
        if not self.purpose.is_filled():
            empty.append("purpose")
        if not self.reading_level.is_filled():
            empty.append("reading_level")
        return empty


# ── 컨텍스트 객체 ─────────────────────────────────────────────

class SessionContext(BaseModel):
    """
    세션 전체를 관통하는 컨텍스트 객체 (P7 토론 결과)

    생성: 첫 질의 입력 시
    업데이트: 매 턴마다 slot 채워질 때
    소멸: 최종 결과 반환 후 (Refinement 시 유지)

    파이프라인별 사용:
        slot filling  → slots 읽기/쓰기
        RAG 검색      → rag_query 사용
        도서관 API    → availability_required 사용
        Refinement    → previous_result + modification_request 사용
    """
    # 원본 질의 (첫 턴)
    original_query: str

    # 질의 파싱 결과 (slot 아님)
    anchor        : Optional[Anchor]    = None

    # slot 상태
    slots         : SlotState           = Field(default_factory=SlotState)

    # 대화 히스토리 (멀티턴)
    turn_count    : int                 = 0
    asked_slots   : list[str]           = Field(default_factory=list)  # 이미 질문한 slot

    # RAG 쿼리 (slot 충분히 채워지면 생성)
    rag_query     : Optional[dict]      = None

    # Refinement 전용
    previous_result     : Optional[list] = None
    modification_request: Optional[str]  = None
