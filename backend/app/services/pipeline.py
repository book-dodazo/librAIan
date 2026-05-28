# -*- coding: utf-8 -*-
# ============================================================
# app/services/pipeline.py
#
# 변경 이력:
#   v0.1 - 최초 작성
#          chat_service.py에서 파이프라인 단계 분리
#   v0.2 - Reranker 연동 (app/modules/reranker/clova_reranker.py)
#          availability 조회 연동 (app/services/loan_availability.py)
#   v0.3 - Reranker 교체: CLOVA → BGE Cross-Encoder (BD variant, Score Fusion α=0.2)
#
# 새 단계 추가 방법:
#   1. 아래에 async def run_xxx() 또는 def run_xxx() 추가
#   2. PipelineResult에 필드 추가
#   3. run_full_pipeline()에 순서대로 호출 추가
# ============================================================
"""
파이프라인 단계 정의

각 단계는 독립 함수로 분리되어 있어서
단계별 교체, 비활성화, 추가가 chat_service.py 수정 없이 가능합니다.

현재 단계:
    [2] run_rag_query     → RAG 쿼리 생성 (slot/rag_query_builder.py)
    [3] run_hybrid_search   → Hybrid 검색 (modules/RAG/retriever.py)
    [4] run_reranker      → BGE Cross-Encoder Reranker (modules/reranker/bge_reranker.py)
    [5] run_availability  → 대출 가능 여부 조회 (models/loan_availability.py)
"""
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Optional

from app.modules.slot.rag_query_builder import build_rag_query
from app.modules.slot.schema import SessionContext
from app.modules.RAG.anchor_book_pipeline import run_anchor_pipeline
from app.modules.RAG.final_hybrid import full_hybrid
from app.modules.reranker.bge_reranker import rerank as bge_rerank
from app.services.loan_availability import check_books_availability

logger = logging.getLogger(__name__)


# ── 파이프라인 결과 컨테이너 ──────────────────────────────────

@dataclass
class PipelineResult:
    """
    파이프라인 각 단계의 결과를 담는 컨테이너

    새 단계 추가 시 여기에 필드를 추가하세요.
    """
    # [2] RAG 쿼리 생성 결과
    rag_query: Optional[dict[str, Any]] = None

    # [2-1] Anchor 기반 query rewrite 결과
    anchor_rewritten: bool = False

    # [3] Hyrbid 검색 결과
    # 형태: [{"rank": 1, "isbn": "...", "score": 1.23}, ...]
    hybrid_results: list[dict] = field(default_factory=list)

    # [4] Reranking 결과
    # 형태: [{"isbn": "...", "title": "...", "final_rank": 1, "final_score": 0.95, ...}, ...]
    reranked_results: list[dict] = field(default_factory=list)

    # [5] 대출 가능 여부 조회 결과
    # 형태: {"isbn": {"has_book": "Y", "loan_available": "Y"}, ...}
    availability_index: dict[str, dict] = field(default_factory=dict)

    # context.slots.availability_required 값 — final_results 필터링 기준
    availability_required: bool = False

    # 에러 발생 단계 기록 (디버깅용)
    errors: list[str] = field(default_factory=list)

    @property
    def final_results(self) -> list[dict]:
        """
        최종 결과 반환 — 항상 최대 3건 보장

        availability_index 없음     → Top3 그대로 반환
        [Scenario C] availability_required=True → 대출가능 우선, 부족하면 상위 랭킹으로 보충
        [Scenario A/B] 그 외        → 대출가능 우선 Top3, 부족하면 상위 랭킹으로 보충
        """
        base = self.reranked_results if self.reranked_results else self.hybrid_results

        if not self.availability_index:
            return base[:3]

        # 대출 가능 여부 정보 부착
        books_with_avail = []
        for book in base:
            isbn  = book.get("isbn", "")
            avail = self.availability_index.get(isbn, {})
            books_with_avail.append({
                **book,
                "has_book"      : avail.get("has_book", "-"),
                "loan_available": avail.get("loan_available", "-"),
            })

        available     = [b for b in books_with_avail if b.get("loan_available") == "Y"]
        not_available = [b for b in books_with_avail if b.get("loan_available") != "Y"]

        # [Scenario C] 대출가능 필수 — 대출가능만, 부족해도 3건 이하로 반환
        if self.availability_required:
            return available[:3]

        # [Scenario A/B] 대출가능 우선, 부족하면 상위 랭킹으로 보충해서 항상 3건
        result = list(available[:3])
        for book in not_available:
            if len(result) >= 3:
                break
            result.append(book)
        return result


# ── 파이프라인 단계 함수들 ────────────────────────────────────

async def run_rag_query(context: SessionContext) -> dict[str, Any]:
    """[2단계] RAG 쿼리 생성"""
    rag_query = await build_rag_query(context)
    logger.info("RAG 쿼리 생성 완료")
    return rag_query

def run_anchor_query_rewrite(rag_query: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """
    [2-1단계] Anchor 기반 RAG 쿼리 재작성

    rag_query 안에 anchor가 있으면:
    - anchor 책/작가 정보를 DB에서 조회
    - HCX-007로 keyword_query, semantic_query 재작성
    - 기존 rag_query에 덮어쓰기

    anchor가 없으면 원본 rag_query 그대로 반환
    """
    if not rag_query:
        return rag_query, False

    anchor = rag_query.get("anchor")

    if not anchor:
        return rag_query, False

    try:
        rewritten = run_anchor_pipeline(rag_query)
        logger.info("Anchor 기반 query rewrite 완료")
        return rewritten, True

    except Exception as e:
        logger.error("Anchor 기반 query rewrite 실패: %s", e, exc_info=True)
        return rag_query, False

def run_hybrid_search(
    rag_query                : dict[str, Any],
    small_category_embeddings: Optional[dict] = None,
    index_name               : str = "books_review_full_100000",
    size                     : int = 20,
) -> list[dict]:
    """
    [3단계] Hybrid 검색 (A파트 연동)

    app/modules/RAG/retriever.py의 search_bm25_with_cate()를 호출합니다.
    모듈이 없으면 빈 리스트 반환 (graceful skip).
    """
    try:
        results = full_hybrid(
            result = rag_query,
        )
        logger.info("Hybrid 검색 완료: %d건", len(results))
        return results

    except ImportError as e:
        # retriever.py 자체는 정상 import됨
        # → 이 ImportError는 내부 의존성(sentence-transformers 등) 누락을 의미함
        logger.warning(
            "Hybrid 검색 의존성 누락 — 검색 스킵: %s "
            "(requirements.txt에 sentence-transformers / torch 추가 필요)",
            e,
        )
        return []
    except Exception as e:
        logger.error("Hybrid 검색 실패: %s", e, exc_info=True)
        return []


def run_reranker(
    hybrid_results: list[dict],
    rag_query     : dict[str, Any],
) -> list[dict]:
    """
    [4단계] BGE Cross-Encoder Reranker

    app/modules/reranker/bge_reranker.py의 rerank()를 호출합니다.

    - 모델: BAAI/bge-reranker-v2-m3
    - 입력 포맷: BD variant (도서명 + 중분류 카테고리 + 책소개 + 리뷰)
    - Score Fusion: 0.2 × norm(retrieval) + 0.8 × norm(bge)  [실험 최적값 α=0.2]

    Args:
        hybrid_results: run_hybrid_search()의 결과
        rag_query     : RAG 쿼리 딕셔너리 (semantic_query 또는 keyword_query 사용)

    Returns:
        재순위된 도서 목록
        [{"isbn": "...", "title": "...", "final_rank": 1, "final_score": 0.95, ...}, ...]
    """
    if not hybrid_results:
        return []

    try:
        result  = bge_rerank(
            search_candidates = hybrid_results,
            rag_query         = rag_query,
        )
        reranked = result.get("reranked_books", [])
        logger.info("BGE Reranking 완료: %d건", len(reranked))
        return reranked

    except ImportError:
        logger.warning("BGE Reranker 의존성 없음 (sentence-transformers / torch) — 스킵")
        return []
    except Exception as e:
        logger.error("BGE Reranking 실패: %s", e, exc_info=True)
        return []


def run_availability(
    books        : list[dict],
    lib_code     : Optional[str] = None,
    naru_api_key : Optional[str] = None,
) -> dict[str, dict]:
    """
    [5단계] 정보나루 API 대출 가능 여부 조회

    app/services/loan_availability.py의 check_books_availability()를 호출합니다.
    availability_required 조건에 따른 필터링은 PipelineResult.final_results에서 처리합니다.

    Args:
        books        : final_results 후보 도서 목록
        lib_code     : 도서관 코드 (없으면 환경변수 NARU_LIB_CODE 사용)
        naru_api_key : 정보나루 API 키 (없으면 환경변수 NARU_API_KEY 사용)

    Returns:
        {"isbn": {"has_book": "Y", "loan_available": "Y"}, ...}
    """
    if not books:
        return {}

    _lib_code = lib_code     or os.getenv("NARU_LIB_CODE", "")
    _api_key  = naru_api_key or os.getenv("NARU_API_KEY", "")

    if not _lib_code or not _api_key:
        logger.warning(
            "NARU_LIB_CODE 또는 NARU_API_KEY 없음 — 대출 가능 여부 조회 스킵"
        )
        return {}

    try:
        isbns  = [b.get("isbn", "") for b in books if b.get("isbn")]
        result = check_books_availability(isbns, _lib_code, _api_key)
        logger.info("대출 가능 여부 조회 완료: %d건", len(result))
        return result

    except ImportError:
        logger.warning("loan_availability 모듈 없음 (app/services/loan_availability.py) — 스킵")
        return {}
    except Exception as e:
        logger.error("대출 가능 여부 조회 실패: %s", e)
        return {}


async def run_full_pipeline(
    context                  : SessionContext,
    small_category_embeddings: Optional[dict] = None,
    lib_code                 : Optional[str]  = None,
    naru_api_key             : Optional[str]  = None,
) -> PipelineResult:
    """
    RAG 이후 전체 파이프라인을 순서대로 실행합니다.

    chat_service.py의 _build_rag_response에서 이 함수를 호출합니다.
    새 단계 추가 시 여기에 순서대로 추가하세요.

    Args:
        context                  : 현재 세션 컨텍스트
        small_category_embeddings: 소분류 임베딩 (없으면 subject boost 스킵)
        lib_code                 : 도서관 코드 (없으면 환경변수 사용)
        naru_api_key             : 정보나루 API 키 (없으면 환경변수 사용)

    Returns:
        PipelineResult
    """
    result = PipelineResult()

    # [2] RAG 쿼리 생성
    result.rag_query = await run_rag_query(context)

    # [2-1] Anchor 기반 query rewrite
    result.rag_query, result.anchor_rewritten = run_anchor_query_rewrite(
        rag_query=result.rag_query

    )

    # [3] Hybrid 검색
    result.hybrid_results = run_hybrid_search(
        rag_query                = result.rag_query,
        small_category_embeddings= small_category_embeddings,
    )

    # [3-1] Refinement: 이전에 추천한 책 후보에서 제거
    if context.previous_result:
        exclude_set = set(context.previous_result)
        before = len(result.hybrid_results)
        result.hybrid_results = [
            r for r in result.hybrid_results
            if r.get("isbn") not in exclude_set
        ]
        logger.info("refinement 제외: %d → %d건", before, len(result.hybrid_results))

    # [4] BGE Cross-Encoder Reranker
    result.reranked_results = run_reranker(
        hybrid_results = result.hybrid_results,
        rag_query      = result.rag_query,
    )

    # [5] 대출 가능 여부 조회 — 전체 결과 대상 (대출 가능 책 탐색 범위 확대)
    candidate_books = (result.reranked_results or result.hybrid_results)
    result.availability_required = context.slots.availability_required
    result.availability_index = run_availability(
        books        = candidate_books,
        lib_code     = lib_code,
        naru_api_key = naru_api_key,
    )

    logger.info(
        "파이프라인 완료: Hybrid=%d건 reranked=%d건 availability=%d건 availability result=%s",
        len(result.hybrid_results),
        len(result.reranked_results),
        len(result.availability_index),
        result.availability_index
    )
    return result
