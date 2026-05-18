# -*- coding: utf-8 -*-
# ============================================================
# app/modules/slot/schema.py
#
# 변경 이력:
#   v0.1 - 최초 작성
#          P1~P5 토론 결과 기반 slot 스키마 정의
#          source 기반 신뢰도, priority_conditions 기반 우선순위
#   v0.2 - MoodCategory, MoodSlot 추가 (조건부 slot)
#          ComparisonDimension, ComparisonBasisSlot 추가 (예외 slot)
#          arousal-valence 2차원 + KOTE 43 감정 분류 참고
#          SlotState에 두 슬롯 통합
# ============================================================
"""
Slot 스키마 정의

핵심 용어:
    slot   : 추천을 만들기 위해 시스템이 채워야 하는 정보 칸
    anchor : 질의에 포함된 직접 조회 가능한 고정 기준점 (slot 아님)
    source : direct/inferred/ambiguous/null — 슬롯 값의 추출 근거 등급

현재 구현된 슬롯 구조:
    핵심 slot      : topic, purpose, reading_level
                     항상 활성. 비어있으면 세션 질문 또는 온보딩 fallback.
    조건부 slot    : mood
                     카테고리 1 (정서/상태) 신호 감지 시 활성화.
                     자유 발화에서 LLM이 추출. 세션 질문으로 직접 묻지 않음.
    예외 slot      : comparison_basis
                     anchor + 유사도 표현 동시 감지 시에만 활성화.
                     비교 기준이 드러나지 않으면 세션 질문으로 채움.
    제약 slot      : constraints 리스트
                     page_range, pub_year, availability, author 등 개별 항목.
    플래그         : availability_required (도서관 API 처리용)
    파싱 결과      : anchor (slot 아님, 세션 질문 대상 아님)

미구현 슬롯 (설계 기준서에 정의돼 있으나 현재 코드에 없음):
    format, location, avoid_mood, length
    → 향후 확장 시 이 파일에 추가

MoodSlot 설계 근거:
    arousal-valence 2차원 모델 (Korean Emotion Lexicon, 한국심리학회 기반 868개 감정 단어)
    + KOTE 43개 감정 레이블 (한국어 온라인 댓글 5만 개 기반)
    + 독서 동기 연구:
        The Reading Agency (2024) — 이완/현실도피/학습
        PLOS ONE (2022) — 완화/회복/활기
        Koopman (2015) — 의미만들기 욕구
        Lazarus & Folkman — 문제/감정 중심 대처 전략

ComparisonBasisSlot 설계 근거:
    설계 기준서 §4-2 비교 기준 slot
    세션 질문 보기: 분위기 / 주제 / 문체 / 난이도 / 생각할 거리 / 직접 입력
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


# ── Mood Slot ─────────────────────────────────────────────────

class MoodCategory(str, Enum):
    """
    감정/상태 분류 (조건부 slot — 카테고리 1 신호 감지 시 활성화)

    설계 근거:
        arousal(각성도) × valence(긍부정) 2차원 모델
        (Korean Emotion Lexicon, 한국심리학회 기반 868개 감정 단어)
        + KOTE 43개 감정 레이블 중 독서 맥락 관련 필터링
        + 독서 동기 연구 (The Reading Agency 2024, PLOS ONE 2022,
          Koopman 2015, Lazarus & Folkman 대처 이론)

    ── low arousal / negative valence (지침/소진 계열) ──────────
    부정_소진     : 지쳐서, 번아웃, 피곤해서, 녹초, 탈진
    부정_우울     : 우울해서, 슬플 때, 눈물날 것 같을 때
    부정_무기력   : 의욕없어서, 멍할 때, 아무것도 하기 싫을 때
    부정_공허     : 공허할 때, 허탈할 때, 텅 빈 느낌

    ── high arousal / negative valence (긴장/분노 계열) ─────────
    부정_불안     : 불안해서, 두려워서, 걱정돼서, 초조할 때
    부정_분노     : 화나서, 억울해서, 짜증날 때, 열받았을 때
    부정_압박     : 스트레스받아서, 바빠서, 여유없어서, 숨막혀서
                    (KOTE 추가 — 한국 직장인/학생 쿼리 빈도 높음)

    ── 회복/위로 욕구 계열 (arousal 무관, 방향 명시) ────────────
    arousal 무관이지만 독서 동기 연구에서 명확히 구분되는 욕구들.
    같은 "지쳐서"라도 아래 중 어느 방향이냐에 따라
    추천 책의 유형(난이도·형식)이 크게 달라짐.

    회복_위로     : 위로가 필요해, 마음이 힘들어, 공감받고 싶어
    회복_이완     : 쉬고 싶어, 여유가 필요해, 숨 쉬고 싶어
                    → The Reading Agency — 이완(Relaxation)
    회복_도피     : 현실 도피하고 싶어, 잠깐 잊고 싶어, 빠져들고 싶어
                    → The Reading Agency — 현실도피(Escapism)
    회복_의미     : 내 상황을 이해하고 싶어, 왜 그런지 알고 싶어
                    → Koopman (2015) — 의미만들기(meaning-making)
                    → Lazarus & Folkman — 문제 중심 대처

    ── low arousal / positive valence (여유/평온 계열) ──────────
    긍정_여유     : 여유로운, 평온한, 기분 좋은, 홀가분한
    긍정_그리움   : 그리운, 옛날 생각나는, 감성적인 기분
                    (KOTE 추가 — 긍부정 경계지만 한국어 독서 맥락 빈도 높음)

    ── high arousal / positive valence (설렘/활기 계열) ─────────
    긍정_설렘     : 설레는, 신나는, 두근거리는, 기대되는
    긍정_활기     : 활기찬, 의욕 넘치는, 에너지 넘치는
                    → PLOS ONE (2022) — 활기(invigoration)
    """
    # low arousal / negative valence
    부정_소진    = "negative_exhausted"
    부정_우울    = "negative_depressed"
    부정_무기력  = "negative_passive"
    부정_공허    = "negative_empty"

    # high arousal / negative valence
    부정_불안    = "negative_anxious"
    부정_분노    = "negative_angry"
    부정_압박    = "negative_stressed"

    # 회복/위로 욕구 계열
    회복_위로    = "recovery_comfort"
    회복_이완    = "recovery_relax"
    회복_도피    = "recovery_escape"
    회복_의미    = "recovery_meaning"

    # low arousal / positive valence
    긍정_여유    = "positive_relaxed"
    긍정_그리움  = "positive_nostalgic"

    # high arousal / positive valence
    긍정_설렘    = "positive_excited"
    긍정_활기    = "positive_energized"


class MoodSlot(BaseModel):
    """
    감정/상태 slot (조건부 slot)

    활성화 조건:
        카테고리 1 (정서/상태) 신호가 자유 발화에서 감지될 때.
        세션 질문으로 직접 묻지 않음 — LLM 추출 전용.

    필드:
        categories : MoodCategory 목록 — 복합 감정 지원 ("불안하고 우울한" → 2개)
        raw        : 원문 표현 보존 ("지쳐서", "번아웃 직전이라" 등)
        source     : 추출 근거 등급

    null_cases (이런 경우 mood로 추출하지 않음):
        "위로가 되는 책"  → mood 아님, purpose 슬롯으로 처리
        "따뜻한 책"       → mood 아님, comparison_basis 또는 constraints로 처리
        "가벼운 책"       → mood 아님, reading_level = easy로 처리

    RAG 활용 (현재 구현):
        categories 값이 rag_query_builder로 전달되어
        semantic_query 생성 시 감정 맥락으로 반영됨.
    """
    categories: list[MoodCategory] = Field(default_factory=list)
    raw       : Optional[str]      = None
    source    : SlotSource         = SlotSource.null

    def is_filled(self) -> bool:
        return bool(self.categories) and self.source != SlotSource.null

    def is_negative(self) -> bool:
        """부정 정서 계열 여부 (부정_* + 회복_* 포함)"""
        return any(
            c.value.startswith("negative_") or c.value.startswith("recovery_")
            for c in self.categories
        )

    def is_positive(self) -> bool:
        """긍정 정서 계열 여부"""
        return any(c.value.startswith("positive_") for c in self.categories)


# ── Comparison Basis Slot ─────────────────────────────────────

class ComparisonDimension(str, Enum):
    """
    비교 기준 축 (예외 slot — 카테고리 8 감지 시 활성화)

    설계 기준서 §4-2 세션 질문 보기:
        "그 책에서 어떤 점이 특히 좋으셨나요?
         분위기 / 주제 / 문체 / 쉽게 읽히는 점 /
         생각할 거리 / 직접 입력"

    RAG 활용:
        분위기  → 분위기 태그 기반 유사도 검색
        주제    → 주제 벡터 기반 유사도 검색
        문체    → 문체 태그 기반 유사도 검색
        난이도  → reading_level 필터 기반 검색
        깊이    → score_boost에 difficulty 반영
        custom  → semantic_query에 자유형으로 포함
    """
    분위기 = "mood"       # 따뜻한, 어두운 등 전반적 분위기
    주제   = "topic"      # 비슷한 주제/소재
    문체   = "style"      # 문장 스타일, 호흡, 필체
    난이도 = "difficulty" # 쉽게 읽히는 점 (읽기 부담)
    깊이   = "depth"      # 생각할 거리, 여운
    custom = "custom"     # 직접 입력


class ComparisonBasisSlot(BaseModel):
    """
    비교 기준 slot (예외 slot)

    활성화 조건:
        anchor (책 제목/저자명/시리즈명) + 유사도 표현("같은", "비슷한" 등)
        이 동시에 감지될 때만 활성화됨.
        anchor 없이 유사도 표현만 있으면 활성화하지 않음.
        예: "비슷한 분위기 책" → anchor 없으므로 미활성

    필드:
        dimensions : 비교 기준 축 목록 (복수 가능)
                     예: "불편한 편의점처럼 따뜻하고 읽기 쉬운 책"
                         → [ComparisonDimension.분위기, ComparisonDimension.난이도]
        raw        : custom 선택 시 원문, 또는 dimensions 보완용 원문
        source     : 추출 근거 등급

    채워지는 경로:
        1. LLM 추출 — 쿼리에서 비교 기준이 직접 드러날 때
           예: "불편한 편의점처럼 따뜻한 책" → dimensions=[분위기], source=direct
        2. 세션 질문 버튼 선택 — 비교 기준이 드러나지 않을 때
           예: "불편한 편의점 같은 책" → dimensions 비어있음 → 세션 질문
           → apply_choice()에서 comparison_basis_dim 키로 채워짐

    null_cases:
        "불편한 편의점 같은 책"
            → anchor=불편한 편의점, dimensions 비어있음
            → is_filled()=False → 세션 질문 발동
        "불편한 편의점처럼 따뜻한 책"
            → anchor=불편한 편의점, dimensions=[분위기]
            → is_filled()=True → 세션 질문 불필요
    """
    dimensions: list[ComparisonDimension] = Field(default_factory=list)
    raw       : Optional[str]             = None
    source    : SlotSource                = SlotSource.null

    def is_filled(self) -> bool:
        return bool(self.dimensions) or bool(self.raw)


# ── Location Slot ─────────────────────────────────────────────

class LocationSlot(BaseModel):
    """
    지역/도서관 slot (조건부 slot)

    활성화 조건:
        카테고리 6 (availability) 또는 카테고리 7 (location) 감지 시 활성화.

    채워지는 경로:
        1. 쿼리에서 직접 언급 ("성북구", "마포구립서강도서관")
           → source=direct, uncertainty LOW → 세션 질문 불필요

        2. 카테고리 6 트리거 + 온보딩 region 없음
           → source=null, uncertainty HIGH → 세션 질문
             "어느 지역 기준으로 찾아드릴까요? / 직접 입력"

        3. 카테고리 6 트리거 + 온보딩 region 있음
           → source=null, uncertainty MEDIUM → 확인 질문
             "오늘은 어느 지역 기준으로 찾으실까요?
              온보딩 지역 1 / 온보딩 지역 2 / 다른 지역 입력"

    필드:
        region  : 지역명 (예: "성북구", "서울 마포구")
        library : 도서관명 (예: "마포구립서강도서관")
                  region과 library 중 하나 이상 있으면 filled
        source  : 추출 근거 등급

    RAG 활용:
        availability_required=True일 때 정보나루 API 대출가능 조회에 사용
        rag_query의 session_signals["location"]으로 전달
    """
    region  : Optional[str] = None
    library : Optional[str] = None
    source  : SlotSource    = SlotSource.null

    def is_filled(self) -> bool:
        return bool(self.region) or bool(self.library)


# ── AvoidMood Slot ────────────────────────────────────────────

class AvoidMoodSlot(BaseModel):
    """
    피하고 싶은 분위기 slot (조건부 slot)

    활성화 조건:
        카테고리 9 (부정/회피 신호) 직접 감지 시,
        또는 카테고리 1 (부정 정서) 트리거 시 조건부 활성화.

    채워지는 경로:
        1. 직접 언급 ("너무 무거운 건 싫어", "잔인한 건 빼줘")
           → source=direct, importance HIGH, uncertainty LOW
           → 세션값이 온보딩 덮어씀

        2. 온보딩 disliked_keywords가 있고 세션과 충돌 없을 때
           → rag_query_builder에서 보조 신호로 전달
           → 충돌 판단: 세션 topic/purpose가 회피 태그와 연관되면 온보딩 비활성
             예: "전쟁 역사책" + 온보딩 "너무 잔인한" → 충돌 → 온보딩 비활성

    필드:
        keywords: 회피 태그 목록 (복수 가능)
                  예: ["너무 무거운", "너무 잔인한"]
        source  : 추출 근거 등급

    RAG 활용:
        직접 언급 → session_signals["disliked"]로 전달 (Reranker 강한 신호)
        온보딩    → onboarding_signals["disliked_keywords"]로 전달 (충돌 없을 때만)
    """
    keywords: list[str] = Field(default_factory=list)
    source  : SlotSource = SlotSource.null

    def is_filled(self) -> bool:
        return bool(self.keywords)


# ── Length Slot ───────────────────────────────────────────────

class LengthLevel(str, Enum):
    """
    분량 수준 (체감 단서 기반 — 상대적 소프트 신호)

    page_range (constraints)와의 차이:
        page_range : "300페이지 이하" 같은 수치 제약 → 하드 필터
        length     : "짧은", "가볍게" 같은 체감 단서 → 소프트 신호

    절대 기준 아님 — 독자마다 "짧은"의 기준이 다르므로 Reranker가 맥락 보정.
    """
    short  = "short"   # 짧은, 가볍게, 금방 읽히는
    medium = "medium"  # 적당한, 보통 분량
    long   = "long"    # 두꺼운, 묵직한, 장편


class LengthSlot(BaseModel):
    """
    분량 slot (예외 slot)

    활성화 조건:
        1. 직접 단서 ("짧은", "가볍게")
           → importance HIGH, uncertainty LOW

        2. 정서형 쿼리 (CAT1 감지 + length 단서)
           → importance MEDIUM, uncertainty HIGH
           → 짧은 쪽으로 고정하지 않음 (방향 B 확정)
           → 이전 세션 논의: "정서형이면 짧은 책이 정답이라고 단정할 수 없음"

        3. refinement에서 분량 요청 ("더 짧은 걸로")
           → importance HIGH, uncertainty LOW

        조건 없음:
           → length 슬롯 비활성
           → 온보딩 preferred_length를 RAG에서 약한 보정 신호로만 사용

    필드:
        level : LengthLevel Enum ("short" / "long")
        source: 추출 근거 등급

    RAG 활용:
        session_signals["length"]로 전달
        조건 없을 때 온보딩 preferred_length → onboarding_signals["reading_level"]에 반영
    """
    level : Optional[LengthLevel] = None
    source: SlotSource             = SlotSource.null

    def is_filled(self) -> bool:
        return self.level is not None and self.source != SlotSource.null


# ── Constraint ────────────────────────────────────────────────

class ConstraintOperator(str, Enum):
    """제약 조건 연산자"""
    eq      = "eq"      # 같음
    gte     = "gte"     # 이상
    lte     = "lte"     # 이하
    gt      = "gt"      # 초과
    lt      = "lt"      # 미만
    exclude = "exclude" # 제외
    around  = "around"  # 내외/정도 (소프트 범위)


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

    슬롯 유형:
        핵심 slot      : topic, purpose, reading_level
                         항상 활성. 비어있으면 세션 질문 또는 온보딩 fallback.
        조건부 slot    : mood, comparison_basis, location, avoid_mood
                         특정 신호 감지 시만 활성화.
        예외 slot      : length
                         분량 단서 직접 있거나 refinement 요청 시 활성화.
        제약 slot      : constraints 리스트
        플래그         : availability_required

    미구현 슬롯 (설계 기준서에 정의돼 있으나 현재 코드에 없음):
        format → topic 안에서 LLM 추출로 처리 결정
    """
    # 핵심 slot
    topic        : TopicSlot   = Field(default_factory=TopicSlot)
    purpose      : SlotValue   = Field(default_factory=SlotValue)
    reading_level: SlotValue   = Field(default_factory=SlotValue)

    # 조건부 slot — 카테고리 신호 감지 시 활성화
    mood             : MoodSlot             = Field(default_factory=MoodSlot)
    comparison_basis : ComparisonBasisSlot  = Field(default_factory=ComparisonBasisSlot)
    location         : LocationSlot         = Field(default_factory=LocationSlot)
    avoid_mood       : AvoidMoodSlot        = Field(default_factory=AvoidMoodSlot)

    # 예외 slot — 분량 단서 직접 있거나 refinement 요청 시 활성화
    length           : LengthSlot           = Field(default_factory=LengthSlot)

    # 제약 slot
    constraints  : list[Constraint] = Field(default_factory=list)

    # availability 플래그 (도서관 API 처리용)
    availability_required: bool = False

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
        if self.comparison_basis.is_filled():
            filled.append("comparison_basis")
        if self.location.is_filled():
            filled.append("location")
        if self.avoid_mood.is_filled():
            filled.append("avoid_mood")
        if self.length.is_filled():
            filled.append("length")
        return filled

    def get_empty_core_slots(self) -> list[str]:
        """비어있는 핵심 slot 이름 목록 반환 (mood, comparison_basis는 조건부라 제외)
        reading_level은 여기서 제외 — LLM이 needs_reading_level_clarification 플래그로 필요 여부 판단
        """
        empty = []
        if not self.topic.is_filled():
            empty.append("topic")
        if not self.purpose.is_filled():
            empty.append("purpose")
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
        세션 질문     → slot_importance로 질문 여부 결정
    """
    # 원본 질의 (첫 턴)
    original_query: str

    # 질의 파싱 결과 (slot 아님) — 복수 anchor 지원
    anchors       : list[Anchor]        = Field(default_factory=list)

    # slot 상태
    slots         : SlotState           = Field(default_factory=SlotState)

    # 대화 히스토리 (멀티턴)
    turn_count    : int                 = 0
    asked_slots   : list[str]           = Field(default_factory=list)  # 이미 질문한 slot

    # signal 모듈에서 계산한 슬롯별 importance
    # 형태: {"topic": "high", "purpose": "medium", "reading_level": "low", ...}
    # get_slots_to_ask()에서 우선순위 결정에 사용
    # 높을수록 추천 결과에 미치는 영향이 크다는 의미
    slot_importance : dict[str, str]     = Field(default_factory=dict)

    # signal 모듈에서 계산한 슬롯별 uncertainty
    # 형태: {"topic": "high", "purpose": "high", "reading_level": "low", ...}
    # get_slots_to_ask()에서 세션 질문 여부 결정에 사용
    # HIGH = 방향 불명확 → 세션 질문 필요
    # LOW  = 방향 명확   → 세션 질문 생략, 온보딩 fallback 또는 LLM inferred 사용
    slot_uncertainty: dict[str, str]     = Field(default_factory=dict)

    # 온보딩 데이터 (user_metadata.json에서 로드)
    # 데모: user_metadata.json에서 user_id로 조회
    # 실서비스: DB에서 user_id로 조회 후 여기에 저장
    # rag_query_builder.py에서 uncertainty HIGH 슬롯에 한해 보조 신호로 사용
    onboarding      : Optional[dict]     = None

    # RAG 쿼리 (slot 충분히 채워지면 생성)
    rag_query     : Optional[dict]      = None

    # Refinement 전용
    previous_result     : Optional[list] = None
    modification_request: Optional[str]  = None

    # ── LLM holistic sufficiency judgment (매 턴 업데이트) ────────
    # extract_slots() → Call 2에서 채워짐

    # RAG 바로 진행 가능 여부 (LLM 판단)
    rag_ready_from_llm  : bool            = False

    # LLM이 제안한 다음 질문 슬롯 목록
    # 가능한 값: "topic_subject", "purpose_detail", "reading_level",
    #            "comparison_basis", "location"
    llm_slots_to_ask    : list[str]       = Field(default_factory=list)

    # 이미 채워진 슬롯 중 수정/보완이 필요한 것
    # 형태: {"topic": {"action": "narrow", "hint": "소설 장르가 너무 넓음"}}
    slot_revision_hints : dict            = Field(default_factory=dict)

    # LLM 판단 근거 (디버깅/로깅용)
    llm_reasoning       : Optional[str]   = None

    # LLM 충분도 판단 신뢰도 (0~100)
    # confidence < 70 + rag_ready=true → filler.py에서 false로 override
    llm_confidence      : int             = 100

    # ── 하위 호환 플래그 (llm_slots_to_ask에서 자동 파생) ─────
    needs_subject_clarification     : bool = False
    needs_purpose_clarification     : bool = False
    needs_reading_level_clarification: bool = False

    # 개인화 체크인 턴 완료 여부 (대분류 요청 시 mood 체크인 — 한 세션에 한 번)
    personalization_turn_done: bool = False
