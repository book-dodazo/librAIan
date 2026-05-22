"""
book_text variant 포맷 함수 (reranker 입력 문서 텍스트 생성)

각 함수는 candidate dict를 받아 문자열을 반환한다.
candidate dict에는 gold_candidate_pool.json의 모든 필드가 포함되어 있으며,
retrieval_rank, retrieval_score 필드도 포함된다 (Variant D, E에서 사용).
"""


def _cat(book: dict) -> str:
    cats = book.get("large_cate", []) + book.get("mid_cate", [])
    return " > ".join(cats) if cats else ""


def format_a(book: dict) -> str:
    """Baseline: 도서명 + 카테고리 + 책소개"""
    return (
        f"도서명: {book.get('title', '')}\n"
        f"카테고리: {_cat(book)}\n"
        f"책소개: {book.get('book_intro', '')}"
    )


def format_b(book: dict) -> str:
    """A + 목차(book_index): 구체적 내용 정보 추가 효과 확인"""
    return format_a(book) + f"\n목차: {book.get('book_index', '')}"


def format_c(book: dict) -> str:
    """A + 저자 + 출판사: 메타 정보가 판단에 도움이 되는지 확인"""
    return (
        format_a(book)
        + f"\n저자: {book.get('author', '')}"
        + f"\n출판사: {book.get('publisher', '')}"
    )


def format_d(book: dict) -> str:
    """A + 검색순위 + 검색점수: retrieval 신호 노출 시 역효과 여부 확인"""
    rank = book.get("retrieval_rank", "")
    score = book.get("retrieval_score", "")
    score_str = f"{score:.4f}" if isinstance(score, float) else str(score)
    return (
        format_a(book)
        + f"\n검색순위: {rank}"
        + f"\n검색점수: {score_str}"
    )


def format_e(book: dict) -> str:
    """전체 필드: 현재 운영 기준"""
    cats = book.get("large_cate", []) + book.get("mid_cate", []) + book.get("small_cate", [])
    rank = book.get("retrieval_rank", "")
    score = book.get("retrieval_score", "")
    score_str = f"{score:.4f}" if isinstance(score, float) else str(score)
    return (
        f"도서명: {book.get('title', '')}\n"
        f"저자: {book.get('author', '')}\n"
        f"출판사: {book.get('publisher', '')}\n"
        f"카테고리: {' > '.join(cats)}\n"
        f"책소개: {book.get('book_intro', '')}\n"
        f"목차: {book.get('book_index', '')}\n"
        f"리뷰: {book.get('review_text', '')}\n"
        f"검색순위: {rank}\n"
        f"검색점수: {score_str}"
    )


VARIANTS: dict[str, callable] = {
    "A": format_a,
    "B": format_b,
    "C": format_c,
    "D": format_d,
    "E": format_e,
}

VARIANT_DESC = {
    "A": "도서명 + 카테고리 + 책소개 (baseline)",
    "B": "A + 목차",
    "C": "A + 저자 + 출판사",
    "D": "A + 검색순위 + 검색점수",
    "E": "전체 필드 (현재 운영)",
}
