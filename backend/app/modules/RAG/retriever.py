from elasticsearch import Elasticsearch
import numpy as np
import uuid
import time
import random
import requests
import os
from app.core.config import settings

# 함수 사용법
# full_bm25(result)
# chunk_bm25(result)
# full_dense(result)
# chunk_dense(result)
# full_hybrid(result)
# chunk_hybrid(result)

URL = "https://clovastudio.stream.ntruss.com/testapp/v1/api-tools/embedding/v2/"
CLOVA_API_KEY = settings.CLOVA_API_KEY

es = Elasticsearch(
    "https://localhost:9200",
    basic_auth=("elastic", "dw2s3Vinv8X6ihtUy_fB"),
    verify_certs=False
)

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
    # 1. subject embedding
    query_vec = get_embedding(subject)

    results = []

    for cate, emb in small_category_embeddings.items():
        sim = cosine_similarity(query_vec, emb)

        if sim >= threshold:
            results.append((cate, sim))

    # 2. 정렬
    results.sort(key=lambda x: x[1], reverse=True)

    # 3. top_k
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

def parse_page_conditions(page_range):
    if not page_range:
        return None, []

    range_body = {}
    must_not_clause = []

    for cond in page_range:
        op = cond.get("operator")
        value = cond.get("value")

        if value is None:
            continue

        if op in ["gte", "gt", "lte", "lt"]:
            range_body[op] = value
        elif op == "eq":
            range_body["gte"] = value
            range_body["lte"] = value
        elif op == "exclude":
            must_not_clause.append({"term": {"page": value}})

    page_filter = None
    if range_body:
        page_filter = {"range": {"page": range_body}}

    return page_filter, must_not_clause

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
    size=20
    ):
    keyword_query = " ".join(result.get("keyword_query", [])).strip()
    filters = result.get("filters", {})
    score_boost = result.get("score_boost", {})
    constraints = result.get("constraints", {})
    coarse_categories = to_list(filters.get("coarse_category"))
    fine_categories = to_list(score_boost.get("fine_category"))
    subjects = to_list(score_boost.get("subject"))

    authors = to_list(constraints.get("author"))
    author_nons = to_list(constraints.get("author_non"))
    page_range = constraints.get("page_range", [])
    pub_years = to_list(constraints.get("pub_year"))

    filter_clause = []
    should_clause = []
    must_not_clause = []

    if coarse_categories:
        filter_clause.append({
            "terms": {
                "large_cate": coarse_categories
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

    page_filter, page_must_not = parse_page_conditions(page_range)

    if page_filter:
        filter_clause.append(page_filter)

    if page_must_not:
        must_not_clause.extend(page_must_not)

    if pub_years:
        min_year = min(int(y) for y in pub_years)

        filter_clause.append({
            "range": {
                "publish_date": {
                    "gte": f"{min_year}-01-01"
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

    return [
    {
        "rank": i + 1,
        "score": hit["_score"],
        **hit["_source"]
    }
    for i, hit in enumerate(res["hits"]["hits"])
    ]

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
    size=20,
    candidate_size=100,
    top_k_per_book=3
):
    keyword_query = " ".join(result.get("keyword_query", [])).strip()
    filters = result.get("filters", {})
    score_boost = result.get("score_boost", {})
    constraints = result.get("constraints", {})

    coarse_categories = to_list(filters.get("coarse_category"))
    fine_categories = to_list(score_boost.get("fine_category"))
    subjects = to_list(score_boost.get("subject"))

    authors = to_list(constraints.get("author"))
    author_nons = to_list(constraints.get("author_non"))
    page_range = constraints.get("page_range", [])
    pub_years = to_list(constraints.get("pub_year"))

    filter_clause = []
    should_clause = []
    must_not_clause = []

    if coarse_categories:
        filter_clause.append({
            "terms": {
                "large_cate": coarse_categories
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

    page_filter, page_must_not = parse_page_conditions(page_range)

    if page_filter:
        filter_clause.append(page_filter)

    if page_must_not:
        must_not_clause.extend(page_must_not)

    if pub_years:
        min_year = min(int(y) for y in pub_years)

        filter_clause.append({
            "range": {
                "publish_date": {
                    "gte": f"{min_year}-01-01"
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
                    "chunk_text": {
                        "query": sub,
                        "boost": 2.0
                    }
                }
            },
            {
                "match": {
                    "book_intro": {
                        "query": sub,
                        "boost": 1.3
                    }
                }
            },
            {
                "match": {
                    "book_index": {
                        "query": sub,
                        "boost": 1.3
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
            make_review_chunk_boost_query(sub, boost=0.4)
        ])

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
    num_candidates=100
):
    semantic_query = result.get("semantic_query", "").strip()

    if not semantic_query:
        semantic_query = " ".join(result.get("keyword_query", [])).strip()

    filters = result.get("filters", {})
    constraints = result.get("constraints", {})

    coarse_categories = to_list(filters.get("coarse_category"))

    authors = to_list(constraints.get("author"))
    author_nons = to_list(constraints.get("author_non"))
    page_range = constraints.get("page_range", [])
    pub_years = to_list(constraints.get("pub_year"))

    filter_clause = []
    must_not_clause = []

    if coarse_categories:
        filter_clause.append({
            "terms": {
                "large_cate": coarse_categories
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

    page_filter, page_must_not = parse_page_conditions(page_range)

    if page_filter:
        filter_clause.append(page_filter)

    if page_must_not:
        must_not_clause.extend(page_must_not)

    if pub_years:
        min_year = min(int(y) for y in pub_years)

        filter_clause.append({
            "range": {
                "publish_date": {
                    "gte": f"{min_year}-01-01"
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

    return [
    {
        "rank": i + 1,
        "score": hit["_score"],
        **hit["_source"]
    }
    for i, hit in enumerate(res["hits"]["hits"])
    ]

#==================================================================
#                            Dense chunk
#==================================================================
def chunk_dense(
    result,
    index_name="books_review_chunk",
    size=20,
    num_candidates=300,
    candidate_size=100,
    top_k_per_book=3
):
    semantic_query = result.get("semantic_query", "").strip()

    if not semantic_query:
        semantic_query = " ".join(result.get("keyword_query", [])).strip()

    filters = result.get("filters", {})
    constraints = result.get("constraints", {})

    coarse_categories = to_list(filters.get("coarse_category"))

    authors = to_list(constraints.get("author"))
    author_nons = to_list(constraints.get("author_non"))
    page_range = constraints.get("page_range", [])
    pub_years = to_list(constraints.get("pub_year"))

    filter_clause = []
    must_not_clause = []

    if coarse_categories:
        filter_clause.append({
            "terms": {
                "large_cate": coarse_categories
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

    page_filter, page_must_not = parse_page_conditions(page_range)

    if page_filter:
        filter_clause.append(page_filter)

    if page_must_not:
        must_not_clause.extend(page_must_not)

    if pub_years:
        min_year = min(int(y) for y in pub_years)

        filter_clause.append({
            "range": {
                "publish_date": {
                    "gte": f"{min_year}-01-01"
                }
            }
        })

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

        book_score = max_score * 0.7 + mean_score * 0.3

        rep = top_chunks[0].copy()
        rep["rank"] = None
        rep["score"] = book_score
        rep["max_chunk_score"] = max_score
        rep["mean_chunk_score"] = mean_score
        rep["matched_chunk_count"] = len(top_chunks)
        rep["top_chunks"] = top_chunks
        rep["source"] = "dense_chunk_book_agg"

        book_results.append(rep)

    book_results.sort(key=lambda x: x["score"], reverse=True)

    for i, r in enumerate(book_results[:size], start=1):
        r["rank"] = i

    return book_results[:size]

#==================================================================
#                            Hybrid full
#==================================================================
def full_hybrid(
    result,
    size=20,
    bm25_weight=0.5,
    dense_weight=0.5,
    bm25_candidate_size=100,
    dense_candidate_size=100,
    num_candidates=300,
    require_both=False,
    overlap_bonus=0.1
):
    def fill_metadata(item, r):
        for key in ["title", "author", "page", "large", "review_count"]:
            if item.get(key) is None and r.get(key) is not None:
                item[key] = r.get(key)

    bm25_results = full_bm25(
        result=result,
        index_name="books_review_full",
        size=bm25_candidate_size
    )

    dense_results = full_dense(
        result=result,
        index_name="books_review_full",
        size=dense_candidate_size,
        num_candidates=num_candidates
    )

    bm25_norm = normalize_scores(bm25_results)
    dense_norm = normalize_scores(dense_results)

    merged = {}

    for r in bm25_norm:
        isbn = r["isbn"]

        if isbn not in merged:
            merged[isbn] = {
                **r,
                "bm25_score": 0.0,
                "dense_score": 0.0,
                "bm25_raw_score": None,
                "dense_raw_score": None,
                "bm25_result": None,
                "dense_result": None,
            }

        fill_metadata(merged[isbn], r)

        merged[isbn]["bm25_score"] = r["normalized_score"]
        merged[isbn]["bm25_raw_score"] = r["score"]
        merged[isbn]["bm25_result"] = r

    for r in dense_norm:
        isbn = r["isbn"]

        if isbn not in merged:
            merged[isbn] = {
                **r,
                "bm25_score": 0.0,
                "dense_score": 0.0,
                "bm25_raw_score": None,
                "dense_raw_score": None,
                "bm25_result": None,
                "dense_result": None,
            }

        fill_metadata(merged[isbn], r)

        merged[isbn]["dense_score"] = r["normalized_score"]
        merged[isbn]["dense_raw_score"] = r["score"]
        merged[isbn]["dense_result"] = r

    final_results = []

    for isbn, item in merged.items():
        has_bm25 = item["bm25_result"] is not None
        has_dense = item["dense_result"] is not None

        if require_both and not (has_bm25 and has_dense):
            continue

        score = (
            item["bm25_score"] * bm25_weight
            + item["dense_score"] * dense_weight
        )

        if has_bm25 and has_dense:
            score += overlap_bonus

        item["score"] = score
        item["has_bm25"] = has_bm25
        item["has_dense"] = has_dense
        item["source"] = "hybrid_full"

        final_results.append(item)

    final_results.sort(key=lambda x: x["score"], reverse=True)

    for i, r in enumerate(final_results[:size], start=1):
        r["rank"] = i

    return final_results[:size]

#==================================================================
#                            Hybrid chunk
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

def chunk_hybrid(
    result,
    size=20,
    bm25_weight=0.5,
    dense_weight=0.5,
    bm25_candidate_size=100,
    dense_candidate_size=100,
    num_candidates=300,
    top_k_per_book=3
):
    bm25_results = chunk_bm25(
        result=result,
        index_name="books_review_chunk",
        size=bm25_candidate_size,
        candidate_size=bm25_candidate_size,
        top_k_per_book=top_k_per_book
    )

    dense_results = chunk_dense(
        result=result,
        index_name="books_review_chunk",
        size=dense_candidate_size,
        candidate_size=dense_candidate_size,
        num_candidates=num_candidates,
        top_k_per_book=top_k_per_book
    )

    bm25_norm = normalize_scores(bm25_results)
    dense_norm = normalize_scores(dense_results)

    merged = {}

    for r in bm25_norm:
        isbn = r["isbn"]

        if isbn not in merged:
            merged[isbn] = {
                **r,
                "bm25_score": 0.0,
                "dense_score": 0.0,
                "bm25_raw_score": None,
                "dense_raw_score": None,
                "bm25_result": None,
                "dense_result": None,
            }

        merged[isbn]["bm25_score"] = r["normalized_score"]
        merged[isbn]["bm25_raw_score"] = r["score"]
        merged[isbn]["bm25_result"] = r

    for r in dense_norm:
        isbn = r["isbn"]

        if isbn not in merged:
            merged[isbn] = {
                **r,
                "bm25_score": 0.0,
                "dense_score": 0.0,
                "bm25_raw_score": None,
                "dense_raw_score": None,
                "bm25_result": None,
                "dense_result": None,
            }

        merged[isbn]["dense_score"] = r["normalized_score"]
        merged[isbn]["dense_raw_score"] = r["score"]
        merged[isbn]["dense_result"] = r

    final_results = []

    for isbn, item in merged.items():
        hybrid_score = (
            item["bm25_score"] * bm25_weight
            + item["dense_score"] * dense_weight
        )

        item["score"] = hybrid_score
        item["source"] = "hybrid_chunk"
        final_results.append(item)

    final_results.sort(key=lambda x: x["score"], reverse=True)

    for i, r in enumerate(final_results[:size], start=1):
        r["rank"] = i

    return final_results[:size]