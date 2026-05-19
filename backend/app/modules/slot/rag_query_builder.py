# -*- coding: utf-8 -*-
# ============================================================
# app/modules/slot/rag_query_builder.py
#
# 변경 이력:
#   v0.1 - 최초 작성
#          BM25 키워드 + Dense 자연어 + 메타데이터 필터
#   v0.2 - constraints 처리 개선
#   v0.3 - [FIX] 여러 버그 수정 및 TODO 추가
#   v0.4 - [FIX] A파트 BM25.py 키 이름 맞춤
#   v0.5 - session_signals / onboarding_signals 분리 추가
#          uncertainty HIGH 슬롯에 한해 온보딩 보조 신호 반영
#          RAG 쿼리에 두 신호를 각각 포함해 Reranker가 가중치 차등 적용
#   v0.6 - [FIX] _summarize_slots, _fallback_keywords mood 타입 변경 대응
#          slots.mood.value → slots.mood.raw or slots.mood.category.value
#          _summarize_slots에 avoid_mood, length 추가
#          _fallback_keywords에 avoid_mood, length 추가
#          _apply_refinement 전면 수정
#          reading_level / length / availability / avoid_mood / author 변경 모두 반영
# ============================================================
"""
RAG 쿼리 빌더

P7 결론:
    - slot 값 기반으로 쿼리 생성 (원문 발화 X)
    - LLM이 자연어 쿼리 생성 (매핑 테이블 X)
    - BM25용 keyword_query, Dense용 semantic_query, 공통 filters
    - Refinement 시 이전 쿼리에 수정 사항만 반영

RAG 파이프라인:
    BM25 검색기  → keyword_query + filters.cate_depth1
    Dense 검색기 → semantic_query + filters.cate_depth1
    Reranking    → score_boost (대분류 필터 + 중분류 스코어)
    도서관 API   → availability_required
"""
import logging
import re
from typing import Any, Optional

from app.core.exceptions import IntentParseError, LLMCallError
from app.modules.llm.clova_client import chat_complete_json
from app.prompts.rag import RAG_QUERY_GENERATION_PROMPT
from app.modules.slot.schema import SessionContext

logger = logging.getLogger(__name__)

# 대분류 수준 topic 집합 — clarification/chat_service와 동일 기준
BROAD_TOPICS = {
    "소설", "인문", "역사", "역사일반", "역사/문화",
    "컴퓨터/IT", "경제/경영", "자기계발", "과학",
    "시/에세이", "에세이", "실용",
}

# reading_level → 자연어 표현
_LEVEL_LABEL = {
    "easy"  : "가볍고 쉽게 읽히는",
    "medium": "적당한 깊이의",
    "hard"  : "깊이 있는",
}

# purpose → 자연어 표현
_PURPOSE_LABEL = {
    "학습": "공부가 되는",
    "교양": "교양을 쌓을 수 있는",
    "재미": "재미있게 읽을 수 있는",
    "실용": "실용적인",
}


async def build_rag_query(context: SessionContext) -> dict[str, Any]:
    """
    SessionContext → RAG 쿼리 객체 변환

    slot filling 완료 후 호출.
    LLM으로 keyword_query + semantic_query 생성.

    Returns:
        {
            "keyword_query"        : ["키워드1", ...],
            "semantic_query"       : "자연어 검색 쿼리",
            "filters"              : {"cate_depth1": [...], ...},
            "constraints"          : {"page_range": [...], "author_non": [...], ...},
            "score_boost"          : {"cate_depth2": [...], "subject": [...]},
            "availability_required": bool,
            "anchor"               : {"value": "...", "type": "..."} or None,
            "session_signals"      : {"purpose": ..., "mood": ..., ...},
            "onboarding_signals"   : {"topic": [...], ...},
        }
    """
    slots = context.slots

    # ── LLM으로 쿼리 생성 ─────────────────────────────────────
    slot_summary = _summarize_slots(context)

    messages = [{
        "role": "user",
        "content": (
            f"원본 질의: {context.original_query}\n\n"
            f"파악된 사용자 요구사항:\n{slot_summary}"
        )
    }]

    try:
        raw = await chat_complete_json(
            system_prompt = RAG_QUERY_GENERATION_PROMPT,
            messages      = messages,
            temperature   = 0.2,
            max_tokens    = 300,
        )
        keyword_query  = raw.get("keyword_query", [])
        semantic_query = raw.get("semantic_query", context.original_query)

    except (LLMCallError, IntentParseError) as e:
        logger.error("RAG 쿼리 생성 실패, 폴백 사용: %s", e)
        # 폴백: 원본 질의 + slot 값 키워드 조합
        keyword_query  = _fallback_keywords(context)
        semantic_query = context.original_query

    # ── 메타데이터 필터 + constraints 생성 ──────────────────────
    # _build_filters 가 {"filters": {...}, "constraints": {...}} 형태로 반환
    filter_result = _build_filters(context)
    filters     = filter_result["filters"]
    constraints = filter_result["constraints"]

    # ── score_boost 생성 ──────────────────────────────────────
    score_boost = _build_score_boost(context)

    # ── Refinement 처리 ───────────────────────────────────────
    if context.modification_request and context.previous_result:
        semantic_query = _apply_refinement(
            base_query   = context.rag_query.get("semantic_query", semantic_query)
                           if context.rag_query else semantic_query,
            modification = context.modification_request,
            slots        = slots,
        )

    rag_query = {
        "keyword_query"        : keyword_query,
        "semantic_query"       : semantic_query,
        "filters"              : filters,
        "constraints"          : constraints,
        "score_boost"          : score_boost,
        "availability_required": slots.availability_required,
        "anchors"              : _anchors_to_list(context),
        # 세션 신호: 세션에서 직접 나온 슬롯 값 (Reranker 가중치 높음)
        "session_signals"      : _build_session_signals(context),
        # 온보딩 신호: uncertainty HIGH 슬롯에 한해 온보딩 fallback (Reranker 가중치 낮음)
        "onboarding_signals"   : _build_onboarding_signals(context),
        # 슬롯 보완 힌트: narrow=해당 슬롯 방향 불확실, verify=inferred 값 재확인 필요
        # Reranker가 해당 슬롯 값에 낮은 가중치를 적용할 수 있도록 전달
        "slot_revision_hints"  : context.slot_revision_hints or {},
    }

    logger.info("RAG 쿼리 생성 완료: %s", rag_query)
    return rag_query


def _summarize_slots(context: SessionContext) -> str:
    """slot 상태를 LLM에게 넘길 자연어 요약으로 변환"""
    slots = context.slots
    lines = []

    if slots.topic.is_filled():
        topic_parts = []
        if slots.topic.coarse:
            topic_parts.append(f"대분류: {', '.join(slots.topic.coarse)}")
        if slots.topic.fine:
            topic_parts.append(f"중분류: {', '.join(slots.topic.fine)}")
        if slots.topic.subject:
            topic_parts.append(f"세부주제: {', '.join(slots.topic.subject)}")
        lines.append(f"주제 - {', '.join(topic_parts)}")

    if slots.purpose.is_filled():
        lines.append(f"목적 - {slots.purpose.value}")

    if slots.reading_level.is_filled():
        label = _LEVEL_LABEL.get(slots.reading_level.value, slots.reading_level.value)
        lines.append(f"읽기 부담 - {label}")

    if slots.mood.is_filled():
        mood_label = slots.mood.raw or ", ".join(c.value for c in slots.mood.categories)
        lines.append(f"감정/상태 - {mood_label}")

    if slots.avoid_mood.is_filled():
        lines.append(f"피하고 싶은 분위기 - {', '.join(slots.avoid_mood.keywords)}")

    if slots.length.is_filled():
        _LENGTH_LABEL = {"short": "짧은 책", "medium": "적당한 분량의 책", "long": "긴 책"}
        length_label = _LENGTH_LABEL.get(slots.length.level.value if slots.length.level else "", "")
        if length_label:
            lines.append(f"분량 - {length_label}")

    if context.onboarding and context.onboarding.get("age") is not None:
        lines.append(f"사용자 나이 - {context.onboarding['age']}세")

    for a in context.anchors:
        lines.append(f"기준 {a.type.value} - {a.value}")

    if slots.comparison_basis.is_filled():
        dims = [d.value for d in slots.comparison_basis.dimensions]
        dim_str = ", ".join(dims) if dims else ""
        raw_str = slots.comparison_basis.raw or ""
        parts = [x for x in [dim_str, raw_str] if x]
        lines.append(f"유사 기준 - {' / '.join(parts)}")

    if slots.location.is_filled():
        loc_parts = []
        if slots.location.library:
            loc_parts.append(slots.location.library)
        elif slots.location.region:
            loc_parts.append(slots.location.region)
        if loc_parts:
            lines.append(f"대출 지역/도서관 - {', '.join(loc_parts)}")

        elif c.type == "pub_year" and c.value and c.operator:
            op = {"gte": "이후", "lte": "이전", "gt": "초과", "lt": "미만"}.get(
                c.operator.value, c.operator.value
    return "\n".join(lines) if lines else "정보 없음"


def _build_filters(context: SessionContext) -> dict:
    """
    메타데이터 필터 생성

    반환 구조 (A파트 BM25.py 키 이름 기준):
        filters     : cate_depth1, target_reader, custom_constraints, anchor 관련
        constraints : author, author_non, page_range, pub_year
    """
    filters    : dict[str, Any] = {}
    constraints: dict[str, Any] = {}
    target_reader_list: list[str] = []
    slots = context.slots

    # ── filters ───────────────────────────────────────────────

    # 대분류 필터 (BM25 + Dense 공통)
    if slots.topic.is_filled() and slots.topic.coarse:
        filters["cate_depth1"] = slots.topic.coarse  # list[str]

    # anchor는 top-level rag_query["anchors"]로 전달 → filters 중복 제거
    # constraints["author"] (하드 필터)와 혼동 방지

    # custom 제약 (자연어 — 하드 필터 불가, 후처리용)
    custom_texts: list[str] = []

    # ── constraints ───────────────────────────────────────────
    # A파트 BM25.py: constraints["author"], ["author_non"], ["page_range"], ["pub_year"]

    page_range_list: list[dict] = []
    pub_year_list  : list[dict] = []
    author_list    : list[str]  = []
    nonauthor_list : list[str]  = []

    for c in slots.constraints:
        if c.type == "page_range" and c.operator and c.value:
            page_range_list.append({
                "operator": c.operator.value,
                "value"   : c.value,
            })
        elif c.type == "pub_year" and c.operator and c.value:
            pub_year_list.append({
                "operator": c.operator.value,
                "value"   : c.value,
            })
        elif c.type == "target_reader" and c.value:
            target_reader_list.append(str(c.value))
        elif c.type == "author" and c.value:
            author_list.append(str(c.value))
        elif c.type == "nonauthor" and c.value:
            nonauthor_list.append(str(c.value))
        elif c.type == "availability":
            pass  # availability_required 플래그로 별도 처리
        elif c.type == "custom" and c.value:
            custom_texts.append(str(c.raw or c.value))

    # constraints 딕셔너리 구성 (값 있을 때만)
    if target_reader_list:
        filters["target_reader"] = target_reader_list
    if page_range_list:
        constraints["page_range"]  = page_range_list
    if pub_year_list:
        constraints["pub_year"]    = pub_year_list
    if author_list:
        constraints["author"]      = author_list      # BM25.py: constraints["author"]
    if nonauthor_list:
        constraints["author_non"]  = nonauthor_list   # BM25.py: constraints["author_non"]

    # custom_constraints는 filters에 유지 (후처리용)
    if custom_texts:
        filters["custom_constraints"] = custom_texts

    return {"filters": filters, "constraints": constraints}


def _build_score_boost(context: SessionContext) -> dict:
    """Reranking용 score_boost 생성 — 리스트로 전달"""
    boost: dict[str, Any] = {}
    slots = context.slots

    if slots.topic.is_filled():
        if slots.topic.fine:
            boost["cate_depth2"] = slots.topic.fine    # list[str]
        if slots.topic.subject:
            boost["subject"] = slots.topic.subject     # list[str]

    return boost


def _fallback_keywords(context: SessionContext) -> list[str]:
    """LLM 실패 시 slot 값에서 키워드 직접 추출"""
    keywords = []
    slots = context.slots

    if slots.topic.fine:
        keywords.extend(slots.topic.fine)
    if slots.topic.subject:
        keywords.extend(slots.topic.subject)
    if slots.purpose.is_filled():
        keywords.append(str(slots.purpose.value))
    if slots.reading_level.is_filled():
        label = _LEVEL_LABEL.get(slots.reading_level.value, "")
        if label:
            keywords.append(label)
    if slots.mood.is_filled():
        mood_label = slots.mood.raw or ", ".join(c.value for c in slots.mood.categories)
        if mood_label:
            keywords.append(mood_label)
    if slots.avoid_mood.is_filled():
        keywords.extend(slots.avoid_mood.keywords)
    if slots.length.is_filled() and slots.length.level:
        _LEN_KW = {"short": "짧은", "medium": "적당한", "long": "긴"}
        keywords.append(_LEN_KW.get(slots.length.level.value, ""))

    return keywords[:7]  # 최대 7개


def _apply_refinement(
    base_query  : str,
    modification: str,
    slots       : Any,
) -> str:
    """
    Refinement 요청을 기존 쿼리에 반영합니다.

    설계 원칙: 처음부터 재생성 X, 이전 쿼리 + 수정 사항만 반영.
    수정된 슬롯 값을 앞에 붙이는 방식으로 처리.

    처리하는 수정 케이스:
        reading_level 변경: "더 쉬운 걸로" → "가볍고 쉽게 읽히는 [기존쿼리]"
        length 변경       : "더 짧은 걸로" → "짧은 [기존쿼리]"
        avoid_mood 추가   : "무거운 건 빼줘" → "[기존쿼리] (너무 무거운 제외)"
        availability      : "지금 빌릴 수 있는 걸로" → "지금 바로 빌릴 수 있는 [기존쿼리]"
        author 변경       : constraints에 포함된 author 키워드 반영
    """
    prefix_parts = []
    suffix_parts = []

    # reading_level 변경
    if slots.reading_level.is_filled():
        rl_val = slots.reading_level.value
        label  = _LEVEL_LABEL.get(
            rl_val.value if hasattr(rl_val, "value") else str(rl_val), ""
        )
        if label:
            prefix_parts.append(label)

    # length 변경
    if slots.length.is_filled() and slots.length.level:
        _LEN_KW = {"short": "짧은", "medium": "적당한 분량의", "long": "긴"}
        length_kw = _LEN_KW.get(slots.length.level.value, "")
        if length_kw:
            prefix_parts.append(length_kw)

    # availability 변경
    if slots.availability_required:
        prefix_parts.append("지금 바로 빌릴 수 있는")

    # avoid_mood 추가
    if slots.avoid_mood.is_filled():
        avoid_str = ", ".join(slots.avoid_mood.keywords)
        suffix_parts.append(f"({avoid_str} 제외)")

    # constraints author 반영
    for c in slots.constraints:
        if c.type == "author" and c.value:
            prefix_parts.append(f"{c.value} 작가의")
        elif c.type == "nonauthor" and c.value:
            suffix_parts.append(f"({c.value} 제외)")

    result = base_query
    if prefix_parts:
        result = f"{' '.join(prefix_parts)} {result}"
    if suffix_parts:
        result = f"{result} {' '.join(suffix_parts)}"

    return result.strip()


def _anchors_to_list(context: SessionContext) -> Optional[list[dict]]:
    """anchors → list[dict] 변환. topic null 시 recent_liked_books도 anchor로 포함."""
    result = [{"value": a.value, "type": a.type.value} for a in context.anchors]

    # topic null + profile override: 최근 좋아한 책을 anchor(book_title)로 추가
    if not context.slots.topic.is_filled() and context.onboarding:
        recent = context.onboarding.get("recent_liked_books") or []
        for book in recent[:5]:
            title = book.get("title") if isinstance(book, dict) else str(book)
            if title:
                result.append({"value": title, "type": "book_title"})

    return result or None


def _build_session_signals(context: SessionContext) -> dict:
    """
    세션에서 직접 나온 슬롯 값을 신호로 변환.

    Reranker에 높은 가중치로 전달됨.
    채워진 슬롯만 포함 (비어있는 슬롯은 신호 없음).

    Returns:
        {
            "purpose"         : "학습",
            "reading_level"   : "easy",
            "mood"            : "negative_exhausted",
            "location"        : {"region": "...", "library": "..."},
            "avoid_mood"      : ["너무 무거운"],
            "length"          : "short",
            "comparison_basis": {"dimensions": [...], "raw": "..."},
        }
        # 제외 항목 (중복 이유):
        #   topic     → score_boost["cate_depth2"] 와 동일
        #   anchor    → top-level rag_query["anchor"] 와 동일
        #   disliked  → constraints["author_non"] / filters["custom_constraints"] 와 동일
    """
    slots   = context.slots
    signals = {}

    # topic(fine/coarse)은 score_boost["cate_depth2"]와 중복 → 제외
    # anchor는 top-level rag_query["anchor"]와 중복 → 제외
    # nonauthor/custom disliked는 constraints["author_non"] / filters["custom_constraints"]와 중복 → 제외

    if slots.purpose.is_filled():
        val = slots.purpose.value
        signals["purpose"] = val.value if hasattr(val, "value") else str(val)

    if slots.reading_level.is_filled():
        val = slots.reading_level.value
        signals["reading_level"] = val.value if hasattr(val, "value") else str(val)

    if slots.mood.is_filled():
        signals["mood"] = [c.value for c in slots.mood.categories]

    if slots.location.is_filled():
        signals["location"] = {
            "region" : slots.location.region,
            "library": slots.location.library,
        }

    if slots.avoid_mood.is_filled():
        signals["avoid_mood"] = slots.avoid_mood.keywords

    if slots.length.is_filled():
        signals["length"] = slots.length.level.value if slots.length.level else None

    if slots.comparison_basis.is_filled():
        signals["comparison_basis"] = {
            "dimensions": [d.value for d in slots.comparison_basis.dimensions],
            "raw"       : slots.comparison_basis.raw,
        }

    return signals


def _build_onboarding_signals(context: SessionContext) -> dict:
    """
    온보딩 데이터를 보조 신호로 변환.

    사용 조건 (연구 근거 — MINICORN uncertainty 기반 접근):
        uncertainty HIGH 슬롯에 한해 온보딩 데이터를 보조 신호로 사용.
        uncertainty LOW  슬롯은 세션 신호가 충분하므로 온보딩 사용 안 함.

    Reranker에 낮은 가중치로 전달됨 (세션 신호보다 항상 낮은 우선순위).

    Returns:
        {
            "preferred_sub_categories": ["한국소설", "프랑스소설"],        # topic이 대분류일 때 프로파일 세부 선호
            "page_range_soft"         : {"operator": "lte", "value": 300}, # preferred_length 파싱 결과
            "disliked_keywords"       : ["dark", "tense"],                 # 온보딩 회피 태그
            "frequent_libraries"      : ["마포구립서강도서관"],
        }
        온보딩 없으면 빈 dict 반환
    """
    if not context.onboarding:
        return {}

    ob      = context.onboarding
    signals = {}

    # age: 독자 연령대 신호 — 연령별 추천 보정에 활용
    age = ob.get("age")
    if age is not None:
        signals["age"] = age

    # topic이 대분류 수준일 때 → 프로파일 sub-category를 약한 신호로 추가
    # "소설 추천해줘" + profile: 한국소설/프랑스소설 선호 → preferred_sub_categories 투입
    if context.slots.topic.is_filled():
        fine_set = set(context.slots.topic.fine or [])
        if fine_set and fine_set.issubset(BROAD_TOPICS):
            categories = ob.get("preferred_categories", [])
            relevant_subs = [
                c["sub"] for c in categories
                if c.get("main") in fine_set and c.get("sub")
            ]
            if relevant_subs:
                signals["preferred_sub_categories"] = relevant_subs

    # disliked_keywords: 충돌 판단 후 조건부 사용
    # 충돌 케이스: "전쟁 역사책" + 온보딩 "너무 잔인한" → 온보딩 비활성
    # 충돌 판단: 세션 topic/purpose가 회피 태그와 연관되면 온보딩 비활성
    disliked = ob.get("disliked_keywords", [])
    if disliked and not _has_avoid_mood_conflict(context, disliked):
        signals["disliked_keywords"] = disliked

    # frequent_libraries: availability 요구가 있을 때만
    if context.slots.availability_required:
        libs = ob.get("frequent_libraries", [])
        if libs:
            signals["frequent_libraries"] = libs

    # page_range_soft: 세션에서 page_range 제약이 없을 때 온보딩 preferred_length를 약한 신호로 사용
    # 숫자 그대로 전달 — short/long 변환 없이 Reranker가 맥락 보정
    has_page_constraint = any(c.type == "page_range" for c in context.slots.constraints)
    if not has_page_constraint:
        preferred_length = ob.get("preferred_length")
        page_range_soft = _parse_preferred_length(preferred_length)
        if page_range_soft:
            signals["page_range_soft"] = page_range_soft

    return signals


def _has_avoid_mood_conflict(context: SessionContext, disliked_keywords: list[str]) -> bool:
    """
    온보딩 disliked_keywords와 세션 topic/purpose 간 충돌 판단.

    충돌 케이스 예시:
        세션: "전쟁 역사책 추천해줘" + 온보딩: "너무 잔인한"
            → 전쟁 역사책은 잔인한 내용을 포함할 수 있음 → 충돌
        세션: "힐링 에세이 추천해줘" + 온보딩: "너무 잔인한"
            → 힐링 에세이는 잔인한 내용과 무관 → 충돌 없음

    현재 구현: 키워드 기반 단순 매칭
    향후: 임베딩 기반 유사도로 개선 가능

    Returns:
        True = 충돌 있음 → 온보딩 비활성
        False = 충돌 없음 → 온보딩 사용
    """
    # 충돌 가능성이 있는 주제-회피태그 조합 (한국어 + 영어 온보딩 키워드 모두 지원)
    _CONFLICT_MAP = {
        "너무 잔인한"   : ["전쟁", "역사", "범죄", "스릴러", "공포", "호러"],
        "너무 무거운"   : ["역사", "사회", "정치", "철학", "인문"],
        "너무 우울한"   : ["사회", "인문", "현실", "역사"],
        "너무 불안한"   : ["스릴러", "공포", "범죄"],
        "너무 선정적인" : ["로맨스", "성인"],
        # 영어 키워드 (user_metadata.json disliked_keywords 실제 값)
        "tense"         : ["스릴러", "공포", "범죄", "전쟁"],
        "dark"          : ["공포", "호러", "범죄"],
        "challenging"   : ["전문서", "학술"],
        "adventurous"   : [],
        "informative"   : [],
    }

    slots = context.slots
    # 세션에서 채워진 topic fine 목록
    topic_fine = slots.topic.fine if slots.topic.is_filled() else []
    topic_text = " ".join(topic_fine).lower() if topic_fine else ""

    for keyword in disliked_keywords:
        conflict_topics = _CONFLICT_MAP.get(keyword, [])
        for ct in conflict_topics:
            if ct in topic_text:
                return True

    return False


def _parse_preferred_length(preferred_length: Optional[str]) -> Optional[dict]:
    """
    온보딩 preferred_length 문자열 → page_range_soft dict 변환

    "300p 이하", "300p 이내" → {"operator": "lte", "value": 300}
    "200p 이상"              → {"operator": "gte", "value": 200}
    "300p 내외", "300p 정도" → {"operator": "around", "value": 300}
    "제한 없음" 또는 숫자 없음 → None
    """
    if not preferred_length:
        return None
    m = re.search(r"(\d+)", preferred_length)
    if not m:
        return None
    value = int(m.group(1))

    if re.search(r"이상|초과", preferred_length):
        operator = "gte"
    elif re.search(r"내외|정도|쯤|전후", preferred_length):
        operator = "around"
    else:  # 이하, 이내, 미만, 숫자만 쓴 경우
        operator = "lte"

    return {"operator": operator, "value": value}
