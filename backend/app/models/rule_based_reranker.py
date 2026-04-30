from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any


Book = dict[str, Any]
Candidate = dict[str, Any]


PURPOSE_KEYWORDS = {
    "위로": ["위로", "회복", "쉼", "마음", "따뜻", "힐링", "치유", "공감"],
    "학습": ["입문", "기초", "개념", "학습", "공부", "이해", "교양"],
    "재미": ["재미", "흥미", "모험", "추리", "유머", "이야기"],
    "정보": ["정보", "실용", "가이드", "방법", "전략", "지식"],
}

MOOD_KEYWORDS = {
    "따뜻한": ["따뜻", "위로", "공감", "다정", "마음"],
    "차분한": ["차분", "쉼", "명상", "고요", "평온"],
    "유쾌한": ["유쾌", "유머", "재미", "웃음"],
    "진지한": ["진지", "성찰", "철학", "깊이"],
}

GENRE_ALIASES = {
    "에세이": ["에세이", "산문"],
    "인문": ["인문", "철학", "심리", "역사"],
    "소설": ["소설", "문학"],
    "자기계발": ["자기계발", "성공", "습관"],
}


def text_of(book: Book) -> str:
    # 도서의 여러 텍스트 필드를 하나로 합쳐 매칭에 사용한다.
    fields = ["title", "category", "book_intro", "book_index", "review_summary"]
    return " ".join(str(book.get(field, "")) for field in fields).lower()


def count_matches(text: str, keywords: list[str]) -> int:
    # 키워드가 텍스트에 등장한 횟수를 센다.
    return sum(1 for word in keywords if word and word.lower() in text)


def clamp(value: float) -> float:
    # 점수를 0~1 범위로 제한한다.
    return max(0.0, min(1.0, value))


def normalize_retrieval_scores(candidates: list[Candidate]) -> dict[str, float]:
    # 검색 점수를 후보 목록 안에서 min-max 정규화한다.
    scores = [float(c.get("retrieval_score") or 0) for c in candidates]
    low, high = min(scores, default=0.0), max(scores, default=0.0)
    if high == low:
        return {str(c.get("isbn", "")): 1.0 for c in candidates}
    return {
        str(c.get("isbn", "")): (float(c.get("retrieval_score") or 0) - low) / (high - low)
        for c in candidates
    }


def score_purpose(book: Book, purpose: str | None) -> float:
    # 독서 목적별 키워드와 도서 텍스트의 일치도를 계산한다.
    if not purpose:
        return 0.0
    text = text_of(book)
    keywords = PURPOSE_KEYWORDS.get(purpose, [purpose])
    matched = count_matches(text, keywords)
    if purpose.lower() in text or matched >= 3:
        return 1.0
    if matched >= 2:
        return 0.7
    if matched == 1:
        return 0.4
    return 0.0


def score_topic(book: Book, topics: list[str]) -> float:
    # topic 키워드가 소개/목차/리뷰 요약에 얼마나 등장하는지 계산한다.
    if not topics:
        return 0.0
    text = text_of(book)
    return clamp(count_matches(text, topics) / len(topics))


def score_genre(book: Book, genre: str | None) -> float:
    # 사용자 장르와 도서 카테고리의 직접/관련 매칭을 계산한다.
    if not genre:
        return 0.0
    category = str(book.get("category", "")).lower()
    genre_lower = genre.lower()
    if genre_lower in category:
        return 1.0
    if any(alias.lower() in category for alias in GENRE_ALIASES.get(genre, [])):
        return 0.7
    return 0.0


def score_level(book: Book, level: str | None) -> float:
    # 페이지 수와 쉬운/어려운 문체 힌트로 난이도 적합도를 계산한다.
    page = int(book.get("page") or 0)
    text = text_of(book)
    easy_hint = count_matches(text, ["쉽게", "입문", "기초", "가볍", "편하게"])
    hard_hint = count_matches(text, ["전문", "심층", "이론", "철학", "학술"])

    estimated = "medium"
    if page and page <= 220 or easy_hint > hard_hint:
        estimated = "easy"
    if page >= 450 or hard_hint > easy_hint:
        estimated = "hard"

    if level == estimated:
        return 1.0
    if level == "medium" or estimated == "medium":
        return 0.7
    return 0.4


def score_mood(book: Book, moods: list[str]) -> float:
    # 분위기별 키워드와 도서 텍스트의 일치도를 계산한다.
    if not moods:
        return 0.0
    text = text_of(book)
    scores = []
    for mood in moods:
        keywords = MOOD_KEYWORDS.get(mood, [mood])
        scores.append(clamp(count_matches(text, keywords) / max(len(keywords), 1)))
    return max(scores, default=0.0)


def score_onboarding(book: Book, onboarding: Book) -> float:
    # 온보딩의 선호 카테고리와 선호 분량을 낮은 비중의 보조 점수로 계산한다.
    category = str(book.get("category", "")).lower()
    preferred = onboarding.get("preferred_categories") or []
    category_score = 1.0 if any(str(c).lower() in category for c in preferred) else 0.0

    page = int(book.get("page") or 0)
    length = onboarding.get("preferred_length")
    length_score = 0.0
    if length == "short":
        length_score = 1.0 if page <= 220 else 0.4
    elif length == "medium":
        length_score = 1.0 if 180 <= page <= 420 else 0.5
    elif length == "long":
        length_score = 1.0 if page >= 350 else 0.4

    return 0.6 * category_score + 0.4 * length_score


def score_dislike(book: Book, session_slots: Book, onboarding: Book) -> float:
    # 세션/온보딩의 비선호 키워드가 도서 텍스트에 포함되면 감점한다.
    dislikes = (session_slots.get("dislikes") or []) + (onboarding.get("disliked_keywords") or [])
    return 1.0 if count_matches(text_of(book), [str(x) for x in dislikes]) else 0.0


def score_availability(isbn: str, availability_results: dict[str, list[Book]]) -> tuple[float, Book]:
    # 도서관 API 결과를 대출 가능성 점수와 표시용 상태로 변환한다.
    results = availability_results.get(isbn)
    if not results:
        return 0.3, {"status": "API 결과 없음", "library": None}

    best_score, best = 0.0, results[0]
    for item in results:
        if item.get("loanAvailable"):
            score, status = 1.0, "대출 가능"
        elif item.get("reservationAvailable"):
            score, status = 0.7, "예약 가능"
        elif item.get("hasBook"):
            score, status = 0.5, "소장 중"
        else:
            score, status = 0.0, "소장 없음"
        if score > best_score:
            best_score, best = score, {**item, "status": status}

    return best_score, {"status": best.get("status", "소장 없음"), "library": best}


def score_popularity(book: Book) -> float:
    # 리뷰 수, 평점, 대출 수를 0~1 범위의 참고용 인기도 점수로 계산한다.
    review_count = math.log1p(float(book.get("review_count") or 0)) / math.log1p(1000)
    total_score = float(book.get("total_score") or 0) / 5
    loan_count = math.log1p(float(book.get("loanCnt") or 0)) / math.log1p(5000)
    return clamp(0.35 * review_count + 0.35 * total_score + 0.30 * loan_count)


def evidence_for(scores: Book, availability: Book) -> list[str]:
    # 상위 노출 결과를 설명할 간단한 근거 문장을 만든다.
    evidence = []
    if scores["session_fit_score"] >= 0.7:
        evidence.append("사용자의 독서 목적과 관심사에 잘 맞음")
    if scores["level_match"] >= 0.8:
        evidence.append("원하는 난이도에 적합함")
    if scores["mood_match"] >= 0.5:
        evidence.append("요청한 분위기와 잘 어울림")
    if availability["status"] == "대출 가능":
        evidence.append("선택한 도서관에서 현재 대출 가능함")
    if scores["dislike_penalty"] > 0:
        evidence.append("비선호 키워드가 포함되어 감점됨")
    return evidence


def rerank_books(
    candidates: list[Candidate],
    session_slots: Book,
    onboarding: Book,
    book_metadata: dict[str, Book],
    availability_results: dict[str, list[Book]],
    top_n: int = 10,
) -> Book:
    # 후보 도서별 feature를 계산한 뒤 final_score 기준으로 재정렬한다.
    normalized_scores = normalize_retrieval_scores(candidates)
    reranked = []

    for candidate in candidates:
        isbn = str(candidate.get("isbn", ""))
        book = book_metadata.get(isbn, {})
        availability_score, availability = score_availability(isbn, availability_results)

        purpose = score_purpose(book, session_slots.get("purpose"))
        topic = score_topic(book, [str(x) for x in session_slots.get("topic", [])])
        genre = score_genre(book, session_slots.get("genre"))
        session_fit = 0.4 * purpose + 0.4 * topic + 0.2 * genre
        level = score_level(book, session_slots.get("level"))
        mood = score_mood(book, [str(x) for x in session_slots.get("mood", [])])
        onboarding_score = score_onboarding(book, onboarding)
        dislike = score_dislike(book, session_slots, onboarding)

        detail = {
            "retrieval_score": normalized_scores.get(isbn, 0.0),
            "purpose_match": purpose,
            "topic_match": topic,
            "genre_match": genre,
            "session_fit_score": session_fit,
            "level_match": level,
            "mood_match": mood,
            "onboarding_match": onboarding_score,
            "availability_score": availability_score,
            "popularity_score": score_popularity(book),
            "dislike_penalty": dislike,
        }
        final_score = (
            0.30 * detail["retrieval_score"]
            + 0.25 * detail["session_fit_score"]
            + 0.10 * detail["onboarding_match"]
            + 0.15 * detail["availability_score"]
            + 0.10 * detail["level_match"]
            + 0.10 * detail["mood_match"]
            - 0.30 * detail["dislike_penalty"]
        )

        reranked.append({
            "isbn": isbn,
            "title": book.get("title"),
            "author": book.get("author"),
            "publisher": book.get("publisher"),
            "category": book.get("category"),
            "page": book.get("page"),
            "original_rank": candidate.get("rank"),
            "final_score": round(clamp(final_score), 4),
            "score_detail": {k: round(v, 4) for k, v in detail.items()},
            "availability": availability,
            "evidence": evidence_for(detail, availability),
        })

    reranked.sort(key=lambda x: x["final_score"], reverse=True)
    for rank, book in enumerate(reranked, 1):
        book["final_rank"] = rank

    return {
        "reranked_books": reranked[:top_n],
        "meta": {
            "candidate_count": len(candidates),
            "reranked_count": len(reranked),
            "top_n": top_n,
        },
    }


def load_sample_inputs(limit: int = 20) -> tuple[list[Candidate], dict[str, Book]]:
    # 실제 JSON에서 샘플 후보와 메타데이터를 만든다.
    path = Path("data/books_sample_100000_page_date_updated.json")
    with path.open(encoding="utf-8") as f:
        rows = json.load(f)[:limit]

    candidates = []
    metadata = {}
    for rank, row in enumerate(rows, 1):
        isbn = str(row.get("isbn", ""))
        candidates.append({"isbn": isbn, "rank": rank, "retrieval_score": 21 - rank})
        category = " > ".join(row.get("cate_depth1") or [])
        metadata[isbn] = {
            "title": row.get("title"),
            "author": row.get("author"),
            "publisher": row.get("publisher"),
            "category": category,
            "page": row.get("page"),
            "book_intro": row.get("book_intro") or row.get("simple_intro"),
            "book_index": "",
            "review_summary": row.get("simple_intro", ""),
            "review_count": rank * 3,
            "total_score": 3.5 + (rank % 4) * 0.3,
            "loanCnt": 500 - rank * 10,
        }
    return candidates, metadata


if __name__ == "__main__":
    sample_candidates, sample_metadata = load_sample_inputs()
    sample_session_slots = {
        "purpose": "위로",
        "topic": ["번아웃", "마음 회복"],
        "genre": "에세이",
        "level": "easy",
        "mood": ["따뜻한", "차분한"],
        "dislikes": ["자기계발식 문체"],
    }
    sample_onboarding = {
        "preferred_categories": ["에세이", "인문"],
        "preferred_length": "medium",
        "disliked_keywords": ["잔인한 내용"],
        "selected_libraries": [{"library_name": "마포중앙도서관", "libCode": "111001"}],
    }
    sample_availability = {
        candidate["isbn"]: [{
            "libCode": "111001",
            "library_name": "마포중앙도서관",
            "hasBook": True,
            "loanAvailable": i % 3 == 0,
            "reservationAvailable": i % 3 == 1,
        }]
        for i, candidate in enumerate(sample_candidates)
    }

    result = rerank_books(
        sample_candidates,
        sample_session_slots,
        sample_onboarding,
        sample_metadata,
        sample_availability,
        top_n=10,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
