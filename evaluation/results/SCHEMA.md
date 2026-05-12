# 평가 결과 기록 스키마

## 파일 역할 구분

| 파일 | 작성 주체 | 형식 | 내용 |
|------|-----------|------|------|
| `retrieval_results.jsonl` | 스크립트 자동 생성 | JSONL | candidates(중첩 배열) + 정량 지표 |
| `rerank_results.jsonl` | 스크립트 자동 생성 | JSONL | reranked 순서 + 정량 지표 |
| `qualitative_scoring.xlsx` | 박정현(멀티턴) / 박다현(Retrieval) / 심소민(Rerank) | Excel | 정성 점수 (2/1/0) 입력 전용 |
| `summary.csv` | 스크립트 자동 생성 | CSV | JSONL + XLSX 병합 후 최종 집계 |

> 멀티턴 정량 평가(SlotMatch 등)는 사용하지 않습니다. 멀티턴은 `qualitative_scoring.xlsx`의 Sheet 1에서 정성 평가만 진행합니다.

> JSONL은 중첩 구조(candidates 배열 등)가 있어 사람이 직접 편집하기 어렵습니다.  
> 사람이 입력하는 정성 점수는 `qualitative_scoring.xlsx`에만 작성하세요.

---

평가 결과는 아래 파일에 기록합니다.

---

## 1. retrieval_results.jsonl

BM25 검색 정량 + 정성 평가 결과. 세션 1개당 1 JSON 줄.

**실행 전제:**
- 입력 쿼리: `session_eval.jsonl`의 `expected_rag_query` (gold query)
- `hit_at_10: false`인 세션은 `retrieval_status: "fail"`로 기록하고 reranking 평가에서 제외

```jsonc
{
  "session_id": "T001-P001-A",
  "template_id": "T001",
  "user_id": "P001-A",
  "query_type": "anchor_based",
  "eval_date": "2026-05-15",

  // 사용한 쿼리 (추적용)
  "rag_query_used": {
    "keyword_query": ["에세이", "위로", "가볍게"],
    "semantic_query": "지쳐있을 때 읽기 좋은 가벼운 에세이",
    "filters": { "coarse_category": ["시/에세이"] },
    "score_boost": { "fine_category": ["테마에세이"] }
  },

  // 세션 상태: "pass" | "fail"
  // fail이면 rerank_results에 포함하지 않음
  "retrieval_status": "pass",

  // BM25 top-k 결과 (reranking의 입력이 됨)
  // injected: true → relevant이지만 top-10 밖에 있어 하위에 삽입한 항목
  // hard_negative는 BM25가 자연적으로 가져온 경우에만 포함 (주입 안 함)
  "k": 10,
  "candidates": [
    { "rank": 1,  "isbn": "9788937460449", "bm25_score": 12.34, "injected": false },
    { "rank": 2,  "isbn": "9788932920191", "bm25_score": 11.20, "injected": false },
    { "rank": 3,  "isbn": "9788901234567", "bm25_score": 10.50, "injected": false },
    { "rank": 10, "isbn": "9788901111111", "bm25_score":  6.10, "injected": false },
    { "rank": 11, "isbn": "9788954642507", "bm25_score":  0.00, "injected": true  }
  ],

  // 정량 지표 (자동 계산, candidates 기준)
  "hit_at_10": true,                  // relevant_isbns 중 1개 이상 top-10 (주입 제외)
  "recall_at_10": 0.67,               // top-10 내 자연 포함된 relevant 비율
  "mrr_at_10": 0.33,                  // 첫 relevant의 순위 역수 (주입 제외)
  "binary_ndcg_at_10": 0.58,
  "injected_count": 1                 // 주입된 relevant 수
  // 정성 점수는 qualitative_scoring.xlsx에 기록 (human + LLM-judge 이중 평가)
}
```

---

## 2. rerank_results.jsonl

리랭킹 정량 + 정성 평가 결과. 세션 1개당 1 JSON 줄.

**실행 전제:**
- 입력: `retrieval_results.jsonl`의 `candidates` (retrieval_status=pass인 세션만)
- 동일한 candidates로 리랭커를 실행해야 함 (재실행 금지)

```jsonc
{
  "session_id": "T001-P001-A",
  "template_id": "T001",
  "user_id": "P001-A",
  "query_type": "anchor_based",
  "eval_date": "2026-05-15",

  // 리랭킹 후 순서
  "reranked": [
    { "rank": 1, "isbn": "9788937460449", "rerank_score": 0.95 },
    { "rank": 2, "isbn": "9788954642507", "rerank_score": 0.88 },
    { "rank": 3, "isbn": "9788932920191", "rerank_score": 0.82 }
  ],

  // 정량 지표 (자동 계산)
  "available_top3_pass": true,        // 시나리오별 가용 도서 top-3 내
  "top1_rerank_available": true,      // 1순위 대출가능 여부
  "explanation_checklist_pass": true  // ExplanationChecklist 통과
  // 정성 점수는 qualitative_scoring.xlsx에 기록 (human + LLM-judge 이중 평가)
}
```

---

## 3. summary.csv

세션 전체 통합 집계. 행 1개 = 세션 1개.

| 컬럼 | 타입 | 설명 |
|------|------|------|
| session_id | str | T004-P001-B |
| template_id | str | T004 |
| user_id | str | P001-B |
| query_type | str | anchor_based 등 |
| multiturn_total_f | int | 0–12, 통합 점수 (_F 기준) |
| multiturn_pass | bool | |
| multiturn_conflict | bool | |H-L|=2 항목 존재 여부 |
| retrieval_status | str | "pass" \| "fail" (fail이면 이후 컬럼 null) |
| retrieval_hit_at_10 | bool | 주입 제외 기준 |
| retrieval_recall_at_10 | float | 주입 제외 기준 |
| retrieval_mrr_at_10 | float | 주입 제외 기준 |
| retrieval_injected_count | int | 주입된 relevant 수 |
| retrieval_qualitative_total_f | int | 0–10, 통합 점수 |
| retrieval_qualitative_pass | bool | |
| retrieval_conflict | bool | |H-L|=2 항목 존재 여부 |
| rerank_available_top3_pass | bool | retrieval_status=pass인 세션만 |
| rerank_qualitative_total_f | int | 0–10, 통합 점수 |
| rerank_qualitative_pass | bool | |
| rerank_conflict | bool | |H-L|=2 항목 존재 여부 |
| slot_persistence_pass | bool | 멀티턴 슬롯 누적 일관성 |
| overall_pass | bool | 모든 pass 통과 시 true (conflict/fail 세션은 false) |

---

## 4. qualitative_scoring.xlsx

인간 평가자와 LLM-judge가 **독립적으로** 채점한 후 점수를 통합합니다.  
열 접미사: `_H` = 인간, `_L` = LLM-judge, `_F` = 최종 (통합 후)

| 시트 | 담당자 |
|------|--------|
| Sheet 1: multiturn | 박정현 |
| Sheet 2: retrieval | 박다현 |
| Sheet 3: rerank | 심소민 |

> 통합 규칙: |H-L|=0 → 그대로 / |H-L|=1 → 내림 평균 / |H-L|=2 → conflict 플래그, 재검토  
> 자세한 절차는 [QUALITATIVE_RUBRIC.md](../QUALITATIVE_RUBRIC.md) 섹션 0 참고

---

### Sheet 1: multiturn — 박정현(_H) + LLM-judge(_L)

| session_id | query_type | 관련성_H | 관련성_L | 관련성_F | 명확성_H | 명확성_L | 명확성_F | 효율_H | 효율_L | 효율_F | 흐름_H | 흐름_L | 흐름_F | 반복_H | 반복_L | 반복_F | 턴수_H | 턴수_L | 턴수_F | 합계_F | pass | conflict | notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| T004-P001-B | anchor_based | 2 | 2 | 2 | 2 | 1 | 1 | 1 | 2 | 1 | 2 | 2 | 2 | 2 | 2 | 2 | 1 | 1 | 1 | 9 | Y | N | |

- 각 점수(_H, _L): 0 / 1 / 2 (드롭다운 설정 권장)
- _F: 통합 규칙 자동 계산 (IF+FLOOR 수식)
- 합계_F: SUM(_F 열)
- pass: 합계_F ≥ 8이면 Y
- conflict: 어느 항목이든 |_H - _L| = 2이면 Y

---

### Sheet 2: retrieval — 박다현(_H) + LLM-judge(_L)

| session_id | query_type | 관련도포함_H | 관련도포함_L | 관련도포함_F | 결과다양성_H | 결과다양성_L | 결과다양성_F | 쿼리정합_H | 쿼리정합_L | 쿼리정합_F | HN배제_H | HN배제_L | HN배제_F | 카테고리_H | 카테고리_L | 카테고리_F | 합계_F | pass | conflict | notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| T004-P001-B | anchor_based | 2 | 2 | 2 | 1 | 1 | 1 | 2 | 2 | 2 | 2 | 2 | 2 | 1 | 2 | 1 | 8 | Y | N | |

- 항목: 관련도포함 / 결과다양성 / 쿼리정합 / HN배제 / 카테고리적합
- pass: 합계_F ≥ 7이면 Y

---

### Sheet 3: rerank — 심소민(_H) + LLM-judge(_L)

| session_id | query_type | 정답순위_H | 정답순위_L | 정답순위_F | 가용성_H | 가용성_L | 가용성_F | 다양성_H | 다양성_L | 다양성_F | HN억제_H | HN억제_L | HN억제_F | 설명일치_H | 설명일치_L | 설명일치_F | 합계_F | pass | conflict | notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| T004-P001-B | anchor_based | 2 | 2 | 2 | 2 | 2 | 2 | 1 | 1 | 1 | 2 | 2 | 2 | 2 | 2 | 2 | 9 | Y | N | |

- 항목: 정답순위 / 가용성반영 / 다양성유지 / HN억제 / 설명일치
- pass: 합계_F ≥ 7이면 Y

---

### conflict 처리 절차

```
conflict = Y 인 세션 발생 시:
  1. 인간 평가자와 LLM-judge 점수 비교
  2. 해당 대화 로그 재검토
  3. 의견 조율 후 _F 열 수동 확정
  4. notes 열에 사유 기재
```

---

## 결과 파일 위치

```
evaluation/
  results/
    SCHEMA.md                    ← 이 파일
    retrieval_results.jsonl      ← 스크립트 자동 생성 (candidates + 정량 지표)
    rerank_results.jsonl         ← 스크립트 자동 생성 (reranked + 정량 지표)
    qualitative_scoring.xlsx     ← 사람 입력 (정성 점수, 멀티턴 포함)
    summary.csv                  ← 스크립트 병합 (JSONL + XLSX → 최종 집계)
```

> `turn_eval_results.jsonl`은 사용하지 않습니다. 멀티턴 점수는 `qualitative_scoring.xlsx` Sheet 1에서만 기록합니다.

**병합 순서:**
```
retrieval_results.jsonl  ─┐
rerank_results.jsonl     ─┼→ merge_script.py → summary.csv
qualitative_scoring.xlsx ─┘
```
