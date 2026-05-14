from elasticsearch import Elasticsearch
import numpy as np
import uuid
import time
import random
import requests
from app.core.config import settings
import os
from pathlib import Path
import json
from dotenv import load_dotenv

load_dotenv()

base = Path(__file__).resolve()

# app 폴더까지
app_dir = base.parents[2]

embedding_path = app_dir / "db" / "small_category_embeddings.json"


URL = "https://clovastudio.stream.ntruss.com/testapp/v1/api-tools/embedding/v2/"
CLOVA_API_KEY = settings.CLOVA_API_KEY

ELASTIC_URL= "https://localhost:9200"
ELASTIC_USER= "elastic"
ELASTIC_PASSWORD="dw2s3Vinv8X6ihtUy_fB"

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



es = Elasticsearch(
    ELASTIC_URL,
    basic_auth=(ELASTIC_USER, ELASTIC_PASSWORD),
    verify_certs=False
)

def cosine_similarity(a, b):
    a = np.array(a).flatten()
    b = np.array(b).flatten()
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))


def get_similar_small_categories(
    subject,
    small_category_embeddings,
    top_k=5,
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


def search_bm25_with_cate(
    result,
    small_category_embeddings=get_small_category_embeddings(),
    index_name="book_bm25_no_review",
    size=20
):
    keyword_query = " ".join(result.get("keyword_query", []))
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

    # 1. 대분류 hard filter
    if coarse_categories:
        filter_clause.append({
            "terms": {
                "large_cate": coarse_categories
            }
        })

    # 2. 원하는 작가 filter
    if authors:
        filter_clause.append({
            "bool": {
                "should": [
                    {"match_phrase": {"author": author}}
                    for author in authors
                ],
                # "minimum_should_match": 1
            }
        })

    # 3. 제외 작가 must_not
    if author_nons:
        must_not_clause.extend([
            {"match_phrase": {"author": author}}
            for author in author_nons
        ])

    # 4. 페이지 조건 filter / must_not
    page_filter, page_must_not = parse_page_conditions(page_range)

    if page_filter:
        filter_clause.append(page_filter)

    if page_must_not:
        must_not_clause.extend(page_must_not)

    # 5. 출판연도 filter
    # pub_year에 숫자가 여러 개 있으면 그중 최솟값 이상으로 처리
    if pub_years:
        min_year = min(int(y) for y in pub_years)

        filter_clause.append({
            "range": {
                "publish_date": {
                    "gte": f"{min_year}-01-01"
                }
            }
        })

    # 6. 중분류 boost
    for fc in fine_categories:
        should_clause.append({
            "term": {
                "middle_cate": {
                    "value": fc,
                    "boost": 2.0
                }
            }
        })

    # 7. 소분류 subject embedding boost
    if subjects and small_category_embeddings:
        for sub in subjects:
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
                            "boost": min(1.0 + sim, 2.0)
                        }
                    }
                })

    query_body = {
        "size": size,
        "query": {
            "bool": {
                # "filter": filter_clause,
                "must": [
                    {
                        "multi_match": {
                            "query": keyword_query,
                            "fields": [
                                "content^2",
                                "categories^2",
                                "author",
                                "title^3",
                            ],
                            "type": "best_fields",
                            "operator": "or",
                            "minimum_should_match": "1"
                        }
                    }
                ],
                # "should": should_clause,
                # "must_not": must_not_clause
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
            "isbn": hit["_source"].get("isbn"),
            "score": hit["_score"]
        }
        for i, hit in enumerate(res["hits"]["hits"])
    ]
