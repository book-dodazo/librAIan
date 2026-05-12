# 평가 역할 분담

> 작성 기준일: 2026-05-12  
> MVP 목표: `session_eval.jsonl` 21개 (query_type 7종 × 3개)  
> 작성 방법: [LABELING_GUIDE.md](./LABELING_GUIDE.md) | 채점 기준: [QUALITATIVE_RUBRIC.md](./QUALITATIVE_RUBRIC.md)

---

## 전체 흐름

평가는 두 단계로 나뉩니다.

```
Phase 1. 데이터셋 작성       ← 지금 할 일
Phase 2. 평가 실행 및 채점   ← 데이터셋 완성 후
```

---

## Phase 1. 데이터셋 작성

### 작업 순서

```
[심소민] session_data_templates.json 21개 확정 → 공유
                        ↓
        ┌───────────────┴────────────────┐
   [박정현]                          [박다현, 심소민]
   conversation_script 작성         relevance_labels 라벨링
   session_data 기입                (relevant 3권 + HN 3권 × 21개)
   expected_rag_query 작성
        └───────────────┬────────────────┘
                        ↓
   [심소민] session_eval.jsonl 통합 완성
```

박정현·박다현은 `session_data_templates.json` 공유 후 **동시에** 시작할 수 있습니다.

---

### 심소민 — 설계 총괄

#### 선행 작업 (박정현·박다현 시작 전)

**산출물:** `evaluation/dataset/session_data_templates.json`

query_type 7종 × 3개 = 21개 session_data 템플릿을 확정합니다.  
각 템플릿에는 다음이 포함되어야 합니다.

| 필드 | 내용 |
|------|------|
| `template_id` | T004 ~ T024 |
| `query_type` | 7종 중 하나 |
| `original_query` | 첫 발화 |
| `anchor` | anchor가 있으면 기입, 없으면 null |
| `slots` | 최종 slot 상태 (value + source 포함) |
| `asked_slots` | 시스템이 질문해야 할 슬롯 목록 |
| `turn_count` | 예상 턴 수 |
| `assigned_persona` | 사용할 onboarding 페르소나 |

#### 후행 작업 (박정현·박다현 완성 후)

**산출물:** `evaluation/dataset/session_eval.jsonl`

두 사람의 결과물을 받아 아래 필드를 추가하고 통합합니다.

| 필드 | 내용 |
|------|------|
| `onboarding_data` | `assigned_persona`에 맞는 데이터 붙이기 |
| `expected_data_usage` | retrieval/reranking에서 onboarding을 어떻게 쓸지 |
| `availability_expectation` | availability_first 케이스에 작성 (나머지 null) |
| `retrieval_eval` | 전체 공통값 (`methods: ["bm25"]`, `primary_k: 10` 등) |

**통합 검토 체크리스트**
```
□ eval_id 001~021이 query_type별 3개씩 채워졌는가?
□ conversation_script의 첫 발화가 original_query와 일치하는가?
□ session_data의 asked_slots와 conversation_script 턴 수가 맞는가?
□ relevance_labels에 relevant 3개, hard_negative 3개가 채워졌는가?
□ assigned_persona와 onboarding_data가 일치하는가?
```

---

### 박정현 — 대화 설계 + 멀티턴 정성평가

#### Phase 1 작업

**산출물:** `session_eval.jsonl`의 `conversation_script`, `session_data`, `expected_rag_query` 필드 (21개)

`session_data_templates.json`을 받아서 각 케이스마다 두 가지를 작성합니다.

**① `conversation_script` — 사용자 발화 목록**

시스템에 순서대로 입력할 발화를 직접 씁니다.

```json
"conversation_script": [
  "요즘 너무 지쳐있어서 뭔가 읽고 싶은데 뭘 읽어야 할지 모르겠어",
  "소설 같은 거 읽어보고 싶어",
  "그냥 재미있게 읽을 수 있는 걸로"
]
```

작성 기준:
- `original_query`를 첫 발화로 사용
- `asked_slots`에 있는 슬롯에 대해 자연스럽게 답하는 발화 추가
- `turn_count`와 발화 수를 맞출 것
- 시스템 발화는 포함하지 않음 (사용자 발화만)

**② `session_data` — 최종 슬롯 상태**

템플릿의 내용을 `session_eval.jsonl` 형식에 맞게 옮겨 씁니다.  
(templates에 이미 정의된 값을 그대로 사용)

**② `expected_rag_query` — 이상적인 검색 쿼리 설계**

session_data를 보고 "이 슬롯 상태라면 검색 쿼리가 어떻게 나와야 하는가"를 작성합니다.  
conversation_script와 session_data를 함께 작성하므로 자연스럽게 이어서 작성합니다.

| session_data 상태 | expected_rag_query 반영 방식 |
|------------------|------------------------------|
| `topic.coarse` 있음 | `filters.coarse_category`에 포함 |
| `topic.fine` 있음 | `score_boost.fine_category`에 포함 |
| `topic.subject` 있음 | `score_boost.subject` + `semantic_query`에 포함 |
| `mood` 있음 | `semantic_query`에 감성 표현 포함 |
| `purpose` 있음 | `keyword_query`에 목적 키워드 포함 |
| `constraints.page` 있음 | `constraints.page_range`에 `{operator, value}` 형식으로 |
| `constraints.author` 있음 | `constraints.author` 또는 `author_non`에 |
| `anchor` 있음 | `anchor` 필드 + `filters`에 title/author |
| 나머지 미사용 필드 | 빈 값으로 명시 (`null`, `[]`) |

**작성 시 주의사항**
```
□ anchor가 있으면 conversation_script 첫 발화에 자연스럽게 포함되어 있는가?
□ asked_slots에 있는 슬롯이 conversation_script에서 실제로 답변되는가?
□ availability_first 케이스는 첫 발화에 "지금 바로", "빌릴 수 있는" 등이 포함되는가?
□ expected_rag_query의 filters/score_boost가 session_data slots와 일치하는가?
```

---

### 박다현 — 도서 라벨링 + Retrieval 정성평가

#### Phase 1 작업

**산출물:** `session_eval.jsonl`의 `relevance_labels` 필드 (21개)

`session_data_templates.json`을 받아서 각 케이스의 정답/오답 도서를 선정합니다.

**`relevance_labels` — 정답/오답 도서 선정**

| 필드 | 수량 | 기준 |
|------|------|------|
| `relevant_isbns` | 정확히 3개 | session_data의 topic·purpose·mood·constraints를 모두 충족하는 책 |
| `hard_negative_isbns` | 정확히 3개 | 겉보기엔 맞지만 실제로 부적합한 책 (reason 필수) |

hard_negative reason 유형:

| reason | 예시 |
|--------|------|
| `topic_confusion` | 제목엔 "에세이"지만 실제론 강의록 |
| `level_mismatch` | 주제는 맞지만 무겁고 어두운 내용 |
| `anchor_confusion` | 같은 저자지만 완전히 다른 작풍 |
| `availability_confusion` | 주제 맞지만 해당 도서관 미보유 |

**라벨링 체크리스트**
```
□ relevant 3권을 실제로 검색해서 주제·분위기·난이도 확인했는가?
□ hard_negative가 relevant와 ISBN 중복되지 않는가?
□ 모든 ISBN이 13자리이고 절판 도서가 아닌가?
□ hard_negative에 reason이 기재되어 있는가?
```

---

## Phase 2. 평가 실행 및 채점

데이터셋 완성 후 순서대로 진행합니다.

```
① 박정현: conversation_script로 실제 시스템 실행 → 멀티턴 정성평가
         (qualitative_scoring.xlsx Sheet 1 기입)
         ↓
② 심소민: evaluate.py 실행
         → results/retrieval_results.jsonl 생성
         → results/rerank_results.jsonl 생성
         ↓
③ 박다현: retrieval 결과 정성평가
         (qualitative_scoring.xlsx Sheet 2 기입)
         ↓
④ 심소민: rerank 결과 정성평가
         (qualitative_scoring.xlsx Sheet 3 기입)
         ↓
⑤ 심소민: summary.csv 생성 (JSONL + XLSX 병합)
```

### 정성평가 방법 (공통)

각 담당자가 **독립적으로** 채점 후 LLM-judge 점수와 통합합니다.

```
1. 담당자(_H)가 먼저 독립 채점 → xlsx _H 열 기입
2. LLM-judge(_L)가 독립 채점 → xlsx _L 열 기입
3. |H-L| = 0 → 그대로 / |H-L| = 1 → 내림 평균 / |H-L| = 2 → conflict 플래그
```

채점 기준은 [QUALITATIVE_RUBRIC.md](./QUALITATIVE_RUBRIC.md) 참고.

---

## 산출물 정리

| 단계 | 파일 | 작성 주체 |
|------|------|-----------|
| Phase 1 | `dataset/session_data_templates.json` | 심소민 (선행) |
| Phase 1 | `dataset/session_eval.jsonl` | 박정현 + 박다현 + 심소민 (통합) |
| Phase 2 | `results/retrieval_results.jsonl` | evaluate.py 자동 생성 |
| Phase 2 | `results/rerank_results.jsonl` | evaluate.py 자동 생성 |
| Phase 2 | `results/qualitative_scoring.xlsx` | 박정현(Sheet1) / 박다현(Sheet2) / 심소민(Sheet3) |
| Phase 2 | `results/summary.csv` | 스크립트 자동 생성 |

---

## 필드별 담당자 한눈에 보기

| session_eval.jsonl 필드 | 담당 |
|------------------------|------|
| `conversation_script` | 박정현 |
| `session_data` | 박정현 (templates에서 옮겨 쓰기) |
| `expected_rag_query` | 박정현 |
| `relevance_labels` | 박다현 |
| `onboarding_data` | 심소민 |
| `expected_data_usage` | 심소민 |
| `retrieval_eval` | 심소민 (공통값 일괄 적용) |
| `availability_expectation` | 심소민 |
