# -*- coding: utf-8 -*-
# ============================================================
# app/modules/signal/detector.py
#
# 변경 이력:
#   v0.1 - 최초 작성
#          카테고리 1~9 Kiwi 형태소 분석 기반 신호 감지
#          importance/uncertainty 계산 + 카테고리 교차 규칙 적용
#   v0.2 - [FIX] CAT8 레퍼런스 신호: "처럼"/"만큼"은 Kiwi에서 JX(보조사)로 분리되어
#          NNG 매칭 불가 → _COMPARISON_SUFFIX_PATTERN 정규식으로 별도 감지 추가
# ============================================================
"""
Signal Detector: 쿼리에서 신호를 감지하고 슬롯별 importance/uncertainty를 계산

역할:
    filler.py의 extract_slots() 앞 단계에서 호출됨.
    LLM에게 넘기기 전에 휴리스틱으로 쿼리 특성을 미리 파악해서
    LLM 프롬프트에 importance 힌트를 제공.

처리 흐름:
    쿼리 텍스트
    → Kiwi 형태소 분석 (_extract_features)
    → 카테고리 1~9 신호 감지 (_detect_categories)
    → importance/uncertainty 계산 (_compute_scores)
    → 교차 규칙 적용 (_apply_cross_rules)
    → SignalResult 반환

SlotScores 구조:
    각 슬롯에 importance(HIGH/MEDIUM/LOW) + uncertainty(HIGH/MEDIUM/LOW) 부여.
    - importance: 이 슬롯이 추천 결과에 미치는 영향도. 높을수록 RAG에서 강하게 반영.
    - uncertainty: 슬롯이 비어있을 때 채워야 할 필요성. 높을수록 세션 질문 우선순위 올라감.

한계:
    CAT8 (레퍼런스 신호): 책 제목/작가명을 휴리스틱으로 잡기 어려움.
    유사도 표현("같은", "비슷한")은 감지하지만 anchor 존재 여부는 LLM이 판단.
    행정구역명(성북구, 마포구 등)은 정규식으로 감지.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from kiwipiepy import Kiwi

from app.modules.signal.expressions import (
    CAT1_NEGATIVE, CAT1_POSITIVE, CAT1_RECOVERY,
    CAT2_LEARN, CAT2_COMFORT, CAT2_FUN, CAT2_PRACTICAL,
    CAT3_SHORT, CAT3_LONG,
    CAT4_EASY, CAT4_HARD,
    CAT5_FORMAT, CAT5_TOPIC, CAT5_LEISURE,
    CAT6_AVAIL,
    CAT7_LOCATION,
    CAT8_REFERENCE,
    CAT9_AVOID,
)

# Kiwi 인스턴스 — 모듈 로드 시 한 번만 생성 (재사용으로 성능 향상)
_kiwi = Kiwi()

# 복합명사 사용자 사전 등록
# Kiwi가 여러 형태소로 쪼개는 단어들을 통합 명사로 처리
_COMPOUND_NOUNS = [
    "자기계발서",
    "그래픽노블",
    "라이트노벨",
    "추리소설",
    "로맨스소설",
    "역사소설",
    "과학책",
    "인문서",
    "역사서",
]
for _word in _COMPOUND_NOUNS:
    _kiwi.add_user_word(_word, "NNG")

# 행정구역 감지용 정규식 (카테고리 7 location 보조)
_GU_PATTERN = re.compile(r'[가-힣]{2,4}[구군시]')

# [FIX] CAT8 보조 정규식 — "처럼", "만큼"은 JX(보조사)라 Kiwi NNG 매칭 불가
# 2글자 이상 한글/영문자가 선행하는 경우만 감지 (단독 "처럼/만큼" 제외)
_COMPARISON_SUFFIX_PATTERN = re.compile(
    r'[가-힣a-zA-Z0-9]{2,}(?:처럼|만큼)',
    re.UNICODE,
)


# ── 수치 정의 ─────────────────────────────────────────────────

class Level(str, Enum):
    HIGH   = "high"
    MEDIUM = "medium"
    LOW    = "low"


# ── 슬롯별 importance/uncertainty ────────────────────────────

@dataclass
class SlotScore:
    importance : Level = Level.LOW
    uncertainty: Level = Level.HIGH


@dataclass
class SlotScores:
    """슬롯별 importance/uncertainty 점수"""
    topic            : SlotScore = field(default_factory=SlotScore)
    purpose          : SlotScore = field(default_factory=SlotScore)
    mood             : SlotScore = field(default_factory=SlotScore)
    difficulty       : SlotScore = field(default_factory=SlotScore)
    format           : SlotScore = field(default_factory=SlotScore)
    length           : SlotScore = field(default_factory=SlotScore)
    location         : SlotScore = field(default_factory=SlotScore)
    comparison_basis : SlotScore = field(default_factory=SlotScore)
    avoid_mood       : SlotScore = field(default_factory=SlotScore)


# ── 감지된 카테고리 ───────────────────────────────────────────

@dataclass
class DetectedCategories:
    cat1_negative : bool = False
    cat1_positive : bool = False
    cat1_recovery : bool = False
    cat2_learn    : bool = False
    cat2_comfort  : bool = False
    cat2_fun      : bool = False
    cat2_practical: bool = False
    cat3_short    : bool = False
    cat3_long     : bool = False
    cat4_easy     : bool = False
    cat4_hard     : bool = False
    cat5_format   : bool = False
    cat5_leisure  : bool = False  # 소설/에세이/만화/시집 등 레저 형식
    cat5_topic    : bool = False
    cat6_avail    : bool = False
    cat7_location : bool = False
    cat8_reference: bool = False
    cat9_avoid    : bool = False


# ── 감지 결과 컨테이너 ────────────────────────────────────────

@dataclass
class SignalResult:
    """
    detect() 반환값

    categories         : 감지된 카테고리 플래그
    scores             : 슬롯별 importance/uncertainty
    needs_llm_fallback : 아무 카테고리도 감지 안 됐을 때 True
                         → filler.py에서 LLM에게 importance 계산도 맡김
    """
    categories        : DetectedCategories
    scores            : SlotScores
    needs_llm_fallback: bool = False


# ── 형태소 분석 특징 추출 ─────────────────────────────────────

@dataclass
class _Features:
    verb_stems : set[str]         # 동사/형용사 어간
    noun_tokens: set[str]         # 명사
    noun_set   : set[str]         # noun_pairs 매칭용 (순서 무관)
    raw        : str              # 원문 (일부 패턴은 원문 정규식으로 처리)


def _extract_features(query: str) -> _Features:
    """
    Kiwi로 형태소 분석 후 매칭에 필요한 특징 추출

    주의사항:
        - "가볍다" 같은 불규칙 형용사는 VA-I 태그로 분리됨 → 별도 처리
        - "같은", "비슷한"은 형용사(VA) 어간이지만
          noun_pairs 매칭에서 "같은" 전체 문자열을 쓰므로 noun_tokens에도 추가
    """
    tokens = _kiwi.tokenize(query)

    verb_stems  = set()
    noun_tokens = set()

    for token in tokens:
        tag = token.tag
        # VV: 동사, VA: 형용사, VA-I: 불규칙 형용사, XR: 어근
        if tag in ("VV", "VA", "VA-I", "XR"):
            verb_stems.add(token.form)
        # NNG: 일반명사, NNP: 고유명사, NNB: 의존명사
        elif tag in ("NNG", "NNP", "NNB"):
            noun_tokens.add(token.form)

    # "같은", "비슷한"은 형용사 어간(같/비슷)으로 분리되지만
    # noun_pairs에서 ("같은", "책") 형태로 정의하므로
    # 원문에 해당 패턴이 있으면 noun_tokens에 문자열 추가
    if "같" in verb_stems and "같은" in query:
        noun_tokens.add("같은")
    if "비슷" in verb_stems and "비슷한" in query:
        noun_tokens.add("비슷한")

    return _Features(
        verb_stems  = verb_stems,
        noun_tokens = noun_tokens,
        noun_set    = noun_tokens,
        raw         = query,
    )


def _match(features: _Features, pattern_dict: dict) -> bool:
    """
    표현 목록과 형태소 분석 결과를 매칭

    verb_stems : 어간 집합 교집합
    noun_tokens: 명사 집합 교집합
    noun_pairs : 두 명사가 모두 있으면 감지
    """
    stems  = pattern_dict.get("verb_stems", set())
    nouns  = pattern_dict.get("noun_tokens", set())
    pairs  = pattern_dict.get("noun_pairs", set())

    if stems & features.verb_stems:
        return True
    if nouns & features.noun_tokens:
        return True
    for n1, n2 in pairs:
        if n1 in features.noun_set and n2 in features.noun_set:
            return True
    return False


# ── 카테고리 감지 ─────────────────────────────────────────────

def _detect_categories(features: _Features, query: str) -> DetectedCategories:
    cats = DetectedCategories()

    cats.cat1_negative  = _match(features, CAT1_NEGATIVE)
    cats.cat1_positive  = _match(features, CAT1_POSITIVE)
    cats.cat1_recovery  = _match(features, CAT1_RECOVERY)
    cats.cat2_learn     = _match(features, CAT2_LEARN)
    cats.cat2_comfort   = _match(features, CAT2_COMFORT)
    cats.cat2_fun       = _match(features, CAT2_FUN)
    cats.cat2_practical = _match(features, CAT2_PRACTICAL)
    cats.cat3_short     = _match(features, CAT3_SHORT)
    cats.cat3_long      = _match(features, CAT3_LONG)
    cats.cat4_easy      = _match(features, CAT4_EASY)
    cats.cat4_hard      = _match(features, CAT4_HARD)
    cats.cat5_format    = _match(features, CAT5_FORMAT)
    cats.cat5_leisure   = _match(features, CAT5_LEISURE)
    cats.cat5_topic     = _match(features, CAT5_TOPIC)
    cats.cat6_avail     = _match(features, CAT6_AVAIL)
    # [FIX] CAT8: Kiwi 기반 매칭 + "처럼"/"만큼" 정규식 보완
    # "처럼"/"만큼"은 JX(보조사)라 _match()의 NNG 매칭에 걸리지 않음
    # → _COMPARISON_SUFFIX_PATTERN 정규식으로 별도 감지
    cats.cat8_reference = (
        _match(features, CAT8_REFERENCE)
        or bool(_COMPARISON_SUFFIX_PATTERN.search(query))
    )
    cats.cat9_avoid     = _match(features, CAT9_AVOID)

    # 카테고리 7: 명사 매칭 + 행정구역 정규식
    cats.cat7_location = (
        _match(features, CAT7_LOCATION)
        or bool(_GU_PATTERN.search(query))
    )

    return cats


# ── importance/uncertainty 계산 ───────────────────────────────

# Level 우선순위 — 숫자가 높을수록 강한 신호
_LEVEL_ORDER = {Level.LOW: 0, Level.MEDIUM: 1, Level.HIGH: 2}


def _max_level(a: Level, b: Level) -> Level:
    """
    두 Level 중 더 높은 것을 반환.

    카테고리 처리 순서와 관계없이 한 번 높아진 값은 낮아지지 않도록 보장.
    의도적인 값 조정은 _apply_cross_rules()에서만 허용.
    """
    return a if _LEVEL_ORDER[a] >= _LEVEL_ORDER[b] else b


def _set(score: SlotScore, importance: Level = None, uncertainty: Level = None) -> None:
    """
    SlotScore에 max 방식으로 importance/uncertainty 설정.
    현재 값보다 낮은 값은 무시.
    """
    if importance is not None:
        score.importance = _max_level(score.importance, importance)
    if uncertainty is not None:
        score.uncertainty = _max_level(score.uncertainty, uncertainty)


def _compute_scores(cats: DetectedCategories) -> SlotScores:
    """
    감지된 카테고리 조합으로 슬롯별 importance 계산.

    변경: uncertainty는 이 함수에서 다루지 않음.
    기본값 HIGH를 유지하고, LOW 확정은 _apply_cross_rules()에서만 처리.
    _set()은 max 방식이라 HIGH를 LOW로 낮출 수 없음 — importance만 올림.
    """
    s = SlotScores()

    # ── 카테고리 1: 정서/상태 신호 ───────────────────────────
    if cats.cat1_negative:
        _set(s.mood,       importance=Level.HIGH)
        _set(s.purpose,    importance=Level.HIGH)
        _set(s.difficulty, importance=Level.MEDIUM)
        _set(s.topic,      importance=Level.LOW)

    if cats.cat1_recovery:
        _set(s.mood,       importance=Level.HIGH)
        _set(s.purpose,    importance=Level.HIGH)
        _set(s.difficulty, importance=Level.MEDIUM)

    if cats.cat1_positive:
        _set(s.mood,       importance=Level.HIGH)
        _set(s.difficulty, importance=Level.MEDIUM)

    # ── 카테고리 2: 목적 신호 ─────────────────────────────────
    if cats.cat2_learn:
        _set(s.purpose,    importance=Level.HIGH)
        _set(s.topic,      importance=Level.HIGH)
        _set(s.difficulty, importance=Level.LOW)

    if cats.cat2_comfort:
        _set(s.purpose,    importance=Level.HIGH)
        _set(s.difficulty, importance=Level.MEDIUM)
        _set(s.format,     importance=Level.MEDIUM)

    if cats.cat2_fun:
        _set(s.purpose,    importance=Level.HIGH)
        _set(s.difficulty, importance=Level.MEDIUM)

    if cats.cat2_practical:
        _set(s.purpose,    importance=Level.HIGH)
        _set(s.topic,      importance=Level.HIGH)
        _set(s.format,     importance=Level.MEDIUM)
        _set(s.difficulty, importance=Level.MEDIUM)

    # ── 카테고리 3: 분량 신호 ─────────────────────────────────
    if cats.cat3_short or cats.cat3_long:
        _set(s.length, importance=Level.HIGH)

    # ── 카테고리 4: 난이도 신호 ───────────────────────────────
    if cats.cat4_easy or cats.cat4_hard:
        _set(s.difficulty, importance=Level.HIGH)

    # ── 카테고리 5: 형식/주제 신호 ───────────────────────────
    if cats.cat5_format:
        _set(s.format, importance=Level.HIGH)

    if cats.cat5_topic:
        _set(s.topic, importance=Level.HIGH)

    # ── 카테고리 6: availability 신호 ────────────────────────
    if cats.cat6_avail:
        _set(s.location, importance=Level.HIGH)
        _set(s.topic,    importance=Level.MEDIUM)
        _set(s.purpose,  importance=Level.MEDIUM)

    # ── 카테고리 7: location 신호 ─────────────────────────────
    if cats.cat7_location:
        _set(s.location, importance=Level.HIGH)

    # ── 카테고리 8: 레퍼런스 신호 ────────────────────────────
    if cats.cat8_reference:
        _set(s.comparison_basis, importance=Level.HIGH)

    # ── 카테고리 9: 부정/회피 신호 ───────────────────────────
    if cats.cat9_avoid:
        _set(s.avoid_mood, importance=Level.HIGH)

    if cats.cat1_negative or cats.cat1_recovery:
        _set(s.avoid_mood, importance=Level.MEDIUM)

    return s


def _apply_cross_rules(cats: DetectedCategories, scores: SlotScores) -> SlotScores:
    """
    uncertainty LOW 확정 + 카테고리 교차 규칙.

    _compute_scores()는 importance만 올림(단조증가).
    uncertainty를 LOW로 낮추는 작업은 전부 여기서 직접 대입으로 처리.

    규칙 1: 카테고리별 uncertainty LOW 확정
    규칙 2: CAT1 × CAT2 교차
    규칙 3: CAT8 단독 감지 시 importance 조정
    """
    # ── 규칙 1: 카테고리별 uncertainty LOW 확정 ─────────────────

    # CAT1: 정서 감지 → mood 방향 확정
    if cats.cat1_negative or cats.cat1_recovery or cats.cat1_positive:
        scores.mood.uncertainty = Level.LOW

    # CAT1_POSITIVE: difficulty 확정 (긍정 정서 → 온보딩 fallback OK)
    if cats.cat1_positive:
        scores.difficulty.uncertainty = Level.LOW

    # CAT2_LEARN: 목적 확정, 난이도는 불확실 유지
    # "공부" 목적이 확정돼도 입문인지 심화인지 알 수 없음 → difficulty HIGH
    if cats.cat2_learn:
        scores.purpose.uncertainty = Level.LOW

    # CAT2_COMFORT: 목적 확정 (위로), difficulty는 불확실 (HIGH 유지)
    if cats.cat2_comfort:
        scores.purpose.uncertainty = Level.LOW

    # CAT2_FUN: 목적 확정, 난이도는 어느 정도 가볍겠지만 LOW로 단정하긴 어려움 → MEDIUM
    if cats.cat2_fun:
        scores.purpose.uncertainty    = Level.LOW
        scores.difficulty.uncertainty = Level.LOW  # 재미 목적이면 대체로 easy/medium 방향

    # CAT2_PRACTICAL: 목적 확정, 난이도 불확실
    # 입문 실용서 ~ 전문 실용서 스펙트럼이 넓음 → difficulty HIGH 유지
    if cats.cat2_practical:
        scores.purpose.uncertainty = Level.LOW

    # CAT3: 분량 확정
    if cats.cat3_short or cats.cat3_long:
        scores.length.uncertainty = Level.LOW

    # CAT4: 난이도 확정
    if cats.cat4_easy or cats.cat4_hard:
        scores.difficulty.uncertainty = Level.LOW

    # CAT5_TOPIC: 주제 확정
    # cat5_format은 topic 확정 안 함 — LLM이 topic.fine으로 채우므로
    if cats.cat5_topic:
        scores.topic.uncertainty = Level.LOW

    # CAT5_LEISURE: 레저 형식(소설/에세이/만화 등) → purpose 방향 확정
    # 이 형식들은 목적이 '재미'로 수렴 → purpose 질문 생략
    if cats.cat5_leisure:
        scores.purpose.uncertainty = Level.LOW

    # CAT7: 위치 확정 (cat6 단독이면 HIGH 유지, cat7 감지되면 LOW)
    if cats.cat7_location:
        scores.location.uncertainty = Level.LOW

    # CAT9: 회피 확정
    if cats.cat9_avoid:
        scores.avoid_mood.uncertainty = Level.LOW

    # ── 규칙 2: CAT1 × CAT2 교차 ─────────────────────────────
    any_cat1 = cats.cat1_negative or cats.cat1_recovery

    if any_cat1:
        if cats.cat2_learn or cats.cat2_fun or cats.cat2_practical:
            scores.difficulty.uncertainty = Level.LOW
        if cats.cat2_learn or cats.cat2_practical:
            scores.mood.importance = Level.LOW

    # ── 규칙 3: CAT8 단독 → importance LOW ───────────────────
    any_other_topic_signal   = cats.cat2_learn or cats.cat2_practical or cats.cat5_topic
    any_other_purpose_signal = (
        cats.cat2_learn or cats.cat2_comfort or cats.cat2_fun or cats.cat2_practical
    )

    if cats.cat8_reference:
        if not any_other_topic_signal:
            scores.topic.importance = Level.LOW
        if not any_other_purpose_signal:
            scores.purpose.importance = Level.LOW
        if not (cats.cat4_easy or cats.cat4_hard):
            scores.difficulty.importance = Level.LOW
        if not cats.cat5_format:
            scores.format.importance = Level.LOW

    return scores


def detect(query: str) -> SignalResult:
    """
    쿼리에서 신호를 감지하고 슬롯별 importance/uncertainty를 계산합니다.

    filler.py의 extract_slots()에서 LLM 호출 전에 실행됨.
    결과는 LLM 프롬프트에 importance 힌트로 전달됨.

    Args:
        query: 사용자 입력 쿼리 원문

    Returns:
        SignalResult
            .categories        : 감지된 카테고리 플래그
            .scores            : 슬롯별 importance/uncertainty
            .needs_llm_fallback: 아무 카테고리도 감지 안 됐으면 True
    """
    features = _extract_features(query)
    cats     = _detect_categories(features, query)
    scores   = _compute_scores(cats)
    scores   = _apply_cross_rules(cats, scores)

    any_detected = any([
        cats.cat1_negative, cats.cat1_positive, cats.cat1_recovery,
        cats.cat2_learn, cats.cat2_comfort, cats.cat2_fun, cats.cat2_practical,
        cats.cat3_short, cats.cat3_long,
        cats.cat4_easy, cats.cat4_hard,
        cats.cat5_format, cats.cat5_leisure, cats.cat5_topic,
        cats.cat6_avail, cats.cat7_location,
        cats.cat8_reference, cats.cat9_avoid,
    ])

    return SignalResult(
        categories         = cats,
        scores             = scores,
        needs_llm_fallback = not any_detected,
    )
