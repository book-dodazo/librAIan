# librAIan 평가셋 설계서

> **한 줄 요약**  
> 대화에서 정보를 잘 뽑았는지(Turn-level) + 그 정보로 좋은 책을 잘 찾았는지(Session/E2E), 두 가지를 따로 평가한다.

---

## 1. 전체 구조

```
evaluation/
├── dataset/
│   ├── turn_eval.jsonl      ← 대화 이해 평가 (멀티턴 slot 추출)
│   └── session_eval.jsonl   ← 추천 파이프라인 평가 (검색→재정렬→추천)
├── metrics/                 ← 지표 구현
├── retrieval/               ← BM25 검색 평가
├── reranking/               ← 재정렬 평가
└── notebooks/               ← 분석 노트북
```

```
평가 흐름

[사용자 대화]
    ↓
[Turn-level 평가] ← slot을 올바르게 추출했는가? 추가 질문 타이밍이 맞는가?
    ↓  (session_data 완성)
[Session/E2E 평가] ← 완성된 session_data로 검색·재정렬·추천이 잘 되는가?
```

---

## 2. 스키마 확정

### 2-1. `onboarding_data` (사용자 장기 취향)

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
  "preferred_length": "200~300p",
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

| 필드 | 설명 | 사용 단계 |
|------|------|-----------|
| `recent_liked_books` | 최근 좋았던 책 (최대 3권) | Reranking (유사 책 boost) |
| `preferred_length` | 선호 분량 | Reranking (soft constraint) |
| `disliked_keywords` | 싫어하는 분위기 키워드 | Reranking (penalty) |
| `frequent_libraries` | 자주 가는 도서관 (최대 2개) | Availability 체크 |
| `preferred_categories` | 선호 카테고리 | Reranking (soft boost) |

---

### 2-2. `session_data` (현재 대화에서 추출한 즉시 의도)

> **코드 기준**: `SessionContext` (`backend/app/modules/slot/schema.py`)

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
    "purpose": {
      "value": "재미",
      "source": "inferred"
    },
    "reading_level": {
      "value": "easy",
      "source": "direct"
    },
    "mood": {
      "value": "지쳐있고 위로가 필요함",
      "source": "direct"
    },
    "constraints": [],
    "availability_required": false
  },

  "turn_count": 2,
  "asked_slots": ["purpose"],
  "ready_for_rag": true
}
```

#### anchor 예시 (책 제목·저자 언급 시)
```json
{
  "anchor": {
    "value": "채식주의자",
    "type": "book_title"
  }
}
```

#### anchor type 종류
| type | 예시 |
|------|------|
| `book_title` | "채식주의자 같은 책 추천해줘" |
| `author` | "한강 작가 다른 책 있어?" |
| `series` | "해리포터 시리즈 다음 권" |
| `library` | "마포 도서관에서 빌릴 수 있는 책" |

#### SlotSource 의미
| source | 의미 | 처리 방식 |
|--------|------|-----------|
| `direct` | 발화에 직접 명시 | 바로 확정 |
| `inferred` | 문맥으로 추론 | 확인 카드 노출 후 확정 |
| `ambiguous` | 해석이 2개 이상 | 선택지 질문 생성 |
| `null` | 언급 없음 | 필수 slot이면 질문 생성 |

---

## 3. `turn_eval.jsonl` 스키마

> **평가 대상**: 멀티턴 대화에서 slot을 올바르게 추출하고, 적절한 시점에 추가 질문을 하는가

```json
{
  "eval_id": "turn_001",
  "query_type": "pure_mood_state",
  "eval_type": "multi_turn_state",

  "steps": [
    {
      "turn": 1,
      "user_input": "요즘 너무 지쳐있어서 가볍게 읽을 수 있는 에세이 추천해줘",
      "expected": {
        "slots": {
          "topic":         { "coarse": ["시/에세이"], "fine": ["테마에세이"], "source": "direct" },
          "purpose":       { "value": "재미", "source": "inferred" },
          "reading_level": { "value": "easy", "source": "direct" },
          "mood":          { "value": "지쳐있음, 위로 필요", "source": "direct" }
        },
        "anchor": null,
        "needs_clarification": true,
        "clarification_target_slots": ["purpose"],
        "ready_for_rag": false
      }
    },
    {
      "turn": 2,
      "user_input": "재미있게 읽고 싶어요",
      "expected": {
        "slots": {
          "topic":         { "coarse": ["시/에세이"], "fine": ["테마에세이"], "source": "direct" },
          "purpose":       { "value": "재미", "source": "direct" },
          "reading_level": { "value": "easy", "source": "direct" },
          "mood":          { "value": "지쳐있음, 위로 필요", "source": "direct" }
        },
        "anchor": null,
        "needs_clarification": false,
        "ready_for_rag": true
      }
    }
  ],

  "expected_final_session_data": {
    "original_query": "요즘 너무 지쳐있어서 가볍게 읽을 수 있는 에세이 추천해줘",
    "anchor": null,
    "slots": {
      "topic":         { "coarse": ["시/에세이"], "fine": ["테마에세이"], "subject": [], "source": "direct" },
      "purpose":       { "value": "재미", "source": "direct" },
      "reading_level": { "value": "easy", "source": "direct" },
      "mood":          { "value": "지쳐있음, 위로 필요", "source": "direct" },
      "constraints":   [],
      "availability_required": false
    },
    "turn_count": 2,
    "asked_slots": ["purpose"],
    "ready_for_rag": true
  }
}
```

---

## 4. `session_eval.jsonl` 스키마

> **평가 대상**: 완성된 session_data + onboarding_data를 받아서 검색→재정렬→대출확인→추천을 잘 하는가

```json
{
  "eval_id": "session_001",
  "query_type": "pure_mood_state",
  "data_usage_case": "session_plus_onboarding_rerank",

  "session_data": { },

  "onboarding_data": { },

  "expected_data_usage": {
    "retrieval_uses": "session_only",
    "reranking_uses": ["disliked_keywords", "preferred_categories"],
    "availability_uses": "frequent_libraries"
  },

  "expected_rag_query": {
    "keyword_query": ["에세이", "위로", "가볍게"],
    "semantic_query": "지쳐있을 때 읽기 좋은 가벼운 에세이",
    "filters": {
      "coarse_category": ["시/에세이"]
    },
    "score_boost": {
      "fine_category": ["테마에세이"]
    },
    "availability_required": false
  },

  "retrieval_eval": {
    "methods": ["bm25"],
    "planned_extensions": ["dense", "hybrid"],
    "primary_k": 10,
    "compare_metrics": ["Hit@10", "Recall@10", "MRR@10", "BinaryNDCG@10"]
  },

  "relevance_labels": {
    "relevant_isbns": [
      "9788937460449",
      "9788932920191"
    ],
    "hard_negative_isbns": [
      { "isbn": "9788901234567", "reason": "topic_confusion" }
    ]
  },

  "availability_expectation": {
    "library": "마포구립서강도서관",
    "mode": "standard",
    "top1_rerank_available": true,
    "expected_output_structure": "available_top3"
  },

  "explanation_checklist": {
    "mentions_mood": true,
    "mentions_topic": true,
    "mentions_reading_level": true,
    "uses_onboarding_signal": false,
    "avoids_disliked_keywords": true
  }
}
```

---

## 5. Query Type 8종

| # | type | 설명 | 예시 발화 |
|---|------|------|-----------|
| 1 | `exact_lookup` | 특정 책/저자 지목 | "채식주의자 같은 책 추천해줘" |
| 2 | `anchor_based` | anchor + 추가 조건 | "한강 소설 중에 짧은 거" |
| 3 | `topic_purpose` | 주제 + 목적 명시 | "심리학 공부하려는데 입문서 있어?" |
| 4 | `topic_constraint` | 주제 + 제약 명시 | "300페이지 이하 SF 소설" |
| 5 | `pure_topic` | 주제만 | "철학 책 추천해줘" |
| 6 | `pure_mood_state` | 기분/상태만 | "요즘 너무 지쳐있어" |
| 7 | `availability_first` | 대출 가능 우선 | "지금 바로 빌릴 수 있는 책" |
| 8 | `broad_ambiguous` | 모호한 포괄 질의 | "뭔가 읽고 싶은데 뭐 읽을지 모르겠어" |

---

## 6. 지표 정의

### Turn-level 지표

| 지표 | 계산 방식 | 비고 |
|------|-----------|------|
| `SlotMatch` | 추출된 slot value & source가 expected와 일치한 비율 | anchor 포함 |
| `SourceMatch` | source 판단(`direct`/`inferred`/`ambiguous`/`null`)이 맞는 비율 | |
| `ClarificationAccuracy` | 추가 질문 여부가 expected와 일치하는가 (0/1) | |
| `TargetSlotAccuracy` | 어떤 slot을 질문했는지가 expected와 일치하는가 (0/1) | |
| `ReadyForRagPass` | RAG 진입 시점이 expected와 일치하는가 (0/1) | |
| `SlotPersistencePass` | 이전 턴에서 `direct`로 확정된 slot이 이후 턴에서도 유지되는가 | 멀티턴 regression 감지 |

### Session/E2E 지표

| 지표 | 계산 방식 | 비고 |
|------|-----------|------|
| `DataUsagePass` | session/onboarding 사용 여부가 expected와 일치하는가 | |
| `RagQueryPass` | RAG query가 핵심 조건(주제·목적·제약)을 포함하는가 | |
| `Hit@10` | Top10 안에 relevant 도서가 1권 이상 있는가 (0/1) | |
| `Recall@10` | Top10 중 relevant_isbns를 몇 % 포함했는가 | |
| `MRR@10` | 첫 relevant 도서의 순위 역수 평균 | 1위=1.0, 2위=0.5, ... |
| `BinaryNDCG@10` | relevant 도서가 상위에 배치됐는가 | |
| `HardNegativeNotTop3` | hard_negative_isbns가 Top3에 없는가 (0/1) | |
| `AvailableTop3Pass` | 최종 출력 Top3가 모두 대출 가능한가 (0/1) | 전체 시나리오 공통 |
| `BestAppendedPass` | 리랭킹 1등 도서가 4번째로 추가됐는가 (0/1) | Scenario B 전용 |
| `StrictNoAppendPass` | strict 모드에서 대출 불가 도서가 없는가 (0/1) | Scenario C 전용 |
| `ExplanationChecklistPass` | checklist 항목 모두 충족하는가 | |

---

## 7. `data_usage_case` 태그

| 태그 | 설명 | 언제 쓰는가 |
|------|------|-------------|
| `session_only` | session_data만 사용 | 명확한 주제/조건 질의 |
| `session_plus_onboarding_rerank` | retrieval은 session, reranking에 onboarding 사용 | 기분/분위기 질의 |
| `onboarding_for_ambiguous_query` | 모호한 질의 → onboarding으로 retrieval 보조 | broad_ambiguous |
| `session_priority_conflict` | session과 onboarding이 충돌 → session 우선 | ex) 평소 SF 좋아하지만 지금은 에세이 원함 |
| `availability_from_onboarding_location` | onboarding의 도서관 정보로 availability 체크 | |

---

## 8. Hard Negative 유형

| reason | 의미 | 예시 |
|--------|------|------|
| `topic_confusion` | 표면상 유사하나 실제 다른 주제 | 심리학 질의에 자기계발서 |
| `level_mismatch` | 주제는 맞지만 난이도 불일치 | easy 원하는데 학술서 |
| `anchor_confusion` | anchor 작가와 유사하지만 완전 다른 작풍 | |
| `availability_confusion` | 주제 맞지만 대출 불가 | availability_first 케이스에서 |

---

## 9. MVP 구성 (총 48개)

| | 내용 | 수량 |
|--|------|------|
| **turn_eval.jsonl** | Query Type 8종 × 3개 | 24개 |
| **session_eval.jsonl** | Query Type 8종 × 3개 | 24개 |

Query Type별 `data_usage_case` 배분 권장:

| query_type | data_usage_case |
|------------|-----------------|
| `exact_lookup` | `session_only` |
| `anchor_based` | `session_only` |
| `topic_purpose` | `session_only` |
| `topic_constraint` | `session_only` |
| `pure_topic` | `session_plus_onboarding_rerank` |
| `pure_mood_state` | `session_plus_onboarding_rerank` |
| `availability_first` | `availability_from_onboarding_location` |
| `broad_ambiguous` | `onboarding_for_ambiguous_query` |

---

## 10. 구현 순서

```
Step 1. 이 문서 기준으로 JSONL 스키마 validator 작성
        (잘못된 샘플이 들어오면 바로 오류)

Step 2. turn_eval.jsonl 24개 작성
        - query_type별 3개
        - 멀티턴 steps 포함

Step 3. session_eval.jsonl 24개 작성
        - session_data + onboarding_data 페어링
        - relevant_isbns / hard_negative_isbns 라벨링

Step 4. 지표 구현
        - Turn-level: SlotMatch, SourceMatch, ReadyForRagPass, SlotPersistencePass
        - Session/E2E: Hit@10, Recall@10, MRR@10, BinaryNDCG@10

Step 5. BM25 retrieval 평가 실행
        → 추후 Dense/Hybrid 추가 시 같은 24개로 비교
```
