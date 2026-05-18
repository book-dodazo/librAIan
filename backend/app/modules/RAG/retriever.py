from elasticsearch import Elasticsearch
import numpy as np
import uuid
import time
import random
import requests
import os
from pathlib import Path
from app.core.config import settings
from dotenv import load_dotenv
import json


# 함수 사용법
# full_bm25(result)
# chunk_bm25(result)
# full_dense(result)
# chunk_dense(result)
# full_hybrid(result)
# chunk_hybrid(result)

load_dotenv()
base = Path(__file__).resolve()

# app 폴더까지
app_dir = base.parents[2]
embedding_path = app_dir / "db" / "small_category_embeddings.json"


URL = "https://clovastudio.stream.ntruss.com/testapp/v1/api-tools/embedding/v2/"
CLOVA_API_KEY = settings.CLOVA_API_KEY

es = Elasticsearch(
    "https://localhost:9200",
    basic_auth=(
        settings.ELASTIC_USER,
        settings.ELASTIC_PASSWORD
    ),
    verify_certs=False
)

_small_cate_cache = None

def get_small_category_embeddings():
    global _small_cate_cache

    if _small_cate_cache is None:
        with open(embedding_path, "r", encoding="utf-8") as f:
            _small_cate_cache = json.load(f)

    return _small_cate_cache

def make_headers():

    return {
        "Authorization": f"Bearer {CLOVA_API_KEY}",
        "X-NCP-CLOVASTUDIO-REQUEST-ID": str(uuid.uuid4()),
        "Content-Type": "application/json"
    }

def get_embedding(text, max_retries=10, timeout=30):
    payload = {
        "text": text
    }

    for attempt in range(max_retries):
        try:
            res = requests.post(URL, headers=make_headers(), json=payload, timeout=timeout)

            if res.status_code == 200:
                data = res.json()
                return data["result"]["embedding"]

            # 429 / 5xx 재시도
            if res.status_code in [429, 500, 502, 503, 504]:
                raise Exception(f"{res.status_code} / {res.text}")

            # 그 외 에러는 바로 종료
            raise Exception(f"{res.status_code} / {res.text}")

        except Exception as e:
            if attempt == max_retries - 1:
                raise e

            # 지수 백오프 + 랜덤 지터
            wait = min(30, (2 ** attempt) + random.uniform(0, 1))
            print(f"[재시도 {attempt+1}/{max_retries}] {wait:.1f}초 대기 → {e}")
            time.sleep(wait)

def cosine_similarity(a, b):
    a = np.array(a).flatten()
    b = np.array(b).flatten()
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))


def get_similar_small_categories(
    subject,
    small_category_embeddings,
    top_k=20,
    threshold=0.7
):
    query_vec = get_embedding(subject)

    results = []

    for item in small_category_embeddings:
        cate = item.get("small_cate") or item.get("category") or item.get("cate")
        emb = item.get("embedding")

        if cate is None or emb is None:
            continue

        sim = cosine_similarity(query_vec, emb)

        if sim >= threshold:
            results.append((cate, sim))

    results.sort(key=lambda x: x[1], reverse=True)
    return results[:top_k]

def to_list(x):
    if x is None:
        return []

    if isinstance(x, list):
        return [
            v for v in x
            if v is not None and str(v).strip() != ""
        ]

    if str(x).strip() == "":
        return []

    return [x]

def parse_page_conditions(page_range, around_margin=30):
    if not page_range:
        return None, []

    range_body = {}

    for cond in page_range:
        op = cond.get("operator")
        value = cond.get("value")

        if value is None:
            continue

        value = int(value)

        if op in ["gte", "gt", "lte", "lt"]:
            range_body[op] = value

        elif op == "eq":
            range_body["gte"] = value
            range_body["lte"] = value

        elif op == "around":
            range_body["gte"] = max(0, value - around_margin)
            range_body["lte"] = value + around_margin

    page_filter = None
    if range_body:
        page_filter = {
            "range": {
                "page": range_body
            }
        }

    return page_filter, []

mid_bonus = 0.08
small_bonus = 0.05

#==================================================================
#                          온보딩 데이터 검색
#==================================================================
READING_LEVEL_TEXT = {

    "easy": "쉽게 읽히는 쉬운 문체 입문자용",
    "medium": "적당한 난이도의 대중적인 문체",
    "hard": "깊이 있는 어려운 문체 전문적인 내용"

}

def make_onboarding_result(result):
    onboarding = result.get("onboarding_signals", {})

    topic = to_list(onboarding.get("topic"))
    reading_level = onboarding.get("reading_level")
    length_soft = onboarding.get("length_soft")

    # 기존 main query 복사
    keyword_query = result.get("keyword_query", [])
    if not isinstance(keyword_query, list):
        keyword_query = [keyword_query]

    keyword_query = [
        q for q in keyword_query
        if q is not None and str(q).strip() != ""
    ]

    semantic_query = result.get("semantic_query", "").strip()

    # 온보딩 검색에만 reading_level 추가
    if reading_level:
        level_text = READING_LEVEL_TEXT.get(reading_level, reading_level)
        keyword_query.append(level_text)

        if semantic_query:
            semantic_query = semantic_query + " " + level_text
        else:
            semantic_query = level_text

    onboarding_result = {
        "keyword_query": keyword_query,
        "semantic_query": semantic_query,

        "filters": {
            "cate_depth2": topic
        },

        "constraints": {
            "page_range": [length_soft] if length_soft else []
        },

        "score_boost": {
            "cate_depth2": [],
            "subject": []
        },

        "onboarding_signals": {}
    }

    return onboarding_result


def apply_bm25_disliked_penalty(results, result, penalty=999):
    disliked_keywords = to_list(
        result.get("onboarding_signals", {}).get("disliked_keywords")
    )

    if not disliked_keywords:
        return results

    fields = [
        "title",
        "book_intro",
        "book_index",
        "content",
        "review_text",
        "category_text",
        "chunk_text"
    ]

    for r in results:
        text = " ".join(str(r.get(f, "") or "") for f in fields)

        if any(kw in text for kw in disliked_keywords):
            r["score"] -= penalty
            r["bm25_disliked_penalty"] = penalty
        else:
            r["bm25_disliked_penalty"] = 0.0

    return results

def apply_dense_disliked_penalty(
    results,
    result,
    penalty=999,
    threshold=0.72
):
    disliked_keywords = to_list(
        result.get("onboarding_signals", {}).get("disliked_keywords")
    )

    if not disliked_keywords:
        return results

    disliked_vectors = [
        get_embedding(kw)
        for kw in disliked_keywords
    ]

    for r in results:
        doc_vec = r.get("embedding")

        if doc_vec is None:
            r["dense_disliked_penalty"] = 0.0
            continue

        max_sim = max(
            cosine_similarity(doc_vec, bad_vec)
            for bad_vec in disliked_vectors
        )

        r["disliked_similarity"] = float(max_sim)

        if max_sim >= threshold:
            r["score"] -= penalty
            r["dense_disliked_penalty"] = penalty
        else:
            r["dense_disliked_penalty"] = 0.0

    return results

# 성인 사용자는 유아나 청소년 카테고리 제외
ADULT_EXCLUDE_CATEGORIES = [
    "고등학교 참고서",
    "어린이",
    "유아",
    "청소년",
    "중학교 참고서",
    "초등학교 참고서",
    "수험서/자격증"
]


def should_exclude_youth_categories(result):
    age = result.get("onboarding_signals", {}).get("age")
    if age is None or age < 20:
        return False

    requested_large_cates = (
        result.get("filters", {}).get("cate_depth1")
        or []
    )

    # 사용자가 명시적으로 어린이/청소년/참고서 계열을 요청했다면 제외하지 않음
    if any(cate in ADULT_EXCLUDE_CATEGORIES for cate in requested_large_cates):
        return False

    return True

#==================================================================
#                            BM25 full
#==================================================================
def make_review_boost_query(query_text, boost):
    return {
        "function_score": {
            "query": {
                "match": {
                    "review_text": {
                        "query": query_text,
                        "boost": boost
                    }
                }
            },
            "script_score": {
                "script": {
                    "source": """
                        double rc = doc['review_count'].size() == 0 ? 0 : doc['review_count'].value;
                        double multiplier = Math.min(1.0 + Math.log1p(rc) * 0.1, 1.5);
                        return _score * multiplier;
                    """
                }
            },
            "boost_mode": "replace"
        }
    }

def full_bm25(
    result,
    index_name="books_review_full",
    size=20,
    small_category_embeddings=None,
    ):
    if small_category_embeddings is None:
        small_category_embeddings = get_small_category_embeddings()

    keyword_query = " ".join(result.get("keyword_query", [])).strip()
    filters = result.get("filters", {})
    score_boost = result.get("score_boost", {})
    constraints = result.get("constraints", {})
    
    coarse_categories = to_list(filters.get("cate_depth1"))
    anchor_title = filters.get("title")
    anchor_author = filters.get("author")
    mid_filter_categories = to_list(filters.get("cate_depth2"))
    fine_categories = to_list(score_boost.get("cate_depth2"))
    subjects = to_list(score_boost.get("subject"))

    authors = to_list(constraints.get("author"))
    author_nons = to_list(constraints.get("author_non"))
    page_range = constraints.get("page_range", [])
    pub_years = constraints.get("pub_year", [])

    filter_clause = []
    should_clause = []
    must_not_clause = []

    if should_exclude_youth_categories(result):
        must_not_clause.append({
            "terms": {
                "large_cate": ADULT_EXCLUDE_CATEGORIES
            }
        })

    if coarse_categories:
        filter_clause.append({
            "terms": {
                "large_cate": coarse_categories
            }
        })

    if mid_filter_categories:
        filter_clause.append({
            "terms": {
                "mid_cate": mid_filter_categories
            }

        })

    if authors:
        filter_clause.append({
            "bool": {
                "should": [
                    {"match_phrase": {"author": author}}
                    for author in authors
                ],
                "minimum_should_match": 1
            }
        })

    if author_nons:
        must_not_clause.extend([
            {"match_phrase": {"author": author}}
            for author in author_nons
        ])

    if anchor_title:
        must_not_clause.append({
            "match_phrase": {
                "title": anchor_title
            }
        })

    if anchor_author:
        must_not_clause.append({
            "match_phrase": {
                "author": anchor_author
            }
        })

    page_filter, page_must_not = parse_page_conditions(page_range)

    if page_filter:
        filter_clause.append(page_filter)

    if page_must_not:
        must_not_clause.extend(page_must_not)

    if pub_years:
        for cond in pub_years:
            operator = cond.get("operator")
            value = cond.get("value")

            if value is None:
                continue

            year = int(value)

            if operator == "gte":
                filter_clause.append({
                    "range": {
                        "publish_date": {
                            "gte": f"{year}-01-01"
                        }
                    }
                })

            elif operator == "gt":
                filter_clause.append({
                    "range": {
                        "publish_date": {
                            "gt": f"{year}-12-31"
                        }
                    }
                })

            elif operator == "lte":
                filter_clause.append({
                    "range": {
                        "publish_date": {
                            "lte": f"{year}-12-31"
                        }
                    }
                })

            elif operator == "lt":
                filter_clause.append({
                    "range": {
                        "publish_date": {
                            "lt": f"{year}-01-01"
                        }
                    }
                })

    for fc in fine_categories:
        should_clause.append({
            "term": {
                "mid_cate": {
                    "value": fc,
                    "boost": 2.0
                }
            }
        })

    for sub in subjects:
        should_clause.extend([
            {
                "match": {
                    "book_intro": {
                        "query": sub,
                        "boost": 1.8
                    }
                }
            },
            {
                "match": {
                    "book_index": {
                        "query": sub,
                        "boost": 1.5
                    }
                }
            },
            {
                "match": {
                    "content": {
                        "query": sub,
                        "boost": 1.0
                    }
                }
            },
            make_review_boost_query(sub, boost=1.1)
        ])

        if small_category_embeddings:

            similar_small_cates = get_similar_small_categories(
                subject=sub,
                small_category_embeddings=small_category_embeddings,
                top_k=5,
                threshold=0.7
            )

            for small_cate, sim in similar_small_cates:
                should_clause.append({
                    "term": {
                        "small_cate": {
                            "value": small_cate,
                            "boost": min(1.0 + float(sim), 2.0)
                        }
                    }
                })

    must_clause = []

    if keyword_query:
        must_clause.append({
            "multi_match": {
                "query": keyword_query,
                "fields": [
                    "title^4",
                    "category_text^2",
                    #"book_intro^1.5",
                    #"book_index^1.5",
                    "content^3",
                    "author^0.5"
                ],
                "type": "best_fields",
                "operator": "or",
                "minimum_should_match": "1"
            }
        })
        should_clause.append(
            make_review_boost_query(keyword_query, boost=1.1)
        )


    else:
        must_clause.append({"match_all": {}})

    query_body = {
        "size": size,
        "query": {
            "bool": {
                "filter": filter_clause,
                "must": must_clause,
                "should": should_clause,
                "must_not": must_not_clause
            }
        }
    }

    res = es.search(
        index=index_name,
        body=query_body
    )

    results = [
        {
            "rank": i + 1,
            "score": hit["_score"],
            **hit["_source"]
        }
        for i, hit in enumerate(res["hits"]["hits"])
    ]
    results = apply_bm25_disliked_penalty(results, result)

    return results

#==================================================================
#                            BM25 chunk
#==================================================================

def make_review_chunk_boost_query(query_text, boost=0.4):
    return {
        "function_score": {
            "query": {
                "bool": {
                    "must": [
                        {
                            "match": {
                                "chunk_text": {
                                    "query": query_text,
                                    "boost": boost
                                }
                            }
                        }
                    ],
                    "filter": [
                        {
                            "term": {
                                "chunk_type": "review"
                            }
                        }
                    ]
                }
            },
            "script_score": {
                "script": {
                    "source": """
                        double rc = doc['review_count'].size() == 0 ? 0 : doc['review_count'].value;
                        double multiplier = Math.min(1.0 + Math.log1p(rc) * 0.01, 1.05);
                        return _score * multiplier;
                    """
                }
            },
            "boost_mode": "replace"
        }
    }


def chunk_bm25(
    result,
    index_name="books_review_chunk",
    small_category_embeddings=None,
    size=20,
    candidate_size=100,
    top_k_per_book=3
):
    if small_category_embeddings is None:
        small_category_embeddings = get_small_category_embeddings()

    keyword_query = " ".join(result.get("keyword_query", [])).strip()
    filters = result.get("filters", {})
    score_boost = result.get("score_boost", {})
    constraints = result.get("constraints", {})

    coarse_categories = to_list(filters.get("cate_depth1"))
    anchor_title = filters.get("title")
    anchor_author = filters.get("author")
    mid_filter_categories = to_list(filters.get("cate_depth2"))
    fine_categories = to_list(score_boost.get("cate_depth2"))
    subjects = to_list(score_boost.get("subject"))

    authors = to_list(constraints.get("author"))
    author_nons = to_list(constraints.get("author_non"))
    page_range = constraints.get("page_range", [])
    pub_years = constraints.get("pub_year", [])

    filter_clause = []
    should_clause = []
    must_not_clause = []

    if should_exclude_youth_categories(result):
        must_not_clause.append({
            "terms": {
                "large_cate": ADULT_EXCLUDE_CATEGORIES
            }
        })

    if coarse_categories:
        filter_clause.append({
            "terms": {
                "large_cate": coarse_categories
            }
        })

    if mid_filter_categories:
        filter_clause.append({
            "terms": {
                "mid_cate": mid_filter_categories
            }

        })

    if authors:
        filter_clause.append({
            "bool": {
                "should": [
                    {"match_phrase": {"author": author}}
                    for author in authors
                ],
                "minimum_should_match": 1
            }
        })

    if author_nons:
        must_not_clause.extend([
            {"match_phrase": {"author": author}}
            for author in author_nons
        ])

    if anchor_title:
        must_not_clause.append({
            "match_phrase": {
                "title": anchor_title
            }
        })

    if anchor_author:
        must_not_clause.append({
            "match_phrase": {
                "author": anchor_author
            }
        })

    page_filter, page_must_not = parse_page_conditions(page_range)

    if page_filter:
        filter_clause.append(page_filter)

    if page_must_not:
        must_not_clause.extend(page_must_not)

    if pub_years:
        for cond in pub_years:
            operator = cond.get("operator")
            value = cond.get("value")

            if value is None:
                continue

            year = int(value)

            if operator == "gte":
                filter_clause.append({
                    "range": {
                        "publish_date": {
                            "gte": f"{year}-01-01"
                        }
                    }
                })

            elif operator == "gt":
                filter_clause.append({
                    "range": {
                        "publish_date": {
                            "gt": f"{year}-12-31"
                        }
                    }
                })

            elif operator == "lte":
                filter_clause.append({
                    "range": {
                        "publish_date": {
                            "lte": f"{year}-12-31"
                        }
                    }
                })

            elif operator == "lt":
                filter_clause.append({
                    "range": {
                        "publish_date": {
                            "lt": f"{year}-01-01"
                        }
                    }
                })

    for fc in fine_categories:
        should_clause.append({
            "term": {
                "mid_cate": {
                    "value": fc,
                    "boost": 2.0
                }
            }
        })

    for sub in subjects:

        should_clause.extend([

            {
                "match": {
                    "book_intro": {
                        "query": sub,
                        "boost": 1.8
                    }
                }
            },
            {
                "match": {
                    "book_index": {
                        "query": sub,
                        "boost": 1.5
                    }
                }
            },
            {
                "match": {
                    "content": {
                        "query": sub,
                        "boost": 1.0
                    }
                }
            },
            make_review_chunk_boost_query(sub, boost=1.1)
        ])

        if small_category_embeddings:

            similar_small_cates = get_similar_small_categories(
                subject=sub,
                small_category_embeddings=small_category_embeddings,
                top_k=5,
                threshold=0.7
            )

            for small_cate, sim in similar_small_cates:
                should_clause.append({
                    "term": {
                        "small_cate": {
                            "value": small_cate,
                            "boost": min(1.0 + float(sim), 2.0)
                        }
                    }
                })


    must_clause = []

    if keyword_query:
        must_clause.append({
            "multi_match": {
                "query": keyword_query,
                "fields": [
                    "chunk_text^3",
                    "title^4",
                    "category_text^2",
                    #"book_intro^1",
                    #"book_index^1",
                    "author^0.5"
                ],
                "type": "best_fields",
                "operator": "or",
                "minimum_should_match": "1"
            }
        })

        should_clause.append(
            make_review_chunk_boost_query(keyword_query, boost=0.4)
        )

    else:
        must_clause.append({"match_all": {}})

    query_body = {
        "size": candidate_size,
        "query": {
            "bool": {
                "filter": filter_clause,
                "must": must_clause,
                "should": should_clause,
                "must_not": must_not_clause
            }
        }
    }

    res = es.search(
        index=index_name,
        body=query_body
    )

    chunk_results = [
    {
        "chunk_rank": i + 1,
        "chunk_score": hit["_score"],
        **hit["_source"]
    }
    for i, hit in enumerate(res["hits"]["hits"])
    ]

    by_isbn = {}

    for r in chunk_results:
        isbn = r["isbn"]

        if not isbn:
            continue

        if isbn not in by_isbn:
            by_isbn[isbn] = []

        by_isbn[isbn].append(r)

    book_results = []

    for isbn, chunks in by_isbn.items():
        chunks = sorted(chunks, key=lambda x: x["chunk_score"], reverse=True)
        top_chunks = chunks[:top_k_per_book]

        max_score = top_chunks[0]["chunk_score"]
        mean_score = sum(c["chunk_score"] for c in top_chunks) / len(top_chunks)

        book_score = max_score * 0.7 + mean_score * 0.3

        rep = top_chunks[0].copy()
        rep["rank"] = None
        rep["score"] = book_score
        rep["max_chunk_score"] = max_score
        rep["mean_chunk_score"] = mean_score
        rep["matched_chunk_count"] = len(top_chunks)
        rep["top_chunks"] = top_chunks
        rep["source"] = "bm25_chunk_book_agg"

        book_results.append(rep)

    book_results = apply_bm25_disliked_penalty(book_results, result)

    book_results.sort(key=lambda x: x["score"], reverse=True)

    for i, r in enumerate(book_results[:size], start=1):
        r["rank"] = i

    return book_results[:size]

#==================================================================
#                            Dense full
#==================================================================
def full_dense(
    result,
    index_name="books_review_full",
    size=20,
    num_candidates=100,
    small_category_embeddings=None

):
    if small_category_embeddings is None:
        small_category_embeddings = get_small_category_embeddings()

    semantic_query = result.get("semantic_query", "").strip()

    if not semantic_query:
        semantic_query = " ".join(result.get("keyword_query", [])).strip()

    filters = result.get("filters", {})
    constraints = result.get("constraints", {})
    score_boost = result.get("score_boost", {})

    coarse_categories = to_list(filters.get("cate_depth1"))
    anchor_title = filters.get("title")
    anchor_author = filters.get("author")
    mid_filter_categories = to_list(filters.get("cate_depth2"))
    fine_categories = to_list(score_boost.get("cate_depth2"))
    subjects = to_list(score_boost.get("subject"))
    authors = to_list(constraints.get("author"))
    author_nons = to_list(constraints.get("author_non"))
    page_range = constraints.get("page_range", [])
    pub_years = constraints.get("pub_year", [])

    filter_clause = []
    must_not_clause = []

    if should_exclude_youth_categories(result):
        must_not_clause.append({
            "terms": {
                "large_cate": ADULT_EXCLUDE_CATEGORIES
            }
        })

    if coarse_categories:
        filter_clause.append({
            "terms": {
                "large_cate": coarse_categories
            }
        })

    if mid_filter_categories:
        filter_clause.append({
            "terms": {
                "mid_cate": mid_filter_categories
            }

        })

    if authors:
        filter_clause.append({
            "bool": {
                "should": [
                    {"match_phrase": {"author": author}}
                    for author in authors
                ],
                "minimum_should_match": 1
            }
        })

    if author_nons:
        must_not_clause.extend([
            {"match_phrase": {"author": author}}
            for author in author_nons
        ])

    if anchor_title:
        must_not_clause.append({
            "match_phrase": {
                "title": anchor_title
            }
        })

    if anchor_author:
        must_not_clause.append({
            "match_phrase": {
                "author": anchor_author
            }
        })

    page_filter, page_must_not = parse_page_conditions(page_range)

    if page_filter:
        filter_clause.append(page_filter)

    if page_must_not:
        must_not_clause.extend(page_must_not)

    if pub_years:
        for cond in pub_years:
            operator = cond.get("operator")
            value = cond.get("value")

            if value is None:
                continue

            year = int(value)

            if operator == "gte":
                filter_clause.append({
                    "range": {
                        "publish_date": {
                            "gte": f"{year}-01-01"
                        }
                    }
                })

            elif operator == "gt":
                filter_clause.append({
                    "range": {
                        "publish_date": {
                            "gt": f"{year}-12-31"
                        }
                    }
                })

            elif operator == "lte":
                filter_clause.append({
                    "range": {
                        "publish_date": {
                            "lte": f"{year}-12-31"
                        }
                    }
                })

            elif operator == "lt":
                filter_clause.append({
                    "range": {
                        "publish_date": {
                            "lt": f"{year}-01-01"
                        }
                    }
                })

    query_vector = get_embedding(semantic_query)

    query_body = {
        "size": size,
        "knn": {
            "field": "embedding",
            "query_vector": query_vector,
            "k": size,
            "num_candidates": num_candidates,
            "filter": {
                "bool": {
                    "filter": filter_clause,
                    "must_not": must_not_clause
                }
            }
        }
    }

    res = es.search(
        index=index_name,
        body=query_body
    )

    # subject 기반 유사 소분류 계산

    similar_small_cate_scores = {}

    if subjects and small_category_embeddings:

        for sub in subjects:

            similar_small_cates = get_similar_small_categories(

                subject=sub,

                small_category_embeddings=small_category_embeddings,

                top_k=5,

                threshold=0.7

            )

            for small_cate, sim in similar_small_cates:

                similar_small_cate_scores[small_cate] = max(

                    similar_small_cate_scores.get(small_cate, 0),

                    float(sim)

                )

    results = []

    for i, hit in enumerate(res["hits"]["hits"]):
        source = hit["_source"]
        dense_score = hit["_score"]
        rerank_score = dense_score
        doc_mid_cates = to_list(source.get("mid_cate"))
        doc_small_cates = to_list(source.get("small_cate"))

        # 중분류 보너스
        if fine_categories and any(cate in fine_categories for cate in doc_mid_cates):
            rerank_score += mid_bonus

        # 유사 소분류 보너스
        matched_small_scores = [
            similar_small_cate_scores[cate]
            for cate in doc_small_cates
            if cate in similar_small_cate_scores
        ]

        if matched_small_scores:
            rerank_score += small_bonus * max(matched_small_scores)

        results.append({
            "rank": None,
            "score": rerank_score,
            "dense_score": dense_score,
            "cate_bonus": rerank_score - dense_score,
            **source
        })

    results = apply_dense_disliked_penalty(results, result)

    results.sort(key=lambda x: x["score"], reverse=True)

    for i, r in enumerate(results[:size], start=1):
        r["rank"] = i

    return results[:size]

#==================================================================
#                            Dense chunk
#==================================================================
def chunk_dense(
    result,
    index_name="books_review_chunk",
    size=20,
    num_candidates=300,
    candidate_size=100,
    top_k_per_book=3,
    small_category_embeddings=None,
    
):  
    if small_category_embeddings is None:
        small_category_embeddings = get_small_category_embeddings()

    semantic_query = result.get("semantic_query", "").strip()

    if not semantic_query:
        semantic_query = " ".join(result.get("keyword_query", [])).strip()

    filters = result.get("filters", {})
    constraints = result.get("constraints", {})
    score_boost = result.get("score_boost", {})
    
    coarse_categories = to_list(filters.get("cate_depth1"))
    anchor_title = filters.get("title")
    anchor_author = filters.get("author")
    mid_filter_categories = to_list(filters.get("cate_depth2"))
    fine_categories = to_list(score_boost.get("cate_depth2"))
    subjects = to_list(score_boost.get("subject"))
    authors = to_list(constraints.get("author"))
    author_nons = to_list(constraints.get("author_non"))
    page_range = constraints.get("page_range", [])
    pub_years = constraints.get("pub_year", [])

    filter_clause = []
    must_not_clause = []

    if should_exclude_youth_categories(result):
        must_not_clause.append({
            "terms": {
                "large_cate": ADULT_EXCLUDE_CATEGORIES
            }
        })

    if coarse_categories:
        filter_clause.append({
            "terms": {
                "large_cate": coarse_categories
            }
        })

    if mid_filter_categories:
        filter_clause.append({
            "terms": {
                "mid_cate": mid_filter_categories
            }

        })

    if authors:
        filter_clause.append({
            "bool": {
                "should": [
                    {"match_phrase": {"author": author}}
                    for author in authors
                ],
                "minimum_should_match": 1
            }
        })

    if author_nons:
        must_not_clause.extend([
            {"match_phrase": {"author": author}}
            for author in author_nons
        ])

    if anchor_title:
        must_not_clause.append({
            "match_phrase": {
                "title": anchor_title
            }
        })

    if anchor_author:
        must_not_clause.append({
            "match_phrase": {
                "author": anchor_author
            }
        })

    page_filter, page_must_not = parse_page_conditions(page_range)

    if page_filter:
        filter_clause.append(page_filter)

    if page_must_not:
        must_not_clause.extend(page_must_not)

    if pub_years:
        for cond in pub_years:
            operator = cond.get("operator")
            value = cond.get("value")

            if value is None:
                continue

            year = int(value)

            if operator == "gte":
                filter_clause.append({
                    "range": {
                        "publish_date": {
                            "gte": f"{year}-01-01"
                        }
                    }
                })

            elif operator == "gt":
                filter_clause.append({
                    "range": {
                        "publish_date": {
                            "gt": f"{year}-12-31"
                        }
                    }
                })

            elif operator == "lte":
                filter_clause.append({
                    "range": {
                        "publish_date": {
                            "lte": f"{year}-12-31"
                        }
                    }
                })

            elif operator == "lt":
                filter_clause.append({
                    "range": {
                        "publish_date": {
                            "lt": f"{year}-01-01"
                        }
                    }
                })

    # subject 기반 유사 소분류 점수 계산

    similar_small_cate_scores = {}

    if subjects and small_category_embeddings:

        for sub in subjects:

            similar_small_cates = get_similar_small_categories(

                subject=sub,

                small_category_embeddings=small_category_embeddings,

                top_k=5,

                threshold=0.7

            )

            for small_cate, sim in similar_small_cates:

                similar_small_cate_scores[small_cate] = max(

                    similar_small_cate_scores.get(small_cate, 0),

                    float(sim)

                )

    query_vector = get_embedding(semantic_query)

    query_body = {
        "size": candidate_size,
        "knn": {
            "field": "embedding",
            "query_vector": query_vector,
            "k": candidate_size,
            "num_candidates": num_candidates,
            "filter": {
                "bool": {
                    "filter": filter_clause,
                    "must_not": must_not_clause
                }
            }
        },
        "rescore": {
            "window_size": candidate_size,
            "query": {
                "rescore_query": {
                    "script_score": {
                        "query": {
                            "match_all": {}
                        },
                        "script": {
                            "source": """
                                double multiplier = 1.0;

                                if (
                                    doc['chunk_type'].size() != 0 &&
                                    doc['chunk_type'].value.endsWith('_3')
                                ) {
                                    double rc = doc['review_count'].size() == 0
                                        ? 0
                                        : doc['review_count'].value;

                                    multiplier = Math.min(
                                        0.95 + Math.log1p(rc) * 0.03,
                                        1.0
                                    );
                                }

                                return multiplier;
                            """
                        }
                    }
                },
                "query_weight": 1.0,
                "rescore_query_weight": 0.05
            }
        }
    }

    res = es.search(
        index=index_name,
        body=query_body
    )

    chunk_results = [
    {
        "chunk_rank": i + 1,
        "chunk_score": hit["_score"],
        **hit["_source"]
    }
    for i, hit in enumerate(res["hits"]["hits"])
    ]

    by_isbn = {}

    for r in chunk_results:
        isbn = r["isbn"]

        if not isbn:
            continue

        if isbn not in by_isbn:
            by_isbn[isbn] = []

        by_isbn[isbn].append(r)

    book_results = []

    for isbn, chunks in by_isbn.items():

        chunks = sorted(chunks, key=lambda x: x["chunk_score"], reverse=True)
        top_chunks = chunks[:top_k_per_book]
    
        max_score = top_chunks[0]["chunk_score"]
        mean_score = sum(c["chunk_score"] for c in top_chunks) / len(top_chunks)
        base_score = max_score * 0.7 + mean_score * 0.3
        cate_bonus = 0.0
        rep = top_chunks[0].copy()

        doc_mid_cates = to_list(rep.get("mid_cate"))
        doc_small_cates = to_list(rep.get("small_cate"))

        if fine_categories and any(cate in fine_categories for cate in doc_mid_cates):
            cate_bonus += mid_bonus

        matched_small_scores = [
            similar_small_cate_scores[cate]
            for cate in doc_small_cates
            if cate in similar_small_cate_scores
        ]

        if matched_small_scores:
            cate_bonus += small_bonus * max(matched_small_scores)

        book_score = base_score + cate_bonus

        rep["rank"] = None
        rep["score"] = book_score
        rep["base_score"] = base_score
        rep["cate_bonus"] = cate_bonus
        rep["max_chunk_score"] = max_score
        rep["mean_chunk_score"] = mean_score
        rep["matched_chunk_count"] = len(top_chunks)
        rep["top_chunks"] = top_chunks
        rep["source"] = "dense_chunk_book_agg"

        book_results.append(rep)

    book_results = apply_dense_disliked_penalty(book_results, result)

    book_results.sort(key=lambda x: x["score"], reverse=True)

    for i, r in enumerate(book_results[:size], start=1):
        r["rank"] = i

    return book_results[:size]

#==================================================================
#                            Hybrid full
#==================================================================
def normalize_scores(results, score_key="score"):
    if not results:
        return []

    scores = [r.get(score_key, 0) for r in results]
    min_score = min(scores)
    max_score = max(scores)

    normalized = []

    for r in results:
        item = r.copy()

        if max_score == min_score:
            item["normalized_score"] = 1.0
        else:
            item["normalized_score"] = (
                (item.get(score_key, 0) - min_score)
                / (max_score - min_score)
            )

        normalized.append(item)

    return normalized

def full_hybrid(
    result,
    size=20,
    bm25_candidate_size=100,
    dense_candidate_size=100,
    num_candidates=300,
    require_both=False,
    overlap_bonus=0.0,
    rrf_k=60,
    bm25_weight=1.0,
    dense_weight=1.0,
    small_category_embeddings=None
):
    if small_category_embeddings is None:
        small_category_embeddings = get_small_category_embeddings()

    def fill_metadata(item, r):
        for key in ["title", "author", "page", "large", "review_count"]:
            if item.get(key) is None and r.get(key) is not None:
                item[key] = r.get(key)

    bm25_results = full_bm25(
        result=result,
        index_name="books_review_full",
        size=bm25_candidate_size,
        small_category_embeddings=small_category_embeddings
    )

    dense_results = full_dense(
        result=result,
        index_name="books_review_full",
        size=dense_candidate_size,
        num_candidates=num_candidates,
        small_category_embeddings=small_category_embeddings
    )

    merged = {}

    # =========================
    # BM25 결과 병합
    # =========================
    for rank, r in enumerate(bm25_results, start=1):
        isbn = r["isbn"]

        if isbn not in merged:
            merged[isbn] = {
                **r,
                "bm25_rank": None,
                "dense_rank": None,
                "bm25_raw_score": None,
                "dense_raw_score": None,
                "bm25_result": None,
                "dense_result": None,
                "bm25_rrf_score": 0.0,
                "dense_rrf_score": 0.0,
            }

        fill_metadata(merged[isbn], r)

        merged[isbn]["bm25_rank"] = rank
        merged[isbn]["bm25_raw_score"] = r.get("score")
        merged[isbn]["bm25_result"] = r
        merged[isbn]["bm25_rrf_score"] = bm25_weight * (1 / (rrf_k + rank))

    # =========================
    # Dense 결과 병합
    # =========================
    for rank, r in enumerate(dense_results, start=1):
        isbn = r["isbn"]

        if isbn not in merged:
            merged[isbn] = {
                **r,
                "bm25_rank": None,
                "dense_rank": None,
                "bm25_raw_score": None,
                "dense_raw_score": None,
                "bm25_result": None,
                "dense_result": None,
                "bm25_rrf_score": 0.0,
                "dense_rrf_score": 0.0,
            }

        fill_metadata(merged[isbn], r)

        merged[isbn]["dense_rank"] = rank
        merged[isbn]["dense_raw_score"] = r.get("score")
        merged[isbn]["dense_result"] = r
        merged[isbn]["dense_rrf_score"] = dense_weight * (1 / (rrf_k + rank))

    # =========================
    # 최종 RRF 점수 계산
    # =========================
    final_results = []

    for isbn, item in merged.items():
        has_bm25 = item["bm25_result"] is not None
        has_dense = item["dense_result"] is not None

        if require_both and not (has_bm25 and has_dense):
            continue

        score = item["bm25_rrf_score"] + item["dense_rrf_score"]

        if has_bm25 and has_dense:
            score += overlap_bonus

        item["score"] = score
        item["has_bm25"] = has_bm25
        item["has_dense"] = has_dense
        item["source"] = "hybrid_full_rrf"

        final_results.append(item)

    final_results.sort(key=lambda x: x["score"], reverse=True)

    for i, r in enumerate(final_results[:size], start=1):
        r["rank"] = i

    return final_results[:size]

#==================================================================
#                            Hybrid chunk
#==================================================================

def chunk_hybrid(
    result,
    size=20,
    bm25_weight=1.0,
    dense_weight=1.0,
    bm25_candidate_size=100,
    dense_candidate_size=100,
    num_candidates=300,
    top_k_per_book=3,
    require_both=False,
    overlap_bonus=0.0,
    rrf_k=60,
    small_category_embeddings=None
):
    if small_category_embeddings is None:
        small_category_embeddings = get_small_category_embeddings()

    bm25_results = chunk_bm25(
        result=result,
        index_name="books_review_chunk",
        size=bm25_candidate_size,
        candidate_size=bm25_candidate_size,
        top_k_per_book=top_k_per_book,
        small_category_embeddings=small_category_embeddings
    )

    dense_results = chunk_dense(
        result=result,
        index_name="books_review_chunk",
        size=dense_candidate_size,
        candidate_size=dense_candidate_size,
        num_candidates=num_candidates,
        top_k_per_book=top_k_per_book,
        small_category_embeddings=small_category_embeddings
    )

    merged = {}

    # =========================
    # BM25 결과 병합
    # =========================
    for rank, r in enumerate(bm25_results, start=1):
        isbn = r["isbn"]

        if isbn not in merged:
            merged[isbn] = {
                **r,
                "bm25_rank": None,
                "dense_rank": None,
                "bm25_raw_score": None,
                "dense_raw_score": None,
                "bm25_result": None,
                "dense_result": None,
                "bm25_rrf_score": 0.0,
                "dense_rrf_score": 0.0,
            }

        merged[isbn]["bm25_rank"] = rank
        merged[isbn]["bm25_raw_score"] = r.get("score")
        merged[isbn]["bm25_result"] = r
        merged[isbn]["bm25_rrf_score"] = bm25_weight * (1 / (rrf_k + rank))

    # =========================
    # Dense 결과 병합
    # =========================
    for rank, r in enumerate(dense_results, start=1):
        isbn = r["isbn"]

        if isbn not in merged:
            merged[isbn] = {
                **r,
                "bm25_rank": None,
                "dense_rank": None,
                "bm25_raw_score": None,
                "dense_raw_score": None,
                "bm25_result": None,
                "dense_result": None,
                "bm25_rrf_score": 0.0,
                "dense_rrf_score": 0.0,
            }

        merged[isbn]["dense_rank"] = rank
        merged[isbn]["dense_raw_score"] = r.get("score")
        merged[isbn]["dense_result"] = r
        merged[isbn]["dense_rrf_score"] = dense_weight * (1 / (rrf_k + rank))

    final_results = []

    # =========================
    # 최종 RRF 점수 계산
    # =========================
    for isbn, item in merged.items():
        has_bm25 = item["bm25_result"] is not None
        has_dense = item["dense_result"] is not None

        if require_both and not (has_bm25 and has_dense):
            continue

        score = item["bm25_rrf_score"] + item["dense_rrf_score"]

        if has_bm25 and has_dense:
            score += overlap_bonus

        item["score"] = score
        item["has_bm25"] = has_bm25
        item["has_dense"] = has_dense
        item["source"] = "hybrid_chunk_rrf"

        final_results.append(item)

    final_results.sort(key=lambda x: x["score"], reverse=True)

    for i, r in enumerate(final_results[:size], start=1):
        r["rank"] = i

    return final_results[:size]

#==================================================================
#                  Main result + Onboarding result 병합 검색
#==================================================================

def merge_weighted_results(
    main_results,
    onboarding_results,
    main_weight=0.7,
    onboarding_weight=0.3,
    size=20
):
    main_norm = normalize_scores(main_results)
    onboarding_norm = normalize_scores(onboarding_results)

    merged = {}

    for r in main_norm:
        isbn = r.get("isbn")
        if not isbn:
            continue

        merged[isbn] = {
            **r,
            "main_score": r["normalized_score"],
            "onboarding_score": 0.0,
            "main_result": r,
            "onboarding_result": None,
        }

    for r in onboarding_norm:
        isbn = r.get("isbn")
        if not isbn:
            continue

        if isbn not in merged:
            merged[isbn] = {
                **r,
                "main_score": 0.0,
                "onboarding_score": r["normalized_score"],
                "main_result": None,
                "onboarding_result": r,
            }
        else:
            merged[isbn]["onboarding_score"] = r["normalized_score"]
            merged[isbn]["onboarding_result"] = r

    final_results = []

    for isbn, item in merged.items():
        item["score"] = (
            item["main_score"] * main_weight
            + item["onboarding_score"] * onboarding_weight
        )
        item["source"] = "main_onboarding_weighted"
        final_results.append(item)

    final_results.sort(key=lambda x: x["score"], reverse=True)

    for i, r in enumerate(final_results[:size], start=1):
        r["rank"] = i

    return final_results[:size]

def run_with_onboarding(
    result,
    search_fn,
    size=20,
    main_weight=0.7,
    onboarding_weight=0.3,
    **kwargs
):
    main_result = result.copy()

    # 검색용 온보딩 신호만 제거하되,
    # disliked_keywords는 penalty용으로 유지
    original_onboarding = result.get("onboarding_signals", {})
    main_result["onboarding_signals"] = {
        "age": original_onboarding.get("age"),
        "disliked_keywords": original_onboarding.get("disliked_keywords", [])
    }

    onboarding_result = make_onboarding_result(result)

    # 온보딩 검색에서도 penalty를 적용하려면 disliked 유지
    onboarding_result["onboarding_signals"] = {
        "age": original_onboarding.get("age"),
        "disliked_keywords": original_onboarding.get("disliked_keywords", [])
    }

    main_results = search_fn(
        result=main_result,
        size=size,
        **kwargs
    )

    onboarding_results = search_fn(
        result=onboarding_result,
        size=size,
        **kwargs
    )

    return merge_weighted_results(
        main_results=main_results,
        onboarding_results=onboarding_results,
        main_weight=main_weight,
        onboarding_weight=onboarding_weight,
        size=size
    )

def full_bm25_with_onboarding(result, size=20, **kwargs):
    return run_with_onboarding(result, full_bm25, size=size, **kwargs)

def chunk_bm25_with_onboarding(result, size=20, **kwargs):
    return run_with_onboarding(result, chunk_bm25, size=size, **kwargs)

def full_dense_with_onboarding(result, size=20, **kwargs):
    return run_with_onboarding(result, full_dense, size=size, **kwargs)

def chunk_dense_with_onboarding(result, size=20, **kwargs):
    return run_with_onboarding(result, chunk_dense, size=size, **kwargs)

def full_hybrid_with_onboarding(result, size=20, **kwargs):
    return run_with_onboarding(result, full_hybrid, size=size, **kwargs)

def chunk_hybrid_with_onboarding(result, size=20, **kwargs):
    return run_with_onboarding(result, chunk_hybrid, size=size, **kwargs)
