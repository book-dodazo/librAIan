# Reranker 실험: 최적 모델 선정

## 목표

MRR@10 기준 최적 reranker를 선정하여 운영 코드(`backend/app/modules/reranker/`)에 반영한다.

---

## 실험 파이프라인

```
[1단계] Gold Candidate Pool 생성
        21 시나리오 × ~70권 → relevance grade 0~3 라벨링
               ↓
[2단계] book_text Ablation (3모델 × 5variant × 21시나리오 = 315번)
        모델별 최적 variant 선정 (MRR@10 기준)
               ↓
[3단계] 모델별 최적 variant 고정 후 최종 성능 비교
        Cross-encoder 3개 + LLM Listwise(EXAONE) + CLOVA(참고)
               ↓
[최종]  MRR@10 기준 최적 모델 선정 → 운영 코드 반영
```

---

## 폴더 구조

```
experiments/rerank/
├── README.md                            # 이 파일
├── src/
│   ├── book_text_variants.py            # A~E 5가지 variant 포맷 함수
│   └── cross_encoder_reranker.py        # CrossEncoder 공통 래퍼
├── data/
│   ├── gold_candidate_pool.json         # 1단계 결과
│   └── results/
│       ├── ablation/                    # 2단계: {variant}_{model}.json × 15개
│       └── final/                       # 3단계: final_comparison.json + PNG
└── notebooks/
    ├── 01_gold_candidate_pool.ipynb     # 1단계: 후보군 구성
    ├── 02_book_text_ablation.ipynb      # 2단계: 315번 ablation
    └── 03_final_comparison.ipynb        # 3단계: 최종 비교 & 시각화
```

---

## 기존 인프라 재활용

| 경로 | 용도 |
|------|------|
| `evaluation/dataset/goldset_final.json` | Gold Candidate Pool 베이스 (final_grade 0~3, 2,519건) |
| `evaluation/dataset/scenario_data_after_retrieval.json` | 21개 시나리오 RAG query (semantic_query 등) |
| `evaluation/metrics/metrics.py` | `mrr_at_k()`, `ndcg_at_k()`, `hit_at_k()` |
| `backend/app/modules/reranker/clova_reranker.py` | CLOVA reranker (참고용) |

---

## 1단계: Gold Candidate Pool

**전략**: 기존 `goldset_final.json` 재활용 (추가 라벨링 없음)
- 시나리오당 평균 ~81개 후보, `final_grade ≥ 2` = relevant
- Variant D를 위해 hybrid `retrieval_rank` / `retrieval_score` 첨부

**출력 스키마** (`data/gold_candidate_pool.json`):
```json
[
  {
    "scenario_id": "S01",
    "semantic_query": "...",
    "candidates": [
      {
        "isbn": "...",
        "title": "...",
        "author": "...",
        "publisher": "...",
        "large_cate": [...],
        "mid_cate": [...],
        "small_cate": [...],
        "book_intro": "...",
        "book_index": "...",
        "review_text": "...",
        "final_grade": 2,
        "retrieval_rank": 3,
        "retrieval_score": 0.82
      }
    ]
  }
]
```

---

## 2단계: book_text Ablation

### 5가지 Variant

| Variant | 포함 필드 | 설계 의도 |
|---------|-----------|-----------|
| A (baseline) | 도서명 + 카테고리 + 책소개 | 핵심 3가지만 |
| B | A + 목차(book_index) | 구체적 내용 정보 추가 효과 |
| C | A + 저자 + 출판사 | 메타 정보 효과 확인 |
| D | A + 검색순위 + 검색점수 | retrieval 신호 노출 시 역효과 여부 |
| E (현재) | 전체 필드 | 현재 운영 기준 |

### Cross-encoder 3개 모델

| 모델 | HuggingFace ID | 파라미터 | 특징 |
|------|---------------|---------|------|
| BGE | `BAAI/bge-reranker-v2-m3` | 568M | mDeBERTa 기반, 가장 강력 |
| GTE | `Alibaba-NLP/gte-multilingual-reranker-base` | 305M | 경량, 다국어 |
| Jina | `jinaai/jina-reranker-v2-base-multilingual` | 278M | 경량, 다국어 |

> **추가 고려**: `BAAI/bge-reranker-v2-gemma` (2B, Gemma 기반) — 더 강력하지만 GPU 16GB+ 필요

**선정 기준**: MRR@10 평균 기준 모델별 최적 variant → 3단계로

---

## 3단계: 최종 모델 비교

| 모델 | 유형 | variant |
|------|------|---------|
| BGE (`bge-reranker-v2-m3`) | Cross-encoder | 2단계에서 선정 |
| GTE (`gte-multilingual-reranker-base`) | Cross-encoder | 2단계에서 선정 |
| Jina (`jina-reranker-v2-base-multilingual`) | Cross-encoder | 2단계에서 선정 |
| EXAONE (`LG-AI-Research/EXAONE-3.5-7.8B-Instruct`) | LLM Listwise | - |
| CLOVA Reranker | API | 참고용 |

**주요 metric**: MRR@10 (primary), NDCG@10 (secondary), Hit@10

---

## 평가 기준

- `final_grade ≥ 2` = relevant
- Primary metric: **MRR@10**
- 시나리오 타입별(`query_type`) 성능 분해로 모델 특성 파악

---

## 최종 선정 결과 (운영 반영)

- **선정 모델**: BGE Cross-Encoder (`BAAI/bge-reranker-v2-m3`)
- **입력 포맷**: BD variant — 도서명 + 중분류 카테고리 + 책소개 + 리뷰 (Ablation NDCG@10 기준 `BD > D > B > C > A > E`)
- **Score fusion**: `final_score = 0.2 × norm(retrieval_score) + 0.8 × norm(bge_score)` (retrieval 가중치는 env `BGE_RETRIEVAL_WEIGHT`로 조정)
- **운영 반영 위치**: [`backend/app/modules/reranker/bge_reranker.py`](../../backend/app/modules/reranker/bge_reranker.py) — GPU 자동 감지(`torch.cuda.is_available()`), sentence-transformers/torch 미설치 시 hybrid 결과로 fallback
- CLOVA Reranker(`clova_reranker.py`)는 초기 baseline으로 대체·보존됨
