# -*- coding: utf-8 -*-
"""
BGE Cross-Encoder Reranker

BAAI/bge-reranker-v2-m3 모델을 사용한 Cross-Encoder Reranker.

입력 포맷 (BD variant):
    도서명 + 카테고리(중분류) + 책소개 + 리뷰

Score Fusion (실험 최적값 α=0.2):
    final_score = 0.2 × norm(retrieval_score) + 0.8 × norm(bge_score)
"""

import logging
import os
from typing import Any, Dict, List, Optional

import psycopg2
import psycopg2.extras

logger = logging.getLogger(__name__)

# ── 모델 설정 ──────────────────────────────────────────────────
MODEL_NAME = os.getenv(
    "BGE_RERANKER_MODEL",
    "BAAI/bge-reranker-v2-m3",
)
DEVICE     = os.getenv("BGE_RERANKER_DEVICE", "cpu")
MAX_LENGTH = int(os.getenv("BGE_RERANKER_MAX_LENGTH", "512"))

# Score Fusion 가중치 (실험 최적값: α=0.2)
RETRIEVAL_WEIGHT = float(os.getenv("BGE_RETRIEVAL_WEIGHT", "0.2"))
BGE_WEIGHT       = 1.0 - RETRIEVAL_WEIGHT

# ── 모델 싱글턴 ────────────────────────────────────────────────
_model = None

def _get_model():
    """BGE CrossEncoder 모델을 한 번만 로드해서 재사용한다."""
    global _model
    if _model is None:
        from sentence_transformers import CrossEncoder
        logger.info("BGE Reranker 모델 로드 중: %s (device=%s)", MODEL_NAME, DEVICE)
        _model = CrossEncoder(
            MODEL_NAME,
            max_length=MAX_LENGTH,
            device=DEVICE,
        )
        logger.info("BGE Reranker 모델 로드 완료")
    return _model


# ── DB 조회 ────────────────────────────────────────────────────

def fetch_books_by_isbn(isbns: List[str]) -> Dict[str, Dict[str, Any]]:
    """
    ISBN 목록으로 PostgreSQL books 테이블에서 도서 메타데이터를 조회한다.

    BD variant에 필요한 필드: title, mid_cate, book_intro, review_text
    """
    conn_kwargs: Dict[str, Any] = {
        "dbname": os.getenv("DB_NAME"),
        "host"  : os.getenv("DB_HOST"),
        "port"  : os.getenv("DB_PORT"),
        "user"  : os.getenv("DB_USER"),
    }
    password = os.getenv("DB_PASSWORD", "")
    if password:
        conn_kwargs["password"] = password

    with psycopg2.connect(**conn_kwargs) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT isbn, title, author, publisher, publish_date,
                       page, book_intro, review,
                       large_cate, mid_cate
                FROM books
                WHERE isbn = ANY(%s)
                """,
                (isbns,),
            )
            rows = cur.fetchall()

    book_index = {}
    for row in rows:
        book = dict(row)
        book["publish_date"] = str(book["publish_date"]) if book["publish_date"] else ""
        book_index[book["isbn"]] = book
    return book_index


# ── BD variant 텍스트 포맷 ─────────────────────────────────────

def format_bd(book: Dict[str, Any]) -> str:
    """
    BD variant: 도서명 + 중분류 카테고리 + 책소개 + 리뷰

    실험에서 BGE 최적 입력 포맷으로 선정된 variant.
    (Ablation 실험 결과: NDCG@10 기준 BD > D > B > C > A > E)
    """
    mid = book.get("mid_cate") or []
    if isinstance(mid, list):
        mid = " > ".join(mid)

    return (
        f"도서명: {book.get('title', '')}\n"
        f"카테고리: {mid}\n"
        f"책소개: {book.get('book_intro', '') or ''}\n"
        f"리뷰: {book.get('review', '') or ''}"
    )


# ── 쿼리 생성 ──────────────────────────────────────────────────

def build_query(rag_query: Dict[str, Any]) -> str:
    """
    rag_query에서 BGE 입력용 단일 쿼리 문자열을 생성한다.

    semantic_query가 있으면 우선 사용.
    없으면 keyword_query 리스트를 공백으로 합친다.
    """
    semantic = rag_query.get("semantic_query", "")
    if semantic:
        return semantic

    keywords = rag_query.get("keyword_query", [])
    if isinstance(keywords, list):
        return " ".join(keywords)
    return str(keywords)


# ── 점수 정규화 ────────────────────────────────────────────────

def _minmax_norm(values: List[float]) -> List[float]:
    """리스트 내 값을 0~1로 min-max 정규화한다."""
    if not values:
        return values
    mn, mx = min(values), max(values)
    if mx == mn:
        return [1.0] * len(values)
    return [(v - mn) / (mx - mn) for v in values]


# ── 핵심 reranking 함수 ────────────────────────────────────────

def rerank(
    search_candidates: List[Dict[str, Any]],
    rag_query        : Dict[str, Any],
    book_index       : Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    BGE Cross-Encoder로 후보 도서를 재정렬한다.

    Args:
        search_candidates: Hybrid 검색 결과
                           [{"rank": 1, "score": 0.016, "isbn": "...", ...}, ...]
        rag_query        : RAG 쿼리 딕셔너리
        book_index       : ISBN → 도서 메타데이터 (None이면 DB 조회)

    Returns:
        {
            "reranked_books": [...],
            "meta": {...}
        }
    """
    if not search_candidates:
        return {"reranked_books": [], "meta": {}}

    # ① 도서 메타데이터 조회
    if book_index is None:
        isbns = [c.get("isbn", "") for c in search_candidates if c.get("isbn")]
        book_index = fetch_books_by_isbn(isbns)

    # ② 쿼리 생성
    query = build_query(rag_query)
    if not query:
        logger.warning("BGE Reranker: 쿼리가 비어 있어 Hybrid 결과 그대로 반환")
        return {"reranked_books": [], "meta": {"reason": "empty_query"}}

    # ③ (query, document) 쌍 생성
    pairs = []
    valid_candidates = []
    for candidate in search_candidates:
        isbn = candidate.get("isbn", "")
        book = book_index.get(isbn, {})
        doc_text = format_bd(book)
        pairs.append((query, doc_text))
        valid_candidates.append({**candidate, "book": book})

    # ④ BGE 점수 계산
    model = _get_model()
    bge_scores: List[float] = model.predict(pairs).tolist()

    # ⑤ Score Fusion: 0.2 × norm(retrieval) + 0.8 × norm(bge)
    retrieval_raw = [float(c.get("score", 0)) for c in valid_candidates]
    norm_retrieval = _minmax_norm(retrieval_raw)
    norm_bge       = _minmax_norm(bge_scores)

    # ⑥ 최종 정렬 및 결과 구성
    scored = []
    for i, candidate in enumerate(valid_candidates):
        book       = candidate["book"]
        isbn       = candidate.get("isbn", "")
        bge_score  = bge_scores[i]
        final_score = (
            RETRIEVAL_WEIGHT * norm_retrieval[i]
            + BGE_WEIGHT     * norm_bge[i]
        )

        scored.append({
            # ES 원본 필드 전체 보존
            **{k: v for k, v in candidate.items() if k != "book"},
            # 메타데이터: PostgreSQL 우선, 없으면 ES fallback
            "isbn"            : isbn,
            "title"           : book.get("title")     or candidate.get("title", ""),
            "author"          : book.get("author")    or candidate.get("author", ""),
            "publisher"       : book.get("publisher") or candidate.get("publisher", ""),
            "page"            : book.get("page")      or candidate.get("page"),
            # 리랭킹 결과 필드
            "original_rank"     : candidate.get("rank"),
            "raw_retrieval_score": retrieval_raw[i],
            "retrieval_score"   : round(norm_retrieval[i], 4),
            "bge_score"         : round(bge_score, 4),
            "final_score"       : round(final_score, 4),
        })

    scored.sort(key=lambda x: x["final_score"], reverse=True)
    for idx, book in enumerate(scored, start=1):
        book["final_rank"] = idx

    logger.info(
        "BGE Reranker 완료: %d건 (query=%s...)",
        len(scored), query[:30],
    )

    return {
        "reranked_books": scored,
        "meta": {
            "model"           : MODEL_NAME,
            "variant"         : "BD",
            "candidate_count" : len(scored),
            "retrieval_weight": RETRIEVAL_WEIGHT,
            "bge_weight"      : BGE_WEIGHT,
            "query"           : query,
        },
    }
