"""
CLOVA Reranker 입력 데이터 생성 및 결과 재정렬 모듈

역할:
1. 재구성된 세션 데이터와 검색 후보 {rank, score, isbn}을 입력받는다.
2. ISBN으로 PostgreSQL DB에서 도서 메타데이터를 조회한다.
3. CLOVA Reranker API에 넣을 query + documents payload를 만든다.
4. CLOVA Reranker 응답에서 문서별 score 또는 citedDocuments를 추출한다.
5. relevance score 기준으로 후보 도서를 재정렬한다.

주의:
- CLOVA Reranker API가 문서별 relevance_score를 직접 반환하지 않는 경우,
  citedDocuments에 포함된 도서만 clova_relevance_score=1.0으로 처리한다.
"""

import json
import os
import uuid
from typing import Any, Dict, List, Optional

import psycopg2
import psycopg2.extras
import requests


CLOVA_RERANKER_URL = "https://clovastudio.stream.ntruss.com/v1/api-tools/reranker"


# --------------------------------------------------
# 1. 공통 유틸
# --------------------------------------------------


def normalize_score(value: float, min_value: float, max_value: float) -> float:
    """검색 점수를 0~1 범위로 정규화한다."""
    if max_value == min_value:
        return 1.0
    return (value - min_value) / (max_value - min_value)


# --------------------------------------------------
# 2. PostgreSQL ISBN 조회
# --------------------------------------------------

def fetch_books_by_isbn(isbns: List[str]) -> Dict[str, Dict[str, Any]]:
    """
    ISBN 목록으로 PostgreSQL books 테이블에서 도서 메타데이터를 조회한다.

    반환 예시:
    {
        "9788937473135": {
            "isbn": "9788937473135",
            "title": "...",
            "author": "...",
            "category": "소설",
            ...
        }
    }
    """
    conn_kwargs: Dict[str, Any] = {
        "dbname": os.getenv("POSTGRES_DB", "book_db"),
        "host": os.getenv("POSTGRES_HOST", "localhost"),
        "port": os.getenv("POSTGRES_PORT", "5432"),
        "user": os.getenv("POSTGRES_USER", os.getenv("USER", "parkdahyeon")),
    }
    password = os.getenv("POSTGRES_PASSWORD", "")
    if password:
        conn_kwargs["password"] = password

    with psycopg2.connect(**conn_kwargs) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT isbn, title, author, publisher, publish_date,
                       page, book_intro, large_cate, book_index
                FROM books
                WHERE isbn = ANY(%s)
                """,
                (isbns,),
            )
            rows = cur.fetchall()

    book_index = {}
    for row in rows:
        book = dict(row)
        book["category"] = ", ".join(book.pop("large_cate") or [])
        book["publish_date"] = str(book["publish_date"]) if book["publish_date"] else ""
        book_index[book["isbn"]] = book

    return book_index


def attach_book_metadata(
    search_candidates: List[Dict[str, Any]],
    book_index: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    검색 후보 {rank, score, isbn}에 책 메타데이터를 붙인다.

    검색 후보 예시:
    [
        {"rank": 1, "score": 0.91, "isbn": "9788937473135"}
    ]
    """
    results = []

    for candidate in search_candidates:
        isbn = str(candidate.get("isbn") or "").strip()
        results.append({
            **candidate,
            "isbn": isbn,
            "book": book_index[isbn],
        })

    return results


# --------------------------------------------------
# 3. CLOVA Reranker query/documents 생성
# --------------------------------------------------

def build_clova_query(reconstructed_session: Dict[str, Any]) -> str:
    """
    재구성된 세션 데이터를 CLOVA Reranker query 문자열로 변환한다.

    입력 예시:
    {
        "keyword_query": ["SF", "소설", "재미", "가벼운"],
        "semantic_query": "지친 일상에서 가볍고 재미있게 읽을 수 있는 SF 소설",
        "filters": {"coarse_category": "과학/기술"},
        "score_boost": {"fine_category": "SF", "subject": "우주 탐험"}
    }
    """
    keyword_query = reconstructed_session.get("keyword_query", [])
    semantic_query = reconstructed_session.get("semantic_query", "")
    filters = reconstructed_session.get("filters", {})
    score_boost = reconstructed_session.get("score_boost", {})

    query_parts = []

    if semantic_query:
        query_parts.append(f"사용자 요청: {semantic_query}")

    if keyword_query:
        query_parts.append(f"핵심 키워드: {', '.join(keyword_query)}")

    if filters.get("coarse_category"):
        query_parts.append(f"검색 대분류: {filters['coarse_category']}")

    if score_boost.get("fine_category"):
        query_parts.append(f"선호 세부 장르: {score_boost['fine_category']}")

    if score_boost.get("subject"):
        query_parts.append(f"관심 소재: {score_boost['subject']}")

    return "\n".join(query_parts)


def build_document_text(book: Dict[str, Any], rank: Any, score: Any) -> str:
    """
    책 메타데이터를 CLOVA Reranker에 넣을 document 텍스트로 변환한다.

    너무 길어지지 않도록 MVP에서는 핵심 필드만 사용한다.
    """
    return f"""
            도서명: {book.get("title", "")}
            저자: {book.get("author", "")}
            출판사: {book.get("publisher", "")}
            출간일: {book.get("publish_date", "")}
            카테고리: {book.get("category", "")}
            페이지: {book.get("page", "")}
            책 소개: {book.get("book_intro", "")}
            목차: {book.get("book_index", "")}
            검색 순위: {rank}
            검색 점수: {score}
            """.strip()


def build_clova_documents(candidate_books: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """
    후보 도서를 CLOVA Reranker documents 형식으로 변환한다.

    document id에 ISBN을 반드시 포함한다.
    그래야 CLOVA 응답의 citedDocuments를 다시 ISBN으로 매핑할 수 있다.
    """
    documents = []

    for item in candidate_books:
        isbn = item["isbn"]
        rank = item.get("rank")
        score = item.get("score")
        book = item["book"]

        documents.append({
            "id": f"{isbn}__rank_{rank}",
            "doc": build_document_text(book, rank, score),
        })

    return documents


def prepare_clova_payload(
    reconstructed_session: Dict[str, Any],
    candidate_books: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    CLOVA Reranker API에 전달할 최종 payload를 만든다.

    API 호출 예시 기준 request body에는 query와 documents만 전달한다.
    """
    return {
        "documents": build_clova_documents(candidate_books),
        "query": build_clova_query(reconstructed_session),
    }


# --------------------------------------------------
# 4. CLOVA Reranker API 호출
# --------------------------------------------------

def call_clova_reranker(
    payload: Dict[str, Any],
    api_key: str,
    request_id: Optional[str] = None,
    api_url: str = CLOVA_RERANKER_URL,
) -> Dict[str, Any]:
    """
    CLOVA Reranker API를 호출한다.

    curl 예시:
      POST https://clovastudio.stream.ntruss.com/v1/api-tools/reranker
      Authorization: Bearer {API Key}
      X-NCP-CLOVASTUDIO-REQUEST-ID: {Request ID}
      Content-Type: application/json
    """
    if not api_key:
        raise ValueError("CLOVA Reranker API key is required.")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "X-NCP-CLOVASTUDIO-REQUEST-ID": request_id or str(uuid.uuid4()),
        "Content-Type": "application/json",
    }

    response = requests.post(api_url, headers=headers, json=payload, timeout=60)
    response.raise_for_status()

    return response.json()


# --------------------------------------------------
# 5. CLOVA 응답에서 relevance score 추출
# --------------------------------------------------

def extract_isbn_from_doc_id(doc_id: str) -> str:
    """
    document id에서 ISBN을 추출한다.

    예:
    "9788937473135__rank_1" -> "9788937473135"
    """
    return str(doc_id.split("__")[0]).strip()


def extract_clova_scores(clova_response: Dict[str, Any]) -> Dict[str, float]:
    """
    CLOVA Reranker 응답에서 ISBN별 relevance score를 추출한다.

    처리 우선순위:
    1. 응답에 문서별 score/relevance_score가 있으면 해당 값을 사용
    2. score가 없으면 citedDocuments에 포함된 ISBN에 1.0 부여
    """
    result = clova_response.get("result", {})

    # case 1: 혹시 응답에 scored documents 형태가 있는 경우를 대비
    scored_docs = (
        result.get("documents")
        or result.get("rankedDocuments")
        or result.get("rerankedDocuments")
        or []
    )

    scores = {}

    for doc in scored_docs:
        doc_id = doc.get("id", "")
        isbn = extract_isbn_from_doc_id(doc_id)

        raw_score = (
            doc.get("relevance_score")
            or doc.get("relevanceScore")
            or doc.get("score")
        )

        if isbn and raw_score is not None:
            scores[isbn] = float(raw_score)

    if scores:
        return scores

    # case 2: 공식 응답의 citedDocuments 기반 fallback
    cited_docs = result.get("citedDocuments", [])

    for doc in cited_docs:
        doc_id = doc.get("id", "")
        isbn = extract_isbn_from_doc_id(doc_id)

        if isbn:
            scores[isbn] = 1.0

    return scores


# --------------------------------------------------
# 6. CLOVA score로 최종 재정렬
# --------------------------------------------------

def rerank_by_clova_score(
    candidate_books: List[Dict[str, Any]],
    clova_scores: Dict[str, float],
    retrieval_weight: float = 0.0,
    clova_weight: float = 1.0,
) -> Dict[str, Any]:
    """
    검색 점수와 CLOVA relevance score를 결합해 최종 재정렬한다.

    final_score =
        retrieval_weight * normalized_retrieval_score
      + clova_weight * clova_relevance_score
    """
    raw_scores = [float(item.get("score", 0)) for item in candidate_books]

    if raw_scores:
        min_score = min(raw_scores)
        max_score = max(raw_scores)
    else:
        min_score = max_score = 0.0

    reranked_books = []

    for item in candidate_books:
        isbn = item["isbn"]
        book = item["book"]

        raw_retrieval_score = float(item.get("score", 0))
        retrieval_score = normalize_score(raw_retrieval_score, min_score, max_score)
        clova_relevance_score = clova_scores.get(isbn, 0.0)

        final_score = (
            retrieval_weight * retrieval_score
            + clova_weight * clova_relevance_score
        )

        reranked_books.append({
            "isbn": isbn,
            "title": book.get("title"),
            "author": book.get("author"),
            "publisher": book.get("publisher"),
            "category": book.get("category"),
            "page": book.get("page"),
            "original_rank": item.get("rank"),
            "raw_retrieval_score": raw_retrieval_score,
            "retrieval_score": round(retrieval_score, 4),
            "clova_relevance_score": round(clova_relevance_score, 4),
            "final_score": round(final_score, 4),
            "evidence": make_evidence(clova_relevance_score),
        })

    reranked_books.sort(key=lambda x: x["final_score"], reverse=True)

    for idx, book in enumerate(reranked_books, start=1):
        book["final_rank"] = idx

    return {
        "reranked_books": reranked_books,
        "meta": {
            "candidate_count": len(candidate_books),
            "reranked_count": len(reranked_books),
            "retrieval_weight": retrieval_weight,
            "clova_weight": clova_weight,
        }
    }


def make_evidence(clova_relevance_score: float) -> List[str]:
    """Generation 단계에서 사용할 간단한 추천 근거를 만든다."""
    if clova_relevance_score >= 1.0:
        return ["CLOVA Reranker가 사용자 요청과 관련 있는 문서로 선택함"]
    if clova_relevance_score > 0:
        return ["CLOVA Reranker 관련성 점수가 일부 반영됨"]
    return []


# --------------------------------------------------
# 7. 전체 파이프라인 함수
# --------------------------------------------------

def create_payload_and_rerank(
    reconstructed_session: Dict[str, Any],
    search_candidates: List[Dict[str, Any]],
    clova_response: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    샘플 입력 데이터 생성부터 CLOVA 응답 기반 재정렬까지 수행한다.

    이 함수는 두 가지 용도로 쓸 수 있다.

    1. clova_response=None:
       - CLOVA API 호출 전 payload 생성 결과만 확인

    2. clova_response=dict:
       - 이미 받은 CLOVA 응답을 넣고 최종 reranking 결과 확인
    """
    isbns = [str(c.get("isbn", "")).strip() for c in search_candidates]
    book_index = fetch_books_by_isbn(isbns)

    candidate_books = attach_book_metadata(
        search_candidates=search_candidates,
        book_index=book_index,
    )

    payload = prepare_clova_payload(
        reconstructed_session=reconstructed_session,
        candidate_books=candidate_books,
    )

    if clova_response is None:
        return {
            "clova_payload": payload,
            "candidate_books": candidate_books,
            "message": "CLOVA API 호출 전 payload 생성까지만 완료됨",
        }

    clova_scores = extract_clova_scores(clova_response)

    reranked_result = rerank_by_clova_score(
        candidate_books=candidate_books,
        clova_scores=clova_scores,
    )

    return {
        "clova_payload": payload,
        "clova_scores": clova_scores,
        **reranked_result,
    }


# --------------------------------------------------
# 8. 실행 예시
# --------------------------------------------------

if __name__ == "__main__":
    from pathlib import Path
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parents[2] / ".env")  # backend/.env

    # 1. 재구성된 세션 데이터
    reconstructed_session = {
        "keyword_query": ["SF", "소설", "재미", "가벼운", "힐링"],
        "semantic_query": "지친 일상에서 가볍고 재미있게 읽을 수 있는 SF 소설",
        "filters": {
            "coarse_category": "과학/기술",
            "availability": None,
        },
        "score_boost": {
            "fine_category": "SF",
            "subject": "우주 탐험",
        },
    }

    # 2. 검색 후보 output (DB에서 샘플 ISBN 10개 조회)
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

    # 3. CLOVA API 호출 전 payload 생성
    prepared = create_payload_and_rerank(
        reconstructed_session=reconstructed_session,
        search_candidates=search_candidates,
        clova_response=None,
    )

    # print("\n=== CLOVA Reranker Payload ===")
    # print(json.dumps(prepared["clova_payload"], ensure_ascii=False, indent=2))

    # 4. 실제 API 호출 예시
    api_key = os.getenv("CLOVA_API_KEY")
    if not api_key:
        print("\nCLOVA_API_KEY가 없어 실제 API 호출은 건너뜁니다.")
        raise SystemExit(0)

    clova_response = call_clova_reranker(
        payload=prepared["clova_payload"],
        api_key=api_key,
    )

    final_result = create_payload_and_rerank(
        reconstructed_session=reconstructed_session,
        search_candidates=search_candidates,
        clova_response=clova_response,
    )
    
    print("\n=== Final Reranked Result (TOP 3) ===")
    print(json.dumps(final_result["reranked_books"][:3], ensure_ascii=False, indent=2))
