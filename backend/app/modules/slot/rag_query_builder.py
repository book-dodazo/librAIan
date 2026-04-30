# -*- coding: utf-8 -*-
# ============================================================
# app/modules/slot/rag_query_builder.py
#
# 변경 이력:
#   v0.1 - 최초 작성
#          P7 토론 결과 기반 RAG 쿼리 생성
#          BM25 키워드 + Dense 자연어 + 메타데이터 필터
# ============================================================
"""
RAG 쿼리 빌더

P7 결론:
    - slot 값 기반으로 쿼리 생성 (원문 발화 X)
    - LLM이 자연어 쿼리 생성 (매핑 테이블 X)
    - BM25용 keyword_query, Dense용 semantic_query, 공통 filters
    - Refinement 시 이전 쿼리에 수정 사항만 반영

RAG 파이프라인:
    BM25 검색기  → keyword_query + filters.coarse_category
    Dense 검색기 → semantic_query + filters.coarse_category
    Reranking    → score_boost (대분류 필터 + 중분류 스코어)
    도서관 API   → availability_required
"""
import logging
from typing import Any, Optional

from app.core.exceptions import IntentParseError, LLMCallError
from app.modules.llm.clova_client import chat_complete_json
from app.modules.slot.prompts import RAG_QUERY_GENERATION_PROMPT
from app.modules.slot.schema import (
    AnchorType,
    ConstraintOperator,
    SessionContext,
)

logger = logging.getLogger(__name__)

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
            "keyword_query" : ["키워드1", ...],
            "semantic_query": "자연어 검색 쿼리",
            "filters"       : {"coarse_category": ..., ...},
            "score_boost"   : {"fine_category": ..., "subject": ...},
            "availability_required": bool,
            "anchor"        : {...} or None,
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

    # ── 메타데이터 필터 생성 ──────────────────────────────────
    filters = _build_filters(context)

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
        "score_boost"          : score_boost,
        "availability_required": slots.availability_required,
        "anchor"               : _anchor_to_dict(context),
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
        lines.append(f"감정/상태 - {slots.mood.value}")

    if context.anchor:
        lines.append(f"기준 {context.anchor.type.value} - {context.anchor.value}")

    for c in slots.constraints:
        lines.append(f"제약 - {c.raw or c.value}")

    return "\n".join(lines) if lines else "정보 없음"


def _build_filters(context: SessionContext) -> dict:
    """메타데이터 필터 생성"""
    filters: dict[str, Any] = {}
    slots = context.slots

    # 대분류 필터 (BM25 + Dense 공통) — 리스트로 전달
    if slots.topic.is_filled() and slots.topic.coarse:
        filters["coarse_category"] = slots.topic.coarse  # list[str]

    # anchor 타입별 필터
    if context.anchor:
        if context.anchor.type == AnchorType.author:
            filters["author"] = context.anchor.value
        elif context.anchor.type == AnchorType.book_title:
            filters["title"] = context.anchor.value

    # constraints → 메타데이터 필터
    for c in slots.constraints:
        if c.type == "page_range" and c.operator and c.value:
            filters["page_range"] = {
                "operator": c.operator.value,
                "value"   : c.value,
            }
        elif c.type == "pub_year" and c.operator and c.value:
            filters["pub_year"] = {
                "operator": c.operator.value,
                "value"   : c.value,
            }
        elif c.type == "target_reader":
            filters["target_reader"] = c.value

    return filters


def _build_score_boost(context: SessionContext) -> dict:
    """Reranking용 score_boost 생성 — 리스트로 전달"""
    boost: dict[str, Any] = {}
    slots = context.slots

    if slots.topic.is_filled():
        if slots.topic.fine:
            boost["fine_category"] = slots.topic.fine    # list[str]
        if slots.topic.subject:
            boost["subject"] = slots.topic.subject       # list[str]

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
        keywords.append(str(slots.mood.value))

    return keywords[:7]  # 최대 7개


def _apply_refinement(
    base_query  : str,
    modification: str,
    slots       : Any,
) -> str:
    """
    Refinement 요청을 기존 쿼리에 반영합니다.

    P7 결론: 처음부터 재생성 X, 이전 쿼리 + 수정 사항만 반영
    """
    # 단순 문자열 조합 (추후 LLM으로 개선 가능)
    additions = []

    if slots.reading_level.is_filled():
        label = _LEVEL_LABEL.get(slots.reading_level.value, "")
        if label:
            additions.append(label)

    # "더 짧은" 같은 수식어가 있으면 추가
    if any(kw in modification for kw in ["짧은", "빠르게", "금방"]):
        additions.append("짧은")

    if additions:
        return f"{' '.join(additions)} {base_query}"
    return base_query


def _anchor_to_dict(context: SessionContext) -> Optional[dict]:
    """anchor → dict 변환"""
    if not context.anchor:
        return None
    return {
        "value": context.anchor.value,
        "type" : context.anchor.type.value,
    }
