"""
정보나루 Open API - 도서관 소장 및 대출가능 여부 조회 모듈

정보나루 API #11 bookExist 를 사용해 특정 도서관의 ISBN 별 소장/대출 가능 여부를 확인한다.

환경변수:
    NARU_API_KEY  : 정보나루 인증키 (필수)
    NARU_LIB_CODE : 도서관코드 (필수, 예: 111003)
"""

import os
from typing import Any, Dict, List, Optional

import requests

BOOK_EXIST_URL = "http://data4library.kr/api/bookExist"


# --------------------------------------------------
# 1. 단건 조회
# --------------------------------------------------

def check_loan_availability(
    isbn: str,
    lib_code: str,
    auth_key: str,
) -> Dict[str, Any]:
    """
    정보나루 bookExist API로 단일 ISBN 의 소장/대출 가능 여부를 조회한다.

    반환 예시:
    {
        "isbn": "9788937473135",
        "has_book": "Y",
        "loan_available": "N"
    }

    대출가능 여부(loanAvailable)는 전일 기준임에 유의.
    """
    params = {
        "authKey": auth_key,
        "libCode": lib_code,
        "isbn13": isbn,
        "format": "json",
    }

    try:
        resp = requests.get(BOOK_EXIST_URL, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        result = data.get("result", {})
        return {
            "isbn": isbn,
            "has_book": result.get("hasBook", "N"),
            "loan_available": result.get("loanAvailable", "N"),
        }
    except requests.RequestException as exc:
        return {
            "isbn": isbn,
            "has_book": "ERROR",
            "loan_available": "ERROR",
            "error": str(exc),
        }


# --------------------------------------------------
# 2. 배치 조회
# --------------------------------------------------

def check_books_availability(
    isbns: List[str],
    lib_code: str,
    auth_key: str,
) -> Dict[str, Dict[str, Any]]:
    """
    ISBN 목록에 대해 일괄로 대출 가능 여부를 조회한다.

    반환 예시:
    {
        "9788937473135": {"isbn": "...", "has_book": "Y", "loan_available": "N"},
        ...
    }
    """
    availability_index: Dict[str, Dict[str, Any]] = {}
    for isbn in isbns:
        availability_index[isbn] = check_loan_availability(isbn, lib_code, auth_key)
    return availability_index


# --------------------------------------------------
# 3. 결과 출력 헬퍼
# --------------------------------------------------

def print_results_with_availability(
    reranked_books: List[Dict[str, Any]],
    availability_index: Dict[str, Dict[str, Any]],
    top_n: Optional[int] = None,
) -> None:
    """재정렬된 도서 목록과 대출 가능 여부를 함께 출력한다."""
    books = reranked_books[:top_n] if top_n else reranked_books

    print(f"\n{'='*60}")
    print(f"  최종 추천 도서 (TOP {len(books)})")
    print(f"{'='*60}")

    for book in books:
        isbn = book.get("isbn", "")
        avail = availability_index.get(isbn, {})

        has_book = avail.get("has_book", "-")
        loan_available = avail.get("loan_available", "-")

        if avail.get("error"):
            avail_str = "조회 실패"
        elif has_book == "Y":
            avail_str = "대출 가능" if loan_available == "Y" else "대출 불가 (소장 중)"
        else:
            avail_str = "미소장"

        print(f"  [{book.get('final_rank', '-')}위]  {book.get('title', '(제목 없음)')}")
        print(f"       저자   : {book.get('author', '-')}")
        print(f"       출판사 : {book.get('publisher', '-')}")
        print(f"       분류   : {book.get('category', '-')}")
        print(f"       ISBN   : {isbn}")
        print(f"       최종점수: {book.get('final_score', '-')}")
        print(f"       대출현황: {avail_str}")
        print()


# --------------------------------------------------
# 4. 실행 예시
# --------------------------------------------------

if __name__ == "__main__":
    import json
    import psycopg2
    from pathlib import Path
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).parents[2] / ".env")  # backend/.env

    from backend.app.models.clova_reranker import (
        call_clova_reranker,
        create_payload_and_rerank,
    )

    auth_key = os.getenv("NARU_API_KEY")
    lib_code = os.getenv("NARU_LIB_CODE")

    if not auth_key or not lib_code:
        print("NARU_API_KEY 와 NARU_LIB_CODE 환경변수를 설정하세요.")
        print("예:\n  export NARU_API_KEY=<your_key>")
        print("  export NARU_LIB_CODE=111003  # 국립중앙도서관")
        raise SystemExit(1)

    # 1. 재구성된 세션 데이터 (샘플)
    reconstructed_session = {
        "keyword_query": ["SF", "소설", "재미", "가벼운", "힐링"],
        "semantic_query": "지친 일상에서 가볍고 재미있게 읽을 수 있는 SF 소설",
        "filters": {"coarse_category": "과학/기술"},
        "score_boost": {"fine_category": "SF", "subject": "우주 탐험"},
    }

    # 2. DB에서 샘플 ISBN 10개 조회
    with psycopg2.connect(
        dbname=os.getenv("POSTGRES_DB", "libraian"),
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        user=os.getenv("POSTGRES_USER", os.getenv("USER", "")),
    ) as _conn:
        with _conn.cursor() as _cur:
            _cur.execute("SELECT isbn FROM books LIMIT 10")
            sample_isbns = [row[0] for row in _cur.fetchall()]

    search_candidates = [
        {"rank": rank, "score": round(0.95 - rank * 0.04, 2), "isbn": isbn}
        for rank, isbn in enumerate(sample_isbns, start=1)
    ]

    # 3. CLOVA Reranker payload 준비
    prepared = create_payload_and_rerank(
        reconstructed_session=reconstructed_session,
        search_candidates=search_candidates,
        clova_response=None,
    )

    # 4. CLOVA API 호출 (없으면 검색 점수 기준 순위만 사용)
    clova_api_key = os.getenv("CLOVA_API_KEY")  # .env: CLOVA_API_KEY
    if clova_api_key:
        clova_response = call_clova_reranker(
            payload=prepared["clova_payload"],
            api_key=clova_api_key,
        )
        final_result = create_payload_and_rerank(
            reconstructed_session=reconstructed_session,
            search_candidates=search_candidates,
            clova_response=clova_response,
        )
        reranked_books = final_result["reranked_books"]
    else:
        print("\nCLOVA_API_KEY 없음 — 검색 점수 순위 기준으로 진행합니다.")
        reranked_books = [
            {
                "isbn": c["isbn"],
                "title": prepared["candidate_books"][i]["book"].get("title"),
                "author": prepared["candidate_books"][i]["book"].get("author"),
                "publisher": prepared["candidate_books"][i]["book"].get("publisher"),
                "category": prepared["candidate_books"][i]["book"].get("category"),
                "final_rank": c["rank"],
                "final_score": c["score"],
            }
            for i, c in enumerate(search_candidates)
        ]

    # 5. 정보나루 대출 가능 여부 조회
    top3_books = reranked_books[:3]
    top3_isbns = [b["isbn"] for b in top3_books]

    print("\n정보나루 API로 대출 가능 여부 조회 중...")
    availability_index = check_books_availability(top3_isbns, lib_code, auth_key)

    # 6. 결과 출력
    print_results_with_availability(top3_books, availability_index)
