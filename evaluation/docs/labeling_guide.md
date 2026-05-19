# 평가셋 라벨링 가이드

> 이 문서는 평가셋 샘플을 직접 작성하는 팀원을 위한 실무 지침서입니다.  
> 스키마 이해가 먼저라면 [EVAL_SCHEMA_GUIDE.md](./EVAL_SCHEMA_GUIDE.md)를 먼저 읽으세요.  
> 정성 평가(2/1/0 척도) 기준은 [QUALITATIVE_RUBRIC.md](./QUALITATIVE_RUBRIC.md)를 참고하세요.

---

## 라벨링 역할 분담

| 역할 | 담당 작업 | 산출물 |
|------|-----------|--------|
| **대화 설계자** | 시나리오 작성, conversation_script + session_data 작성 | `session_eval.jsonl`의 `conversation_script`, `session_data` |
| **도서 라벨러** | relevant / hard_negative 선정 | `session_eval.jsonl`의 `relevance_labels` |
| **파이프라인 설계자** | expected_rag_query, availability_expectation 작성 | `session_eval.jsonl` 나머지 필드 |

> 한 사람이 여러 역할을 맡아도 됩니다. 역할을 구분한 이유는 **작업 순서** 때문입니다.  
> 반드시 위에서 아래 순서로 진행하세요. 도서 라벨링은 대화 설계 후에 합니다.  
> 정성 평가(qualitative_scoring.xlsx)는 라벨링 완료 후 별도로 진행합니다 ([QUALITATIVE_RUBRIC.md](./QUALITATIVE_RUBRIC.md) 참고).

---

## 전체 작업 흐름

```
Step 1. 시나리오 선택
        어떤 query_type × 어떤 페르소나 조합으로 할지 결정

Step 2. conversation_script + session_data 작성
        사용자 발화 목록 작성 → 최종 session_data 도출

Step 3. session_eval.jsonl에 session_data 기입
        시나리오 기반으로 session_data 직접 작성, 적합한 onboarding_data 선택

Step 4. 도서 라벨링 (session_eval)
        검색해서 relevant / hard_negative 책 선정

Step 5. 나머지 session_eval 필드 채우기
        expected_rag_query, availability_expectation 등

Step 6. 정성 평가 기록 (qualitative_scoring.xlsx)
        담당자별로 QUALITATIVE_RUBRIC.md 기준에 따라 0/1/2 점수 기입
        → 인간 평가자(_H)와 LLM-judge(_L) 독립 채점 후 _F 열 통합
        → conflict(|H-L|=2) 항목은 재협의 후 수동 확정
```

---

## Step 1. 시나리오 선택

### 어떤 조합이 필요한가

MVP 목표: 총 21개 (7종 × 3개)

| query_type | 목표 수 | 권장 페르소나 |
|------------|---------|---------------|
| `anchor_based` | 3 | 모든 페르소나 가능 |
| `topic_purpose` | 3 | persona 1, 2, 4 |
| `topic_constraint` | 3 | persona 2, 4 |
| `pure_topic` | 3 | 모든 페르소나 가능 |
| `pure_mood_state` | 3 | persona 1, 3, 5 |
| `availability_first` | 3 | 모든 페르소나 가능 |
| `broad_ambiguous` | 3 | persona 3, 5 (독서 비경험자) |

### 좋은 시나리오란?

✅ **좋은 시나리오**
- 실제 도서관 이용자가 쓸 법한 자연스러운 발화
- 멀티턴이 필요한 이유가 명확함 (slot이 비어있어서, 추론이 필요해서)
- 추천 결과가 명확히 갈리는 케이스 (모호하지 않은 정답)

❌ **피해야 할 시나리오**
- 너무 완벽한 첫 질의 ("심리학 입문서 300페이지 이하 2020년 이후 출판 추천해줘")
- 정답 도서가 1권밖에 없는 케이스
- 실제로 검색이 안 되는 마이너한 주제

---

## Step 2. `conversation_script` 작성

`session_eval.jsonl`의 `conversation_script` 필드에 평가자가 시스템에 순서대로 입력할 **사용자 발화 목록**만 작성합니다.  
slot 상태나 expected 필드는 기록하지 않습니다 — 질문 품질은 정성 루브릭으로만 평가합니다.

### 형식

```json
"conversation_script": [
  "첫 번째 발화",
  "두 번째 발화",
  "세 번째 발화"
]
```

### 작성 기준

- **첫 발화**가 `query_type`을 결정합니다 (EVAL_Design.md 섹션 6 참고)
- 시스템이 질문을 하면 평가자가 다음 발화를 입력하는 흐름으로 설계합니다
- `anchor_based`처럼 1턴으로 충분한 경우 발화 1개도 가능합니다

### 예시 — pure_mood_state (3턴)

```json
"conversation_script": [
  "요즘 너무 지쳐있어서 뭔가 읽고 싶은데 뭘 읽어야 할지 모르겠어",
  "소설 같은 거 읽어보고 싶어",
  "그냥 재미있게 읽을 수 있는 걸로"
]
```

### 예시 — anchor_based (1턴)

```json
"conversation_script": [
  "채식주의자 같은 책 추천해줘"
]
```

---

## Step 3. `session_data` 작성

conversation_script 시나리오를 머릿속에서 실행해보고, **마지막 턴 이후 기대되는 session_data**를 직접 작성합니다.  
`onboarding_data`는 적합한 페르소나 샘플(`dataset/onboarding_data.json`)에서 골라 붙입니다.

### session_data 작성 규칙

**topic**
```json
"topic": {
  "coarse": ["시/에세이"],
  "fine":   ["테마에세이"],
  "subject": [],
  "source": "direct"
}
```
- 발화에 직접 언급 → `source: "direct"`
- 문맥 추론 → `source: "inferred"`
- 언급 없음 → `coarse: [], fine: [], subject: [], source: "null"`

**purpose / reading_level / mood**
```json
"purpose": { "value": "재미", "source": "inferred" }
```
- 발화에 명시 → `source: "direct"`
- 문맥 추론 → `source: "inferred"`
- 해석이 2가지 이상 → `source: "ambiguous"`
- 언급 없음 → `"value": null, "source": "null"`

#### source 판단 기준표

| 발화 예시 | slot | source | 이유 |
|-----------|------|--------|------|
| "에세이 추천해줘" | topic | direct | 장르 직접 언급 |
| "지쳐있어서" | purpose | inferred | "재미"로 추론 가능 |
| "뭔가 읽고 싶어" | topic | null | 주제 언급 없음 |
| "가벼운 건지 깊은 건지 모르겠어" | reading_level | ambiguous | 두 가지 해석 가능 |

#### `ready_for_rag` 판단 기준

| 조건 | ready_for_rag |
|------|---------------|
| anchor가 있음 | `true` |
| topic + (purpose 또는 reading_level) 이 채워짐 | `true` |
| topic만 direct이고 나머지 모두 null | `false` |
| 모든 slot이 null | `false` |

---

## Step 4. 도서 라벨링

> 가장 중요하고 시간이 많이 걸리는 단계입니다.

### 4-1. relevant_isbns 선정

**이 질의에 대한 추천으로 나와도 적절한 책**을 선정합니다.

#### 선정 기준 (모두 충족해야 함)

| 기준 | 확인 방법 |
|------|-----------|
| **주제 일치** | session_data의 topic.coarse / fine과 맞는가 | 
| **목적 일치** | purpose에 맞는 성격의 책인가 |
| **난이도 일치** | reading_level에 맞는 책인가 |
| **분위기 일치** | mood가 있다면 분위기가 맞는가 |
| **제약 충족** | constraints가 있다면 충족하는가 |

#### 몇 권을 선정할까?

MVP 평가셋 기준: **정확히 3권** 선정합니다.

> 3권으로 고정하면 Recall@10, MRR@10 계산이 일관됩니다.  
> 확신이 없는 책은 포함하지 않고, 명확히 적합한 3권을 고릅니다.  
> (3권 이상 확실한 경우에는 최대 5권까지 허용)

#### 도서 검색 방법

1. 실제 librAIan 검색 결과에서 확인
2. 교보문고 / 알라딘 카테고리 필터 활용
3. 사서 추천 목록 참고

#### 주의사항

- ISBN은 **13자리 ISBN-13**으로 기록합니다 (`9788937460449` 형식)
- 절판된 책은 제외합니다 (검색 결과에 나올 수 없음)
- 확신이 없으면 포함하지 않습니다 (정답 오염 방지)

---

### 4-2. hard_negative_isbns 선정

**겉보기에는 관련 있어 보이지만 실제로는 부적합한 책**을 선정합니다.  
일반 오답과 달리 **시스템이 헷갈릴 가능성이 높은 책**을 골라야 합니다.

#### hard negative의 조건

```
다음 중 하나 이상 해당하면서, 동시에 나머지 기준은 어긋나는 책
```

| reason | 겉으로 맞는 것 | 실제로 어긋나는 것 | 예시 |
|--------|---------------|-------------------|------|
| `topic_confusion` | 제목/저자가 유사 | 실제 주제 다름 | 심리학 질의에 → 자기계발서 |
| `level_mismatch` | 주제 일치 | 난이도/분위기 불일치 | easy 원하는데 → 학술 논문집 |
| `anchor_confusion` | anchor와 같은 저자/장르 | 작풍이 완전히 다름 | 한강 요청에 → 한강 번역서 (원작과 분위기 다름) |
| `availability_confusion` | 주제 완벽히 일치 | 해당 도서관 미보유 | availability_first 케이스에서 |

#### hard negative 수량

MVP 평가셋 기준: **정확히 3권** 선정합니다.

> `HardNegativeNotTop3` 지표 계산의 일관성을 위해 3권으로 고정합니다.  
> 가능하면 서로 다른 reason 유형으로 채우세요.

#### hard negative 작성 예시

```json
"hard_negative_isbns": [
  {
    "isbn": "9788936434120",
    "reason": "topic_confusion",
    "note": "제목에 '에세이'가 들어가지만 실제로는 강의록"
  },
  {
    "isbn": "9788934941842",
    "reason": "level_mismatch",
    "note": "같은 소설 장르지만 매우 어둡고 무거운 내용"
  }
]
```

> `note`는 선택 사항이지만 작성하면 나중에 분석할 때 매우 유용합니다.

---

### 4-3. 라벨링 셀프 체크리스트

작성 후 아래를 확인합니다.

```
□ relevant_isbns에 있는 책들이 실제로 해당 질의에 맞는가?
□ 한 권씩 직접 검색해서 주제/난이도/분위기 확인했는가?
□ hard_negative가 relevant와 명확히 구분되는가?
□ hard_negative에 reason이 모두 채워져 있는가?
□ ISBN이 13자리 숫자인가? (하이픈 없이)
□ 절판 도서는 제외했는가?
```

---

## Step 5. 나머지 session_eval 필드 채우기

### 5-1. `expected_rag_query` 작성

session_data를 보고 "이 상태라면 어떤 검색 쿼리가 나와야 하는가"를 작성합니다.

```json
"expected_rag_query": {
  "keyword_query": ["소설", "재미", "가볍게"],
  "semantic_query": "지쳐있을 때 가볍게 읽을 수 있는 재미있는 소설",
  "filters": {
    "coarse_category": ["소설"],
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
    "fine_category": [],
    "subject": []
  },
  "availability_required": false,
  "anchor": null
}
```

#### 작성 팁

| session_data 상태 | expected_rag_query 반영 방식 |
|------------------|------------------------------|
| `topic.coarse` 있음 | → `filters.coarse_category`에 포함 |
| `topic.fine` 있음 | → `score_boost.fine_category`에 포함 |
| `topic.subject` 있음 | → `score_boost.subject` + `semantic_query`에 포함 |
| `mood` 있음 | → `semantic_query`에 감성 표현 포함 |
| `purpose` 있음 | → `keyword_query`에 목적 키워드 포함 |
| `constraints.page` 있음 | → `constraints.page_range`에 `{operator, value}` 형식으로 |
| `constraints.author` 있음 | → `constraints.author` 또는 `author_non`에 |
| `anchor` 있음 | → `anchor` 필드에 반영, `filters`에 author/title 추가 |
| 대상 독자 명시 | → `filters.target_reader`에 기입 |
| 자유 형식 제약 | → `filters.custom_constraints`에 자연어로 |

---

### 5-2. `availability_expectation` 작성

availability와 무관한 일반 질의는 `null`로 설정합니다.  
그 외에는 아래 3가지 시나리오 중 하나를 선택해서 작성합니다.

#### 어떤 시나리오인지 먼저 판단

```
사용자 query에 "지금 당장", "바로 빌릴 수 있는" 등이 있는가?
        ↓
       Yes → Scenario C (strict)
        No
        ↓
  이 케이스에서 리랭킹 1등 도서가 대출 가능할 것 같은가?
  (실제 ISBN으로 정보나루 API 확인하거나, 샘플 데이터 기준 판단)
        ↓
      Yes → Scenario A
       No → Scenario B
```

#### Scenario A — 1등이 대출 가능, 대출가능 Top3만 출력

```json
"availability_expectation": {
  "library": "마포구립서강도서관",
  "mode": "standard",
  "top1_rerank_available": true,
  "expected_output_structure": "available_top3"
}
```

#### Scenario B — 1등이 대출 불가, 대출가능 Top3 + 1등 추가 출력

```json
"availability_expectation": {
  "library": "마포구립서강도서관",
  "mode": "standard",
  "top1_rerank_available": false,
  "expected_output_structure": "available_top3_plus_best"
}
```

#### Scenario C — "지금 당장 대출가능" 명시, 추가 출력 없음

```json
"availability_expectation": {
  "library": "마포구립서강도서관",
  "mode": "strict",
  "top1_rerank_available": false,
  "expected_output_structure": "available_top3"
}
```

#### `library` 결정 규칙

1. 세션에서 도서관을 직접 언급했으면 → 그 도서관
2. 언급 없으면 → `onboarding_data.frequent_libraries[0]`

#### 적용 지표

| 시나리오 | 평가 지표 |
|----------|-----------|
| A, B, C 공통 | `AvailableTop3Pass` — 출력 Top3가 모두 대출 가능한가 |
| B 전용 | `BestAppendedPass` — 리랭킹 1등 도서가 추가됐는가 |
| C 전용 | `StrictNoAppendPass` — 추가 출력이 없는가 |

---

### 5-3. `explanation_checklist` — ⚠️ Generation 미구현으로 현재 보류

추천 설명 생성(Generation) 기능이 구현되기 전까지 이 필드는 `session_eval.jsonl`에 작성하지 않는다.  
Generation 구현 완료 후 이 섹션에 작성 지침을 추가할 예정이다.

> 리랭킹 루브릭의 **항목 5 (설명 일치)**도 동일한 이유로 평가 보류 중 ([QUALITATIVE_RUBRIC.md](./QUALITATIVE_RUBRIC.md) 참고).

---

## 완성된 session_eval 샘플

```json
{
  "eval_id": "session_006",
  "query_type": "pure_mood_state",
  "data_usage_case": "session_plus_onboarding_rerank",

  "conversation_script": [
    "요즘 너무 지쳐있어서 뭔가 읽고 싶은데 뭘 읽어야 할지 모르겠어",
    "소설 같은 거 읽어보고 싶어",
    "그냥 재미있게 읽을 수 있는 걸로"
  ],

  "session_data": {
    "original_query": "요즘 너무 지쳐있어서 뭔가 읽고 싶은데 뭘 읽어야 할지 모르겠어",
    "anchor": null,
    "slots": {
      "topic":         { "coarse": ["소설"], "fine": [], "subject": [], "source": "direct" },
      "purpose":       { "value": "재미", "source": "direct" },
      "reading_level": { "value": "easy", "source": "inferred" },
      "mood":          { "value": "지쳐있음, 무기력함", "source": "direct" },
      "constraints":   [],
      "availability_required": false
    },
    "turn_count": 3,
    "asked_slots": ["topic", "purpose"],
    "ready_for_rag": true
  },

  "onboarding_data": {
    "user_id": "P001-A",
    "persona": 1,
    "name": "김지유",
    "age": 23,
    "region": "서울 마포구",
    "recent_liked_books": [
      { "title": "아무튼, 계속", "author": "김연수" }
    ],
    "preferred_length": "200~300p",
    "disliked_keywords": ["tense", "dark"],
    "frequent_libraries": ["마포구립서강도서관"],
    "preferred_categories": [
      { "main": "소설", "sub": "한국소설" }
    ]
  },

  "expected_data_usage": {
    "retrieval_uses": "session_only",
    "reranking_uses": ["disliked_keywords", "preferred_categories", "recent_liked_books"],
    "availability_uses": null
  },

  "expected_rag_query": {
    "keyword_query": ["소설", "재미", "가볍게"],
    "semantic_query": "지쳐있을 때 위로가 되는 가볍게 읽을 수 있는 소설",
    "filters": {
      "coarse_category": ["소설"],
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
      "fine_category": [],
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
    "relevant_isbns": [
      "9788937460449",
      "9788932920191",
      "9788954651929"
    ],
    "hard_negative_isbns": [
      {
        "isbn": "9788936434120",
        "reason": "level_mismatch",
        "note": "소설 맞지만 매우 어둡고 무거운 내용 — disliked_keyword 'dark' 해당"
      },
      {
        "isbn": "9788954600001",
        "reason": "topic_confusion",
        "note": "제목에 '소설'이 들어가지만 실제로는 강의 모음집"
      },
      {
        "isbn": "9788901111223",
        "reason": "anchor_confusion",
        "note": "비슷한 분위기 소설로 분류되지만 작풍이 완전히 다름"
      }
    ]
  },

  "availability_expectation": null
}
```

---

## 자주 하는 실수

### conversation_script + session_data 작성 시

| 실수 | 올바른 방법 |
|------|-------------|
| anchor 있는데 session_data의 `ready_for_rag: false` | anchor 있으면 항상 `true` |
| session_data에 `null` source인데 value가 있음 | `source: "null"`이면 `value`도 `null` |
| conversation_script에 시스템 발화 포함 | 사용자 발화만 기록 (시스템 응답 제외) |

### 도서 라벨링 시

| 실수 | 올바른 방법 |
|------|-------------|
| relevant와 hard_negative 중복 | 하나의 ISBN은 둘 중 하나에만 |
| ISBN 10자리 사용 | 반드시 13자리 ISBN-13 |
| 절판 도서 포함 | 현재 검색 가능한 책만 |
| hard_negative에 reason 없음 | 반드시 reason 기재 |

---

## eval_id 네이밍 규칙

```
session_eval: session_001 ~ session_021
```

---

## 작업 배분 템플릿

샘플을 나눠서 작업할 때 아래 표를 활용하세요.

| eval_id | query_type | 담당자 | session_eval | 검토 완료 |
|---------|------------|--------|--------------|----------|
| 001 | anchor_based | | ☐ | ☐ |
| 002 | anchor_based | | ☐ | ☐ |
| 003 | anchor_based | | ☐ | ☐ |
| 004 | topic_purpose | | ☐ | ☐ |
| 005 | topic_purpose | | ☐ | ☐ |
| 006 | topic_purpose | | ☐ | ☐ |
| 007 | topic_constraint | | ☐ | ☐ |
| 008 | topic_constraint | | ☐ | ☐ |
| 009 | topic_constraint | | ☐ | ☐ |
| 010 | pure_topic | | ☐ | ☐ |
| 011 | pure_topic | | ☐ | ☐ |
| 012 | pure_topic | | ☐ | ☐ |
| 013 | pure_mood_state | | ☐ | ☐ |
| 014 | pure_mood_state | | ☐ | ☐ |
| 015 | pure_mood_state | | ☐ | ☐ |
| 016 | availability_first | | ☐ | ☐ |
| 017 | availability_first | | ☐ | ☐ |
| 018 | availability_first | | ☐ | ☐ |
| 019 | broad_ambiguous | | ☐ | ☐ |
| 020 | broad_ambiguous | | ☐ | ☐ |
| 021 | broad_ambiguous | | ☐ | ☐ |
