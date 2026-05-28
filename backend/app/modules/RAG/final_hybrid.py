from elasticsearch import Elasticsearch
from app.core.config import settings
from dotenv import load_dotenv

try:
    from sentence_transformers import SentenceTransformer
    _SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SentenceTransformer = None
    _SENTENCE_TRANSFORMERS_AVAILABLE = False


load_dotenv()

es = Elasticsearch(
    settings.ELASTIC_URL,
    basic_auth=(settings.ELASTIC_USER, settings.ELASTIC_PASSWORD),
    verify_certs=False
)

_embedding_models = {}


def load_embedding_model():
    if not _SENTENCE_TRANSFORMERS_AVAILABLE:
        raise ImportError("sentence_transformers 패키지가 설치되지 않았습니다.")

    if "kure" not in _embedding_models:
        _embedding_models["kure"] = SentenceTransformer("nlpai-lab/KURE-v1")

    return _embedding_models["kure"]


def get_embedding(text):
    model = load_embedding_model()
    return model.encode(text, normalize_embeddings=True).tolist()


def to_list(x):
    if x is None:
        return []
    if isinstance(x, list):
        return [v for v in x if v is not None and str(v).strip() != ""]
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

    if not range_body:
        return None, []

    return {"range": {"page": range_body}}, []


_COARSE_TO_ES = {
    "과학": "자연/과학",
    "역사/문화": "역사",
    "정치/사회": "사회/정치",
    "건강": "건강/취미",
    "취미/실용/스포츠": "건강/취미",
    "가정/육아": "가정/요리",
    "외국어": "국어/외국어",
    "취업/수험서": "수험서/자격증",
    "대학교재": "대학교재/전문서적",
    "어린이(초등)": "어린이",
    "어린이ELT": "어린이",
    "유아(0~7세)": "유아",
    "초등참고서": "초등학교 참고서",
    "중/고등참고서": ["중학교 참고서", "고등학교 참고서"],
}


def translate_coarse_to_es(categories):
    result = []

    for c in categories:
        mapped = _COARSE_TO_ES.get(c, c)
        if isinstance(mapped, list):
            result.extend(mapped)
        else:
            result.append(mapped)

    return result


def make_review_boost_query(query_text, boost=1.1):
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


def build_filter_clauses(result):
    filters = result.get("filters", {})
    constraints = result.get("constraints", {})
    anchor = result.get("anchor")

    coarse_categories = translate_coarse_to_es(
        to_list(filters.get("cate_depth1"))
    )
    mid_filter_categories = to_list(filters.get("cate_depth2"))

    authors = to_list(constraints.get("author"))
    author_nons = to_list(constraints.get("author_non"))
    page_range = constraints.get("page_range", [])
    pub_years = constraints.get("pub_year", [])

    filter_clause = []
    must_not_clause = []

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

    # anchor 제외 처리
    if anchor:
        anchor_value = anchor.get("value")
        anchor_type = anchor.get("type")

        if anchor_value and anchor_type == "book_title":
            must_not_clause.append({
                "match": {
                    "title": {
                        "query": anchor_value,
                        "operator": "or"
                    }
                }
            })

        elif anchor_value and anchor_type == "author":
            must_not_clause.append({
                "match_phrase": {
                    "author": anchor_value
                }
            })

        elif anchor_value and anchor_type == "series":
            must_not_clause.append({
                "multi_match": {
                    "query": anchor_value,
                    "fields": [
                        "title",
                        "content",
                        "book_intro"
                    ],
                    "operator": "or"
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
                filter_clause.append({"range": {"publish_date": {"gte": f"{year}-01-01"}}})
            elif operator == "gt":
                filter_clause.append({"range": {"publish_date": {"gt": f"{year}-12-31"}}})
            elif operator == "lte":
                filter_clause.append({"range": {"publish_date": {"lte": f"{year}-12-31"}}})
            elif operator == "lt":
                filter_clause.append({"range": {"publish_date": {"lt": f"{year}-01-01"}}})

    return filter_clause, must_not_clause


def full_bm25(result, index_name="books_review_full", size=100):
    keyword_query = " ".join(result.get("keyword_query", [])).strip()
    filter_clause, must_not_clause = build_filter_clauses(result)

    must_clause = []
    should_clause = []

    if keyword_query:
        must_clause.append({
            "multi_match": {
                "query": keyword_query,
                "fields": [
                    "title^4",
                    "category_text^2",
                    "content^3",
                    "author^0.5"
                ],
                "type": "best_fields",
                "operator": "or",
                "minimum_should_match": "1"
            }
        })

        should_clause.append(make_review_boost_query(keyword_query))

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

    res = es.search(index=index_name, body=query_body)

    return [
        {
            "rank": i + 1,
            "score": hit["_score"],
            **hit["_source"]
        }
        for i, hit in enumerate(res["hits"]["hits"])
    ]


def full_dense(result, index_name="books_review_full", size=100, num_candidates=300):
    semantic_query = result.get("semantic_query", "").strip()

    if not semantic_query:
        semantic_query = " ".join(result.get("keyword_query", [])).strip()

    filter_clause, must_not_clause = build_filter_clauses(result)
    query_vector = get_embedding(semantic_query)

    query_body = {
        "size": size,
        "knn": {
            "field": "embedding_kure",
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

    res = es.search(index=index_name, body=query_body)

    return [
        {
            "rank": i + 1,
            "score": hit["_score"],
            "dense_score": hit["_score"],
            **hit["_source"]
        }
        for i, hit in enumerate(res["hits"]["hits"])
    ]


def full_hybrid(result):
    index_name = "books_review_full_100000"

    final_size = 20
    bm25_candidate_size = 100
    dense_candidate_size = 100
    num_candidates = 300

    bm25_weight = 0.3
    dense_weight = 0.7
    rrf_k = 60

    bm25_results = full_bm25(
        result=result,
        index_name=index_name,
        size=bm25_candidate_size
    )

    dense_results = full_dense(
        result=result,
        index_name=index_name,
        size=dense_candidate_size,
        num_candidates=num_candidates
    )

    merged = {}

    for rank, r in enumerate(bm25_results, start=1):
        isbn = r.get("isbn")
        if not isbn:
            continue

        merged[isbn] = {
            **r,
            "bm25_rank": rank,
            "dense_rank": None,
            "bm25_raw_score": r.get("score"),
            "dense_raw_score": None,
            "bm25_result": r,
            "dense_result": None,
            "bm25_rrf_score": bm25_weight * (1 / (rrf_k + rank)),
            "dense_rrf_score": 0.0,
        }

    for rank, r in enumerate(dense_results, start=1):
        isbn = r.get("isbn")
        if not isbn:
            continue

        if isbn not in merged:
            merged[isbn] = {
                **r,
                "bm25_rank": None,
                "dense_rank": rank,
                "bm25_raw_score": None,
                "dense_raw_score": r.get("score"),
                "bm25_result": None,
                "dense_result": r,
                "bm25_rrf_score": 0.0,
                "dense_rrf_score": dense_weight * (1 / (rrf_k + rank)),
            }
        else:
            merged[isbn]["dense_rank"] = rank
            merged[isbn]["dense_raw_score"] = r.get("score")
            merged[isbn]["dense_result"] = r
            merged[isbn]["dense_rrf_score"] = dense_weight * (1 / (rrf_k + rank))

    final_results = []

    for isbn, item in merged.items():
        score = item["bm25_rrf_score"] + item["dense_rrf_score"]

        item["score"] = score
        item["has_bm25"] = item["bm25_result"] is not None
        item["has_dense"] = item["dense_result"] is not None
        item["source"] = "hybrid_full_rrf"

        final_results.append(item)

    final_results.sort(key=lambda x: x["score"], reverse=True)

    for i, r in enumerate(final_results[:final_size], start=1):
        r["rank"] = i

    return final_results[:final_size]