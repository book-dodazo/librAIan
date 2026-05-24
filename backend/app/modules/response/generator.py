# -*- coding: utf-8 -*-
"""
추천 결과 생성 모듈

역할:
    1. 검색 결과 도서의 상세 정보(표지, 소개)를 DB에서 조회
    2. RAG 쿼리 + 온보딩 프로파일 기반으로 맞춤형 추천 이유를 LLM으로 생성
    3. 최종 결과 카드 리스트 반환

출력 형태 (각 카드):
    {
        "isbn"                  : "9791234567890",
        "title"                 : "책 제목",
        "author"                : "저자명",
        "publisher"             : "출판사",
        "cover_url"             : "https://...",
        "book_intro"            : "책 소개 텍스트",
        "recommendation_reason" : "맞춤형 추천 이유 (LLM 생성)",
        "loan_available"        : "Y" | "N" | "-",
        "has_book"              : "Y" | "N" | "-",
        "final_rank"            : 1,
    }
"""
import asyncio
import logging
import re
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.modules.llm.clova_client import chat_complete
from app.prompts.response import RECOMMENDATION_REASON_PROMPT

logger = logging.getLogger(__name__)


# ── 리뷰 텍스트 빌더 ───────────────────────────────────────────

def _build_reader_review(review: dict, review_count: int) -> str:
    """
    DB review JSON + review_count → 프롬프트용 독자 평가 텍스트.
    리뷰가 없으면 빈 문자열 반환.
    """
    if not review or review_count == 0:
        return ""

    parts = []
    if review.get("strengths"):
        parts.append(f"좋은 점: {review['strengths']}")
    if review.get("reader_reaction"):
        parts.append(f"독자 반응: {review['reader_reaction']}")
    if review.get("weaknesses"):
        parts.append(f"아쉬운 점: {review['weaknesses']}")

    if not parts:
        return ""

    return f"(리뷰 {review_count}건) " + " / ".join(parts)


# ── DB 조회 ────────────────────────────────────────────────────

def fetch_book_details(isbns: list[str], db: Session) -> dict[str, dict]:
    """
    isbn 목록으로 books 테이블에서 표지 URL, 책 소개를 조회.

    Returns:
        {isbn: {"cover_url": "...", "book_intro": "..."}, ...}
    """
    if not isbns:
        return {}

    from sqlalchemy import text
    placeholders = ", ".join(f"'{isbn}'" for isbn in isbns)
    query = text(f"""
        SELECT isbn, ori_cover_s, book_intro, review, review_count, review_score
        FROM books
        WHERE isbn IN ({placeholders})
    """)

    result = {}
    try:
        rows = db.execute(query).fetchall()
        for row in rows:
            # review JSON에서 독자 반응 텍스트 추출
            review_raw = row[3] or {}
            if isinstance(review_raw, str):
                import json as _json
                try:
                    review_raw = _json.loads(review_raw)
                except Exception:
                    review_raw = {}
            reader_review = _build_reader_review(review_raw, row[4] or 0)

            # review_score: 0~10 스케일 → 5점 만점으로 변환
            raw_score = row[5]
            review_score = round(float(raw_score) / 2, 1) if raw_score else None

            result[row[0]] = {
                "cover_url"     : row[1] or "",
                "book_intro"    : (row[2] or "")[:800],
                "reader_review" : reader_review,
                "review_score"  : review_score,
            }
    except Exception as e:
        logger.error("책 상세 정보 조회 실패: %s", e)

    return result


# ── 프롬프트 빌더 ──────────────────────────────────────────────

def _build_request_analysis(rag_query: dict, original_query: str) -> str:
    """RAG 쿼리에서 사용자 요청 분석 텍스트 생성"""
    parts = [f"원본 질의: {original_query}"]

    filters = rag_query.get("filters", {})
    if filters.get("cate_depth1"):
        parts.append(f"주제: {', '.join(filters['cate_depth1'])}")
    if filters.get("cate_depth2"):
        parts.append(f"세부 주제: {', '.join(filters['cate_depth2'])}")

    signals = rag_query.get("session_signals", {})
    if signals.get("purpose"):
        parts.append(f"독서 목적: {signals['purpose']}")
    if signals.get("mood"):
        parts.append(f"원하는 분위기: {signals['mood']}")
    if signals.get("reading_level"):
        parts.append(f"난이도: {signals['reading_level']}")

    semantic = rag_query.get("semantic_query", "")
    if semantic:
        parts.append(f"검색 의도: {semantic}")

    constraints = rag_query.get("constraints", {})
    if constraints.get("page_range"):
        parts.append(f"분량 조건: {constraints['page_range']}")

    anchors = rag_query.get("anchors")
    if anchors:
        anchor_type = anchors.get("type", "")
        anchor_val  = anchors.get("value", "")
        if anchor_val:
            parts.append(f"기준 {anchor_type}: {anchor_val}")

    return "\n".join(f"- {p}" for p in parts)


def _build_user_profile(onboarding: Optional[dict]) -> str:
    """온보딩 데이터에서 사용자 성향 텍스트 생성"""
    if not onboarding:
        return "- 독서 성향 정보 없음"

    parts = []

    cats = onboarding.get("preferred_categories") or []
    if cats:
        cat_labels = []
        for c in cats[:3]:
            if isinstance(c, dict):
                label = c.get("sub") or c.get("main") or ""
            else:
                label = str(c)
            if label:
                cat_labels.append(label)
        if cat_labels:
            parts.append(f"선호 분야: {', '.join(cat_labels)}")

    liked = onboarding.get("recent_liked_books") or []
    if liked:
        titles = [b.get("title", "") if isinstance(b, dict) else str(b) for b in liked[:3]]
        titles = [t for t in titles if t]
        if titles:
            parts.append(f"최근 좋았던 책: {', '.join(titles)}")

    length = onboarding.get("preferred_length", "")
    if length:
        parts.append(f"선호 분량: {length}")

    disliked = onboarding.get("disliked_keywords") or []
    if disliked:
        parts.append(f"기피 키워드: {', '.join(disliked[:5])}")

    return "\n".join(f"- {p}" for p in parts) if parts else "- 독서 성향 정보 없음"


# ── LLM 추천 이유 생성 ─────────────────────────────────────────

async def _generate_reason(
    book          : dict,
    book_detail   : dict,
    rag_query     : dict,
    original_query: str,
    onboarding    : Optional[dict],
) -> str:
    """단일 도서에 대한 추천 이유를 LLM으로 생성"""
    request_analysis = _build_request_analysis(rag_query, original_query)
    user_profile     = _build_user_profile(onboarding)

    reader_review = book_detail.get("reader_review", "")
    prompt = RECOMMENDATION_REASON_PROMPT.format(
        request_analysis = request_analysis,
        user_profile     = user_profile,
        title            = book.get("title", ""),
        author           = book.get("author", ""),
        category         = book.get("category", ""),
        book_intro       = book_detail.get("book_intro", "정보 없음"),
        reader_review    = reader_review if reader_review else "리뷰 정보 없음",
    )

    try:
        raw = await chat_complete(
            system_prompt = prompt,
            messages      = [{"role": "user", "content": "이 도서의 맞춤 추천 이유를 작성해주세요."}],
            temperature   = 0.6,
            max_tokens    = 500,
        )

        # <reason>...</reason> 태그에서 추출
        match = re.search(r"<reason>(.*?)</reason>", raw, re.DOTALL)
        if match:
            return match.group(1).strip()

        # 태그 없으면 <thinking> 이후 텍스트 반환
        thinking_end = raw.find("</thinking>")
        if thinking_end != -1:
            return raw[thinking_end + len("</thinking>"):].strip()

        return raw.strip()

    except Exception as e:
        logger.warning("추천 이유 생성 실패 (isbn=%s): %s", book.get("isbn"), e)
        return ""


# ── 메인 진입점 ────────────────────────────────────────────────

async def generate_result_cards(
    final_results : list[dict],
    rag_query     : dict[str, Any],
    original_query: str,
    onboarding    : Optional[dict],
    db            : Session,
) -> list[dict]:
    """
    검색 결과에 표지/소개/추천이유를 붙여 최종 카드 리스트 반환.

    Args:
        final_results : pipeline.final_results (reranked + availability 정보 포함)
        rag_query     : RAG 쿼리 딕셔너리
        original_query: 사용자 원본 질의
        onboarding    : 온보딩 데이터 (없으면 None)
        db            : SQLAlchemy 세션

    Returns:
        카드 리스트 (각 카드에 cover_url, book_intro, recommendation_reason 추가)
    """
    if not final_results:
        return []

    # DB에서 표지/소개 일괄 조회
    isbns       = [b.get("isbn", "") for b in final_results if b.get("isbn")]
    book_detail = fetch_book_details(isbns, db)

    # 추천 이유 병렬 생성
    reason_tasks = [
        _generate_reason(
            book           = book,
            book_detail    = book_detail.get(book.get("isbn", ""), {}),
            rag_query      = rag_query,
            original_query = original_query,
            onboarding     = onboarding,
        )
        for book in final_results
    ]
    reasons = await asyncio.gather(*reason_tasks)

    # 최종 카드 조합
    cards = []
    for book, reason in zip(final_results, reasons):
        isbn   = book.get("isbn", "")
        detail = book_detail.get(isbn, {})
        cards.append({
            "isbn"                  : isbn,
            "title"                 : book.get("title", ""),
            "author"                : book.get("author", ""),
            "publisher"             : book.get("publisher", ""),
            "cover_url"             : detail.get("cover_url", ""),
            "book_intro"            : detail.get("book_intro", ""),
            "reader_review"         : detail.get("reader_review", ""),
            "review_score"          : detail.get("review_score"),
            "recommendation_reason" : reason,
            "loan_available"        : book.get("loan_available", "-"),
            "has_book"              : book.get("has_book", "-"),
            "final_rank"            : book.get("final_rank", 0),
            "final_score"           : book.get("final_score", 0.0),
        })

    logger.info("결과 카드 생성 완료: %d건", len(cards))
    return cards
