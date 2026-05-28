#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BGE-BD 파이프라인 레이턴시 벤치마크

사용법:
    python scripts/benchmark_latency.py            # 기본 쿼리
    python scripts/benchmark_latency.py --runs 5   # 5회 반복 평균

측정 단계:
    [1] Hybrid Search  (ES BM25 + Dense)
    [2] BGE 모델 로드  (cold start, 최초 1회)
    [3] BGE 추론       (DB 조회 + Cross-Encoder scoring)

출력:
    단계별 소요 시간 및 warm 평균 레이턴시
"""

import argparse
import sys
import time
from pathlib import Path

# ── 경로 설정 ──────────────────────────────────────────────────
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

try:
    import dotenv
    dotenv.load_dotenv(BACKEND_DIR / ".env", override=True)
except ImportError:
    pass

# ── 기본 테스트 쿼리 ──────────────────────────────────────────
DEFAULT_RAG_QUERY = {
    "keyword_query"    : ["비 오는 날", "잔잔한 소설", "독서 추천"],
    "semantic_query"   : "비 오는 날 읽으면 좋은 잔잔한 분위기의 소설을 추천해주세요.",
    "filters"          : {},
    "constraints"      : {},
    "score_boost"      : {"subject": ["잔잔한 소설"]},
    "availability_required": False,
    "anchors"          : None,
    "session_signals"  : {"purpose": "재미"},
    "onboarding_signals": {},
    "slot_revision_hints": {},
}


# ── 유틸 ──────────────────────────────────────────────────────

def fmt(ms: float) -> str:
    return f"{ms:>7.0f} ms"


def print_section(title: str):
    print(f"\n{'─'*58}")
    print(f"  {title}")
    print(f"{'─'*58}")


def run_benchmark(rag_query: dict, n_runs: int = 3) -> None:
    print("=" * 58)
    print("  BGE-BD 파이프라인 레이턴시 벤치마크")
    print("=" * 58)

    # ── [1] Hybrid Search ─────────────────────────────────
    print_section("[1] Hybrid Search")
    from app.modules.RAG.final_hybrid import full_hybrid

    t0 = time.perf_counter()
    hybrid_results = full_hybrid(result=rag_query)
    hybrid_ms = (time.perf_counter() - t0) * 1000

    print(f"  소요 시간  : {fmt(hybrid_ms)}")
    print(f"  검색 결과  : {len(hybrid_results)}건")
    print(f"  상위 3건   :")
    for r in hybrid_results[:3]:
        print(f"    {r.get('rank','')}위 {r.get('title','')[:35]}  score={r.get('score',0):.4f}")

    # ── [2] BGE 모델 로드 (cold start) ────────────────────
    print_section("[2] BGE 모델 로드 (cold start)")
    from app.modules.reranker.bge_reranker import (
        rerank as bge_rerank,
        _get_model,
        fetch_books_by_isbn,
        format_bd,
        build_query,
        DEVICE,
        MODEL_NAME,
    )

    print(f"  모델       : {MODEL_NAME}")
    print(f"  디바이스   : {DEVICE}")

    t0 = time.perf_counter()
    _ = _get_model()
    cold_ms = (time.perf_counter() - t0) * 1000
    print(f"  소요 시간  : {fmt(cold_ms)}  (이후 요청에서는 0ms)")

    # ── [3] BGE 추론 — 세분화 측정 ───────────────────────
    print_section("[3] BGE 추론 세분화 (1st call)")
    isbns = [c.get("isbn", "") for c in hybrid_results if c.get("isbn")]

    t_db0 = time.perf_counter()
    book_index = fetch_books_by_isbn(isbns)
    db_ms = (time.perf_counter() - t_db0) * 1000

    query = build_query(rag_query)
    pairs = [(query, format_bd(book_index.get(isbn, {}))) for isbn in isbns]
    model = _get_model()

    t_m0 = time.perf_counter()
    _ = model.predict(pairs)
    score_ms = (time.perf_counter() - t_m0) * 1000

    t_r0 = time.perf_counter()
    result   = bge_rerank(search_candidates=hybrid_results, rag_query=rag_query)
    reranked = result.get("reranked_books", [])
    total_bge_ms = (time.perf_counter() - t_r0) * 1000

    print(f"  DB 조회    : {fmt(db_ms)}  (PostgreSQL, {len(isbns)}건)")
    print(f"  CE 추론    : {fmt(score_ms)}  (Cross-Encoder scoring)")
    print(f"  합계       : {fmt(total_bge_ms)}")

    # ── [4] Warm run N회 반복 ─────────────────────────────
    print_section(f"[4] Warm run {n_runs}회 반복 (모델 상주 상태)")
    warm_times = []
    for i in range(n_runs):
        t0 = time.perf_counter()
        bge_rerank(search_candidates=hybrid_results, rag_query=rag_query)
        elapsed = (time.perf_counter() - t0) * 1000
        warm_times.append(elapsed)
        print(f"  run {i+1}       : {fmt(elapsed)}")

    avg_warm = sum(warm_times) / len(warm_times)
    min_warm = min(warm_times)
    max_warm = max(warm_times)
    print(f"  평균       : {fmt(avg_warm)}")
    print(f"  최소/최대  : {fmt(min_warm)} / {fmt(max_warm)}")

    # ── top5 결과 ─────────────────────────────────────────
    print_section("리랭킹 결과 top5")
    for b in reranked[:5]:
        orig = b.get("original_rank") or b.get("rank", "?")
        print(f"  {b['final_rank']}위 (검색{orig:>2}위)  "
              f"{b.get('title', '')[:30]:<30}  "
              f"bge={b['bge_score']:.3f}  final={b['final_score']:.3f}")

    # ── 최종 요약 ─────────────────────────────────────────
    total_cold = hybrid_ms + cold_ms + total_bge_ms
    total_warm = hybrid_ms + avg_warm

    print(f"\n{'='*58}")
    print(f"  최종 요약")
    print(f"{'='*58}")
    print(f"  [Cold start — 서버 최초 요청]")
    print(f"    Hybrid Search  : {fmt(hybrid_ms)}")
    print(f"    BGE 모델 로드  : {fmt(cold_ms)}  (1회성)")
    print(f"    BGE 추론       : {fmt(total_bge_ms)}")
    print(f"    합계           : {fmt(total_cold)}  ({total_cold/1000:.2f}s)")
    print()
    print(f"  [Warm — 정상 서비스 상황]")
    print(f"    Hybrid Search  : {fmt(hybrid_ms)}")
    print(f"    BGE 추론 (평균): {fmt(avg_warm)}")
    print(f"    합계           : {fmt(total_warm)}  ({total_warm/1000:.2f}s)")
    print(f"{'='*58}")


# ── 진입점 ────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BGE-BD 파이프라인 레이턴시 벤치마크")
    parser.add_argument("--runs", type=int, default=3, help="warm run 반복 횟수 (기본 3)")
    args = parser.parse_args()

    run_benchmark(rag_query=DEFAULT_RAG_QUERY, n_runs=args.runs)
