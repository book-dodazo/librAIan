import json
import uuid
import requests
import psycopg2
from psycopg2.extras import RealDictCursor
from app.core.config import settings

"""

Anchor Book Based Query Rewrite Pipeline

역할:

- sample 안의 anchor 정보를 읽는다.
- anchor가 book_title이면 해당 책을 DB에서 조회한다.
- anchor가 author이면 해당 작가의 책들을 DB에서 조회한다.
- 조회된 anchor 정보를 기반으로 HCX-007이 keyword_query와 semantic_query를 재작성한다.
- 재작성된 query를 기존 sample에 덮어쓴 결과를 반환한다.

사용 예시:

from app.modules.RAG.anchor_book_pipeline import run_anchor_pipeline

sample = {
    "semantic_query": "불안의 서처럼 실존주의적 주제를 다루는 사유하게 만드는 에세이",
    "anchor": {
        "value": "불안의 서",
        "type": "book_title"
    }
}

result = run_anchor_pipeline(sample)

입력 sample 필수 구조:
{
    "semantic_query": str,
    "anchor": {
        "value": str,
        "type": "book_title" 또는 "author"
    }
}

반환값:
- 기존 sample을 복사한 뒤,
  keyword_query와 semantic_query를 LLM 재작성 결과로 덮어쓴 dict
"""

# =========================================================
# CONFIG
# =========================================================

URL = "https://clovastudio.stream.ntruss.com/v3/chat-completions/HCX-007"
CLOVA_API_KEY = settings.CLOVA_API_KEY

DB_CONFIG = {
    "host": settings.DB_HOST,
    "database": "book_db_100000",
    "user": settings.DB_USER,
    "password": settings.DB_PASSWORD,
    "port": settings.DB_PORT
}


# =========================================================
# HCX
# =========================================================

def make_headers():
    return {
        "Authorization": f"Bearer {CLOVA_API_KEY}",
        "X-NCP-CLOVASTUDIO-REQUEST-ID": str(uuid.uuid4()),
        "Content-Type": "application/json",
        "Accept": "text/event-stream"
    }


def parse_hcx_response(text):

    if "event:" in text:
        last_data = None

        for block in text.split("\n\n"):

            lines = block.strip().splitlines()

            event_type = None
            data_text = None

            for line in lines:

                if line.startswith("event:"):
                    event_type = line.replace("event:", "").strip()

                elif line.startswith("data:"):
                    data_text = line.replace("data:", "").strip()

            if event_type == "result" and data_text:
                last_data = data_text

        if last_data is not None:
            data = json.loads(last_data)
            return data["message"]["content"]

    data = json.loads(text)

    if "result" in data:
        return data["result"]["message"]["content"]

    if "message" in data:
        return data["message"]["content"]

    raise ValueError(f"응답 파싱 실패:\n{text[:1000]}")


# =========================================================
# DB SEARCH
# =========================================================

def search_anchor_book(anchor: dict):

    anchor_value = anchor.get("value")
    anchor_type = anchor.get("type")

    if not anchor_value or not anchor_type:
        raise ValueError("anchor must contain value and type")

    conn = psycopg2.connect(
        host=DB_CONFIG["host"],
        database=DB_CONFIG["database"],
        user=DB_CONFIG["user"],
        password=DB_CONFIG["password"],
        port=DB_CONFIG["port"],
        cursor_factory=RealDictCursor
    )

    cur = conn.cursor()

    # -----------------------------------------------------
    # book title
    # -----------------------------------------------------

    if anchor_type == "book_title":

        query = """
        SELECT *
        FROM books
        WHERE LOWER(TRIM(title)) = LOWER(TRIM(%s))        
        LIMIT 1
        """

        cur.execute(query, (f"%{anchor_value}%",))

        result = cur.fetchone()

    # -----------------------------------------------------
    # author
    # -----------------------------------------------------

    elif anchor_type == "author":

        query = """
        SELECT *
        FROM books
        WHERE author ILIKE %s
        ORDER BY publish_date DESC
        LIMIT 5
        """

        cur.execute(query, (f"%{anchor_value}%",))

        result = cur.fetchall()

    else:

        cur.close()
        conn.close()

        raise ValueError(
            "anchor.type must be 'book_title' or 'author'"
        )

    cur.close()
    conn.close()

    return result


# =========================================================
# FORMAT CONTEXT
# =========================================================

def format_anchor_context(anchor_info, anchor_type):

    if not anchor_info:
        return None

    # -----------------------------------------------------
    # book title
    # -----------------------------------------------------

    if anchor_type == "book_title":

        book = anchor_info

        return {
            "anchor_type": "book_title",
            "title": book.get("title"),
            "author": book.get("author"),
            "publisher": book.get("publisher"),
            "publish_date": str(book.get("publish_date")),
            "page": book.get("page"),

            "categories": {
                "large_cate": book.get("large_cate"),
                "mid_cate": book.get("mid_cate"),
                "small_cate": book.get("small_cate"),
            },

            "book_intro": book.get("book_intro"),
            "review": book.get("review")
        }

    # -----------------------------------------------------
    # author
    # -----------------------------------------------------

    elif anchor_type == "author":

        books = anchor_info

        return {
            "anchor_type": "author",

            "books": [
                {
                    "title": book.get("title"),
                    "publisher": book.get("publisher"),
                    "publish_date": str(book.get("publish_date")),
                    "page": book.get("page"),
                    "categories": {
                        "large_cate": book.get("large_cate"),
                        "mid_cate": book.get("mid_cate"),
                        "small_cate": book.get("small_cate"),
                    },
                    "book_intro": book.get("book_intro"),
                    "review": book.get("review")
                }

                for book in books
            ]
        }


# =========================================================
# PROMPT
# =========================================================

def build_anchor_query_rewrite_prompt(
    user_query,
    anchor_context
):

    prompt = f"""
당신은 책 추천 RAG 시스템의 Query Rewriter이다.

사용자 요청과 anchor 정보를 바탕으로 검색에 사용할
keyword_query와 semantic_query를 생성하라.

[사용자 요청]
{user_query}

[Anchor 정보]
{json.dumps(anchor_context, ensure_ascii=False, indent=2)}

작업 목표:
1. 사용자가 anchor에서 어떤 요소를 기준으로 삼는지 판단한다.
2. 그 기준에 맞게 검색 가능한 표현으로 일반화한다.
3. BM25 검색용 keyword_query와 Dense 검색용 semantic_query만 생성한다.

비교 기준 판단 규칙:
- 사용자가 "분위기", "느낌", "톤", "감성", "몽환적", "어두운", "따뜻한" 등을 말하면
  → mood / tone / atmosphere 중심으로 쿼리를 만든다.
- 사용자가 "주제", "내용", "말하고자 하는 바", "메시지", "사상", "문제의식" 등을 말하면
  → theme / message / subject 중심으로 쿼리를 만든다.
- 사용자가 "문체", "스타일", "서술 방식", "작가 스타일" 등을 말하면
  → writing style / narrative style 중심으로 쿼리를 만든다.
- 사용자가 "실무에 적용", "현실적인", "도움 되는", "활용 가능한" 등을 말하면
  → practical value / use case 중심으로 쿼리를 만든다.
- 사용자가 명확한 기준을 말하지 않고 "비슷한 책"이라고만 하면
  → anchor 정보에서 핵심 장르, 주제, 분위기, 독서 경험을 종합해 쿼리를 만든다.

생성 규칙:
- semantic_query는 Dense retrieval에 사용할 자연어 문장 1개로 작성한다.
- keyword_query는 BM25 검색에 사용할 핵심 키워드 3~7개로 작성한다.
- 책 제목이나 작가명 자체에 의존하지 말고, 검색 가능한 일반화된 특징으로 바꾼다.
- anchor의 줄거리를 그대로 요약하지 말고, 추천 기준이 되는 특징을 추출한다.
- JSON만 출력한다.
- 설명 문장, 코드블럭은 출력하지 않는다.
- anchor에 포함된 책 제목, 작가 이름을 keyword_query와 semantic_query에 직접 포함하지 않는다.
- 고유명사(anchor title/author)를 검색어로 재사용하지 말고 일반화된 특징으로 변환한다.
- 특정 작품명/작가명이 없어도 retrieval 가능한 표현으로 바꾼다.

출력 형식:
{{
  "keyword_query": ["키워드1", "키워드2", "키워드3"],
  "semantic_query": "검색에 사용할 자연어 문장"
}}
"""

    return prompt


# =========================================================
# REMOVE ANCHOR TERMS
# =========================================================

def remove_anchor_terms(rag_query, anchor):

    banned_terms = [anchor["value"].lower()]
    banned_terms.extend(
        anchor["value"].lower().split()
    )
    rag_query["keyword_query"] = [
        kw for kw in rag_query["keyword_query"]
        if kw.lower() not in banned_terms
    ]
    semantic_query = rag_query["semantic_query"]

    for term in banned_terms:
        semantic_query = semantic_query.replace(term, "")

    rag_query["semantic_query"] = " ".join(
        semantic_query.split()
    )

    return rag_query


# =========================================================
# GENERATE RAG QUERY
# =========================================================

def generate_rag_query(
    user_query,
    anchor_context,
    anchor
):

    prompt = build_anchor_query_rewrite_prompt(
        user_query=user_query,
        anchor_context=anchor_context
    )

    body = {
        "messages": [
            {
                "role": "system",
                "content": (
                    "당신은 책 추천 검색 쿼리를 생성하는 "
                    "Query Rewriter이다. "
                    "반드시 JSON만 출력한다."
                )
            },
            {
                "role": "user",
                "content": prompt
            }
        ],

        "topP": 0.1,
        "topK": 0,
        "max_tokens": 300,
        "temperature": 0.0,
        "repetitionPenalty": 1.0,
        "includeAiFilters": False,
        "seed": 42
    }

    res = requests.post(
        URL,
        headers=make_headers(),
        json=body,
        timeout=60
    )

    if res.status_code != 200:

        print("status:", res.status_code)
        print("response:", res.text[:1000])

        raise RuntimeError("HCX 호출 실패")

    llm_text = parse_hcx_response(res.text)

    rag_query = json.loads(llm_text)

    rag_query = remove_anchor_terms(
        rag_query=rag_query,
        anchor=anchor
    )

    return rag_query


# =========================================================
# APPLY QUERY
# =========================================================

def apply_rewritten_query(sample, rag_query):

    updated = sample.copy()

    updated["keyword_query"] = rag_query.get(
        "keyword_query",
        sample.get("keyword_query")
    )

    updated["semantic_query"] = rag_query.get(
        "semantic_query",
        sample.get("semantic_query")
    )

    return updated

def run_anchor_pipeline(sample):

    anchor = sample.get("anchor")

    if not anchor:
        raise ValueError("sample must contain anchor")

    # -------------------------------------------------
    # 1. anchor 검색
    # -------------------------------------------------

    anchor_info = search_anchor_book(anchor)

    if not anchor_info:
        raise ValueError("anchor book not found")

    # -------------------------------------------------
    # 2. anchor context 생성
    # -------------------------------------------------

    anchor_context = format_anchor_context(
        anchor_info=anchor_info,
        anchor_type=anchor["type"]
    )

    # -------------------------------------------------
    # 3. rag query 생성
    # -------------------------------------------------

    rag_query = generate_rag_query(
        user_query=sample.get("semantic_query"),
        anchor_context=anchor_context,
        anchor=anchor
    )

    # -------------------------------------------------
    # 4. sample 덮어쓰기
    # -------------------------------------------------

    updated_sample = apply_rewritten_query(
        sample=sample,
        rag_query=rag_query
    )

    return updated_sample
