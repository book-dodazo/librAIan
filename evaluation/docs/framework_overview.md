# librAIan 평가셋 설계서

> **한 줄 요약**  
> 대화에서 정보를 잘 뽑았는지(Turn-level) + 그 정보로 좋은 책을 잘 찾았는지(Session/E2E), 두 가지를 따로 평가한다.

---

## 1. 전체 구조

```
evaluation/
├── dataset/
│   ├── onboarding_data.json         ← 사용자 온보딩 데이터 5개 페르소나 3개의 샘플 총 15개
│   ├── session_data_templates.json  ← 심소민 작성. 박정현·박다현 병렬 작업 기준점
│   └── session_eval.jsonl           ← 평가 입력 데이터 (대화 스크립트 + 검색→재정렬→추천 기준)
├── evaluate.py                     ← 평가 실행 (BM25→리랭크→지표 계산→결과 저장)
├── metrics/                        ← Hit@k, Recall@k, MRR, NDCG 계산 함수
├── results/                        ← 실행 결과 저장 (JSONL, XLSX, CSV)
└── notebooks/                      ← 결과 분석·시각화
```

```
평가 흐름

dataset/session_eval.jsonl
    ↓
[멀티턴] conversation_script로 시스템 실행
    → 질문 품질·흐름을 정성 루브릭으로 평가 (QUALITATIVE_RUBRIC.md)
    ↓
evaluate.py
    백엔드 run_bm25_search, run_reranker 직접 import
    expected_rag_query(gold query) 기준으로 실행
    ↓
results/retrieval_results.jsonl
results/rerank_results.jsonl
    ↓
qualitative_scoring.xlsx (수동 채점)
    ↓
results/summary.csv
```

---

## 2. 평가 코퍼스

```
전체 데이터: 약 10만 건
평가 코퍼스: 카테고리별 20% 균등 샘플 (~22,732건)
분포: 전체 데이터와 유사 (대표성 확보)
```

> 검색 지표(Hit@10 등)의 **절대값**은 코퍼스 크기에 영향을 받으므로,  
> MVP에서는 방향 비교(BM25 vs Dense vs Hybrid) 중심으로 해석한다.

---

## 3. 스키마 확정

### 3-1. `onboarding_data` (사용자 장기 취향)

```json
{
  "user_id": "P001-A",
  "persona": 1,
  "name": "김지유",
  "age": 23,
  "region": "서울 마포구",
  "recent_liked_books": [
    { "title": "아무튼, 계속", "author": "김연수" },
    { "title": "불안의 서",   "author": "페르난두 페소아" }
  ],
  "preferred_length": "300p 이하",
  "disliked_keywords": ["tense", "dark", "informative"],
  "frequent_libraries": [
    "마포구립서강도서관",
    "이화여자대학교 도서관"
  ],
  "preferred_categories": [
    { "main": "시/에세이", "sub": "테마에세이" },
    { "main": "소설",     "sub": "한국소설" }
  ]
}
```

- 실제 Retrieval, Reranking 단계에서 사용할 데이터는 
질의 이해 단계에서 각각 사용할 필드만을 정해서 넘겨준다. 
- 사용 예시: 
  | 필드 | 사용 단계 |
  |------|-----------|
  | `recent_liked_books` | Reranking (유사 책 boost) |
  | `preferred_length` | Reranking (soft penalty) |
  | `disliked_keywords` | Reranking (penalty) |
  | `frequent_libraries` | Availability 체크 |
  | `preferred_categories` | Reranking (soft boost), 모호한 질의 시 Retrieval 보조 |

---

### 3-2. `session_data` (현재 대화에서 추출한 즉시 의도)

> 코드 기준: `SessionContext` (`backend/app/modules/slot/schema.py`)

```json
{
  "original_query": "요즘 지쳐서 가볍게 읽을 수 있는 에세이 추천해줘",
  "anchor": null,
  "slots": {
    "topic": {
      "coarse": ["시/에세이"],
      "fine":   ["테마에세이"],
      "subject": [],
      "source": "direct"
    },
    "purpose":       { "value": "재미", "source": "inferred" },
    "reading_level": { "value": "easy", "source": "direct"   },
    "mood":          { "value": "지쳐있음, 위로가 필요함", "source": "direct" },
    "constraints":   [],
    "availability_required": false
  },
  "turn_count": 2,
  "asked_slots": ["purpose"],
  "ready_for_rag": true
}
```

#### anchor 예시 (맞는지 모름)

```json
{ "anchor": { "value": "채식주의자", "type": "book_title" } }
```

#### anchor type 종류

| type | 예시 발화 |
|------|-----------|
| `book_title` | "채식주의자 같은 책 추천해줘" |
| `author` | "한강 작가 다른 책 있어?" |
| `series` | "해리포터 시리즈 다음 권" |
| `library` | "마포 도서관에서 빌릴 수 있는 책" |


#### SlotSource 의미

| source | 의미 | 시스템 동작 |
|--------|------|-------------|
| `direct` | 발화에 명시됨 | 그대로 사용 |
| `inferred` | 문맥으로 추론됨 | 확인 카드 노출 후 사용 |
| `ambiguous` | 해석이 2개 이상 | 선택지 질문 생성 |
| `null` | 언급 없음 | 필수 slot이면 질문 생성 |

---

## 4. `session_eval.jsonl` 스키마

> **평가 대상**: 멀티턴 대화 시나리오 실행 + 완성된 session_data로 검색→재정렬→대출확인을 잘 하는가  
> 멀티턴 질문 품질은 **정성 루브릭으로만 평가** (`QUALITATIVE_RUBRIC.md`)

```json
{
  "eval_id": "session_001",
  "query_type": "pure_mood_state",

  // 평가자가 시스템에 순서대로 입력할 사용자 발화 목록
  "conversation_script": [
    "요즘 너무 지쳐있어서 가볍게 읽을 수 있는 에세이 추천해줘",
    "재미있게 읽고 싶어요"
  ],

  "session_data": {},

  "onboarding_data": {},

  "expected_data_usage": {
    "retrieval_uses": "session_only",
    "reranking_uses": ["disliked_keywords", "preferred_categories"],
    "availability_uses": "frequent_libraries"
  },

  "expected_rag_query": {
    "keyword_query": ["에세이", "위로", "가볍게"],
    "semantic_query": "지쳐있을 때 읽기 좋은 가벼운 에세이",
    "filters": {
      "coarse_category": ["시/에세이"],
      "target_reader": null,
      "custom_constraints": []
    },
    "constraints": {
      "author": [],
      "author_non": [],
      "page_range": [],
      "pub_year": []
    },
    "score_boost": {
      "fine_category": ["테마에세이"],
      "subject": []
    },
    "availability_required": false,
    "anchor": null
  },

  "retrieval_eval": {
    "methods": ["bm25"],
    "planned_extensions": ["dense", "hybrid"],
    "primary_k": 10,
    "compare_metrics": ["Hit@10", "Recall@10", "MRR@10", "BinaryNDCG@10"]
  },

  "relevance_labels": {
    "relevant_isbns": [ // 정확히 3개
      "9788937460449",
      "9788932920191",
      "9788954642507"
    ],
    "hard_negative_isbns": [ // 정확히 3개
      { "isbn": "9788901234567", "reason": "topic_confusion", "note": "제목에 에세이 포함되지만 실제로는 강의록" },
      { "isbn": "9788901111111", "reason": "level_mismatch", "note": "분류는 맞지만 내용이 무겁고 어두운 에세이" },
      { "isbn": "9788901222222", "reason": "anchor_confusion", "note": "같은 저자의 다른 분위기 작품" }
    ]
  },

  "availability_expectation": {
    "library": "마포구립서강도서관",
    "mode": "standard",
    "top1_rerank_available": true,
    "expected_output_structure": "available_top3"
  }
}
```

---

## 5. Query Type 7종

> query_type은 **첫 발화 기준**으로 결정한다.  
> 최종 session_data의 모양이 아니라, 사용자가 처음에 어떻게 의도를 표현했는가를 분류한다.

| # | type | 첫 발화 특징 | 예시 발화 | 핵심 평가 능력 |
|---|------|------------|-----------|--------------|
| 1 | `anchor_based` | anchor + 추가 slot 함께 명시 | "한강 소설 중에 짧은 거" | anchor + slot 동시 추출 |
| 2 | `topic_purpose` | topic, purpose 모두 직접 명시 | "심리학 공부하려는데 입문서 있어?" | 명확한 발화에서 정밀 추출 |
| 3 | `topic_constraint` | topic + 제약 조건 명시 | "300페이지 이하 SF 소설" | constraints 파싱 정확도 |
| 4 | `pure_topic` | topic만 있고 나머지는 null | "철학 책 추천해줘" | 부족한 정보에서 적절한 질문 생성 |
| 5 | `pure_mood_state` | mood만 있고 topic 없음 | "요즘 너무 지쳐있어" | mood → topic 추론 능력 |
| 6 | `availability_first` | 대출 가능 여부 명시 | "지금 바로 빌릴 수 있는 책" | availability_required 즉시 감지 |
| 7 | `broad_ambiguous` | 대부분 null, 매우 모호 | "뭔가 읽고 싶은데 뭘 읽을지 모르겠어" | 질문 우선순위 결정 능력 |

---

## 6. 지표 정의

### 멀티턴 지표

멀티턴 대화 품질은 **정성 루브릭**으로만 평가한다 (QUALITATIVE_RUBRIC.md 섹션 1 참고).  
정량 지표(SlotMatch 등)는 사용하지 않는다.

### Session/E2E 지표

| 지표 | 의미 | 비고 |
|------|------|------|
| `DataUsagePass` | session/onboarding 사용 여부가 expected와 일치하는가 | |
| `RagQueryPass` | RAG query가 핵심 조건(주제·목적·제약)을 포함하는가 | |
| `Hit@10` | Top10 안에 relevant 도서가 1권 이상 있는가 (0/1) | |
| `Recall@10` | Top10 중 relevant_isbns를 몇 % 포함했는가 | |
| `MRR@10` | 첫 relevant 도서의 순위 역수 평균 | 1위=1.0, 2위=0.5, … |
| `BinaryNDCG@10` | relevant 도서가 상위에 배치됐는가 | |
| `HardNegativeNotTop3` | hard_negative_isbns가 Top3에 없는가 (0/1) | |
| `AvailableTop3Pass` | 최종 출력 Top3가 모두 대출 가능한가 (0/1) | 전체 시나리오 공통 |
| `BestAppendedPass` | 리랭킹 1등 도서가 4번째로 추가됐는가 (0/1) | Scenario B 전용 |
| `StrictNoAppendPass` | strict 모드에서 대출 불가 도서가 없는가 (0/1) | Scenario C 전용 |
| `ExplanationChecklistPass` | checklist 항목 모두 충족하는가 | ⚠️ Generation 미구현으로 보류 |

---

## 7. Availability 출력 시나리오

```
리랭킹 Top5 확정
      ↓
사용자가 "지금 당장" 등 명시 요청?
  Yes → [Scenario C] availability_required=true   → 대출가능 Top3만 출력 (추가 없음)
  No  → 리랭킹 1등이 대출 가능?
          Yes → [Scenario A] → 대출가능 Top3만 출력
          No  → [Scenario B] → 대출가능 Top3 + 리랭킹 1등 추가 출력
```

| Scenario | availability_required | top1_rerank_available | expected_output_structure |
|----------|------|-----------------------|--------------------------|
| A | `false` | `true` | `available_top3` |
| B | `false` | `false` | `available_top3_plus_best` |
| C | `true` | 무관 | `available_top3` |

---

## 8. `data_usage_case` 태그

| 태그 | 설명 | 주로 쓰이는 query_type |
|------|------|----------------------|
| `session_only` | session_data만으로 충분 | anchor_based, topic_purpose, topic_constraint |
| `session_plus_onboarding_rerank` | retrieval은 session, reranking에 onboarding 활용 | pure_topic, pure_mood_state |
| `onboarding_for_ambiguous_query` | 모호한 질의 → onboarding으로 retrieval 보조 | broad_ambiguous |
| `session_priority_conflict` | session과 onboarding 취향 충돌 → session 우선 | pure_mood_state 일부 |
| `availability_from_onboarding_location` | onboarding의 도서관 정보로 availability 체크 | availability_first |

---

## 9. Hard Negative 유형

| reason | 의미 | 예시 |
|--------|------|------|
| `topic_confusion` | 표면상 유사하나 실제 주제 다름 | 심리학 질의에 자기계발서 |
| `level_mismatch` | 주제는 맞지만 난이도·분위기 불일치 | easy 원하는데 학술 논문집 |
| `anchor_confusion` | anchor와 같은 저자·장르지만 작풍이 완전히 다름 | |
| `availability_confusion` | 주제 맞지만 해당 도서관 미보유 | availability_first 케이스 |

---

## 10. MVP 구성 (총 21개)

| 파일 | 내용 | 수량 |
|------|------|------|
| `session_eval.jsonl` | Query Type 7종 × 3개 (conversation_script 포함) | 21개 |

---

## 11. 작업 구조

- 1단계: 데이터셋 작성

```
심소민: session_data_templates.json 21개 확정
        ↓
박정현: conversation_script 작성       ←→  박다현: relevance_labels 라벨링
        session_data 기입                    (relevant 3권 + HN 3권 × 21개)
        expected_rag_query 작성
        ↓                              ↓
심소민: session_eval.jsonl 통합
```
- 2단계: 평가 실행 (데이터셋 완성 후)
```
박정현이 실제 시스템에 conversation_script 입력
    ↓
멀티턴 대화 진행 → 정성 평가 (Sheet 1)
    ↓
시스템이 rag_query 생성
    ↓
evaluate.py: expected_rag_query(gold)로 BM25 실행
    ↓
박다현이 retrieval 결과 정성 평가 (Sheet 2)
    ↓
심소민이 rerank 결과 정성 평가 (Sheet 3)
```


---

## 참고 문서

| 문서 | 내용 |
|------|------|
| [EVAL_SCHEMA_GUIDE.md](./EVAL_SCHEMA_GUIDE.md) | 각 필드의 왜/어떻게 설명 |
| [LABELING_GUIDE.md](./LABELING_GUIDE.md) | 단계별 라벨링 작성 방법 |
| [TASK_ASSIGNMENT.md](./TASK_ASSIGNMENT.md) | 팀원별 역할 분담 |
| [dataset/session_data_templates.json](./dataset/session_data_templates.json) | 21개 session_data 템플릿 (병렬 작업 기준점) |
