# 평가셋 스키마 해설서

> 팀원들이 평가셋의 각 필드를 이해하고 직접 샘플을 작성할 수 있도록 설명한 문서입니다.  
> 스키마 원문은 [EVAL_DESIGN.md](./EVAL_DESIGN.md)를 참고하세요.

---

## 이 문서를 읽는 순서

```
1. onboarding_data  — 사용자 장기 취향 데이터
2. session_data     — 현재 대화에서 뽑아낸 즉시 의도
3. session_eval     — 추천 파이프라인 평가셋
```

---

## 1. `onboarding_data` 해설

> 사용자가 앱에 처음 가입할 때 입력하는 취향 프로필입니다.  
> **"이 사람이 평소에 어떤 책을 좋아하는가"** 를 담습니다.

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

---

### `user_id` / `persona` / `name`

**왜 있는가**  
평가셋에서 "어떤 사람"이 질의했는지 추적하기 위해서입니다.  
같은 질의라도 20대 대학생과 60대 주부에게 어울리는 추천이 다릅니다.

**어떻게 쓰는가**  
`persona` 번호로 비슷한 취향군을 묶습니다. 평가 결과를 페르소나별로 비교할 때 사용합니다.  
`name`은 가독성용이고 평가 로직에서는 사용하지 않습니다.

```
persona 1 → 20대 문학 독자
persona 2 → 30-40대 직장인
persona 3 → 60대 이상
persona 4 → 10대 청소년
persona 5 → 독서 비경험자
```

---

### `age`

**왜 있는가**  
추천 결과 설명 시 나이대를 고려한 언어 톤을 쓰기 위해서입니다.  
또한 일부 카테고리(청소년 도서 등)를 적절히 필터/부스트할 때 사용합니다.

**어떻게 쓰는가**  
현재는 Reranking 단계에서 soft signal로 활용합니다.  
예: 15세 사용자 → `청소년` 카테고리 가중치 증가.

---

### `region` + `frequent_libraries`

**왜 따로 분리했는가**  
`region`만으로는 어느 도서관을 이용할 수 있는지 알 수 없습니다.  
같은 마포구라도 자주 가는 도서관이 다를 수 있습니다.

**어떻게 쓰는가**  
Availability 체크 단계에서 사용합니다. 사용자가 별도로 도서관을 지정하지 않으면  
`frequent_libraries`의 첫 번째 도서관을 기본값으로 사용합니다.

```
"frequent_libraries": ["마포구립서강도서관", "이화여자대학교 도서관"]
                         ↑ 기본값으로 사용              ↑ 두 번째 선택지
```

---

### `recent_liked_books`

**왜 있는가**  
이 사람이 어떤 "결"의 책을 좋아하는지 파악하기 위해서입니다.  
카테고리 선호보다 더 세밀한 취향 신호입니다.

**어떻게 쓰는가**  
Reranking 단계에서 이 책들과 유사한 책에 가중치를 줍니다.  
예: "불안의 서"를 좋아한다면 → 페르난두 페소아 스타일, 철학적 에세이 장르에 boost.

> ⚠️ 주의: `recent_liked_books`가 null인 사용자도 있습니다 (P003-C, P005-A).  
> 이 경우 `preferred_categories`만으로 Reranking합니다.

---

### `preferred_length` (수정 필요, 기준 page 이상/이하)

**왜 있는가**  
분량은 독서 피로도와 직결됩니다. 짧은 책을 선호하는 사람에게 600페이지 책을 추천하면 안 됩니다.

**어떻게 쓰는가**  
Reranking에서 soft penalty로 사용합니다. Hard filter(완전 제외)가 아닌 이유는  
사용자가 세션 중에 "이번엔 조금 길어도 괜찮아"라고 말할 수 있기 때문입니다.

```
preferred_length = "300p 이하"
→ 400p 이상 책은 Reranking 점수 소폭 감점
→ Hard filter가 아니므로 최종 Top10에 등장할 수는 있음
```

---

### `disliked_keywords`

**왜 있는가**  
카테고리 선호로는 잡을 수 없는 "분위기 거부" 신호입니다.  
예: SF는 좋아하지만 "어둡고 긴장감 있는" SF는 싫다.

**어떻게 쓰는가**  
Reranking에서 penalty로 사용합니다. 책 메타데이터의 분위기 태그와 매칭합니다.

```
disliked_keywords: ["tense", "dark"]
→ 책 태그에 "tense", "dark" 포함 시 → Reranking 점수 감점
```

> 키워드는 영어 감성 태그 기준입니다. (책 메타데이터 태그 체계와 통일)

---

### `preferred_categories`

**왜 있는가**  
사용자의 장기적인 카테고리 선호입니다. 현재 세션 질의가 모호할 때 retrieval 방향을 잡아줍니다.

**어떻게 쓰는가**  
- **모호한 질의** (`broad_ambiguous`): retrieval 자체에 onboarding 카테고리를 반영
- **명확한 질의**: retrieval은 session_data만 사용, Reranking에서 소폭 boost

```json
{ "main": "시/에세이", "sub": "테마에세이" }
   ↑ 대분류 (필터용)        ↑ 중분류 (boost용)
```

---

## 2. `session_data` 해설

> 현재 진행 중인 대화에서 LLM이 추출한 즉시 의도입니다.  
> **"지금 이 사람이 원하는 게 뭔가"** 를 담습니다.  
> 코드의 `SessionContext` 객체와 동일한 구조입니다.

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
    "purpose":       { "value": "재미",  "source": "inferred" },
    "reading_level": { "value": "easy",  "source": "direct"   },
    "mood":          { "value": "지쳐있음, 위로가 필요함", "source": "direct" },
    "constraints":   [],
    "availability_required": false
  },
  "turn_count": 2,
  "asked_slots": ["purpose"],
  "ready_for_rag": true
}
```

---

### `original_query`

**왜 있는가**  
멀티턴 대화에서 최초 질의를 기억하기 위해서입니다.  
여러 턴이 지나도 사용자가 처음에 무엇을 원했는지 잃지 않습니다.

**어떻게 쓰는가**  
RAG Query 생성 시 참조합니다. 이후 턴에서 slot이 수정되더라도  
원본 의도를 semantic_query에 반영할 때 사용합니다.

---

### `anchor` (정현님 컨펌 필요)

**왜 있는가**  
"채식주의자 같은 책"처럼 **특정 책/저자/시리즈를 기준점**으로 삼는 질의가 있습니다.  
이건 slot(채워야 할 칸)이 아니라 질의 파싱 결과이기 때문에 별도로 분리합니다.

**어떻게 쓰는가**  
- `book_title`: 해당 책과 유사한 책 검색 (임베딩 유사도)
- `author`: 해당 저자의 다른 작품, 또는 유사 작가 검색
- `library`: availability 체크 대상 도서관 지정

```
"채식주의자 같은 책 추천해줘"
→ anchor: { "value": "채식주의자", "type": "book_title" }
→ 검색 시 "채식주의자"의 임베딩을 활용해 유사 소설 찾기
```

---

### `slots.topic` — `coarse` / `fine` / `subject`

**왜 3단계로 나눴는가**  
검색 단계마다 다른 방식으로 사용하기 때문입니다.

| 필드 | 예시 | 검색에서의 역할 |
|------|------|----------------|
| `coarse` | `["시/에세이"]` | **Hard filter** — 이 카테고리만 검색 |
| `fine` | `["테마에세이"]` | **Score boost** — 이 중분류에 가중치 |
| `subject` | `["한국 근현대사"]` | **Dense 검색** — 자연어 쿼리에 포함 |

```
"한국 근현대사 책 추천해줘"
→ coarse: ["역사/문화"]   ← 이 대분류로 필터
→ fine:   ["한국사"]      ← 한국사 중분류 boost
→ subject: ["한국 근현대사"] ← dense 쿼리: "한국 근현대사를 다룬 책"
```

---

### `slots.*.source` — SlotSource

**왜 있는가**  
"사용자가 직접 말한 것"과 "시스템이 추측한 것"을 구분하기 위해서입니다.  
추측한 것은 사용자에게 확인받아야 하기 때문입니다.

| source | 의미 | 시스템 동작 |
|--------|------|-------------|
| `direct` | 발화에 명시됨 | 그대로 사용 |
| `inferred` | 문맥으로 추론됨 | 확인 카드 노출 후 사용 |
| `ambiguous` | 해석이 2개 이상 | 선택지 질문 생성 |
| `null` | 언급 없음 | 필수 slot이면 질문 생성 |

```
"요즘 지쳐서 에세이 추천해줘"

topic.source   = "direct"    ← "에세이" 직접 언급
purpose.source = "inferred"  ← "지쳐서" → '재미'로 추론 (확인 필요)
reading_level.source = "null" ← 언급 없음 (질문 생성)
```

---

### `slots.purpose`

**왜 있는가**  
같은 "경제 책"도 목적에 따라 추천이 달라집니다.

```
목적: 학습 → 입문서, 교재
목적: 교양 → 대중 경제 교양서
목적: 실용 → 재테크 실용서
목적: 재미 → 경제 소설, 에세이
```

**어떻게 쓰는가**  
RAG Query의 `semantic_query`와 `keyword_query`에 반영합니다.  
예: `목적=학습` → semantic_query에 "입문", "기초" 포함.

---

### `slots.reading_level`

**왜 있는가**  
같은 주제도 난이도 스펙트럼이 넓습니다. 철학 입문서와 칸트 원전은 다릅니다.

| 값 | 의미 | 검색 반영 |
|----|------|-----------|
| `easy` | 가볍고 빠르게 | "쉽게 읽히는", "입문" 키워드 boost |
| `medium` | 적당한 깊이 | 중립 |
| `hard` | 깊이 있게 | "심층", "학술" 키워드 boost |

---

### `slots.mood`

**왜 있는가**  
기분/감정 상태는 카테고리나 목적으로 표현하기 어렵지만 추천에 중요한 신호입니다.

**어떻게 쓰는가**  
자유형 문자열로 저장합니다. RAG Query의 `semantic_query`에 자연어로 반영합니다.

```
mood: "요즘 무기력하고 삶의 방향을 잃은 것 같음"
→ semantic_query: "무기력하고 지쳐있을 때 위로가 되는 책"
```

---

### `slots.constraints`

**왜 있는가**  
"300페이지 이하", "2020년 이후 출판", "번역서 제외" 같은 명시적 제약 조건을 담습니다.

**어떻게 쓰는가**  
RAG Query의 `constraints` 필드로 전달되어 Elasticsearch 필터/must_not에 반영됩니다.

```json
{ "type": "page_range", "value": 300, "operator": "lte", "raw": "300페이지 이하" }
   ↑ 제약 종류            ↑ 기준값      ↑ 연산자(이하)     ↑ 원문 (디버깅용)
```

#### constraint type 목록
| type | 예시 발화 |
|------|-----------|
| `page_range` | "300페이지 이하로" |
| `pub_year` | "최근 5년 이내" |
| `author` | "한강 작가 작품으로" |
| `nonauthor` | "번역서 제외해줘" |
| `availability` | "지금 바로 빌릴 수 있는 것" |
| `custom` | "영화로 나온 책" |

---

### `slots.availability_required`

**왜 있는가**  
"지금 당장 빌릴 수 있는 책"을 원하는 경우와 그냥 추천을 원하는 경우를 구분합니다.

**어떻게 쓰는가**  
`true`이면 정보나루 API를 호출해 대출 불가 도서를 결과에서 제거합니다.  
`false`이면 API 호출하지 않고 대출 가능 여부를 정보로만 표시합니다.

---

### `turn_count`

**왜 있는가**  
몇 번째 대화인지 추적합니다. 너무 많은 턴이 지나도 RAG로 넘어가지 않으면  
강제로 진행하는 로직이 있기 때문입니다.

**어떻게 쓰는가**  
평가에서는 **몇 턴 만에 `ready_for_rag`에 진입했는가**를 볼 때 사용합니다.  
대화가 너무 길어지면 사용자 경험이 나빠집니다.

---

### `asked_slots`

**왜 있는가**  
같은 slot을 두 번 물어보지 않기 위해서입니다.

**어떻게 쓰는가**  
질문 생성 전에 이 목록을 확인합니다. 이미 물어본 slot이면 건너뜁니다.

```
asked_slots: ["purpose", "reading_level"]
→ 다음 턴에서 purpose, reading_level 다시 묻지 않음
```

---

### `ready_for_rag`

**왜 있는가**  
"이제 충분한 정보가 모였으니 검색을 시작해도 된다"는 신호입니다.  
이 플래그가 `true`가 되는 순간 파이프라인이 retrieval 단계로 넘어갑니다.

**어떻게 쓰는가**  
Turn-level 평가의 핵심 지표 `ReadyForRagPass`가 이 값을 평가합니다.  
너무 일찍 진입하면 정보 부족, 너무 늦게 진입하면 대화가 길어집니다.

---

## 3. `session_eval.jsonl` 해설

> session_data가 완성되었다고 가정하고, 파이프라인 전체를 평가합니다.  
> **"좋은 재료(session_data)가 있을 때 좋은 결과가 나오는가"** 를 검사합니다.

---

### `data_usage_case`

**왜 있는가**  
session_data와 onboarding_data를 어떻게 조합해서 사용했는지를 태그로 명시합니다.  
케이스별로 성능을 분석할 수 있습니다.

| 태그 | 의미 |
|------|------|
| `session_only` | onboarding 없이 세션 정보만으로 충분한 케이스 |
| `session_plus_onboarding_rerank` | 검색은 세션으로, 재정렬에 onboarding 활용 |
| `onboarding_for_ambiguous_query` | 질의가 너무 모호해서 onboarding으로 검색 보조 |
| `session_priority_conflict` | 세션과 onboarding 취향이 충돌 → 세션 우선 |
| `availability_from_onboarding_location` | onboarding의 도서관 정보로 대출 체크 |

---

### `expected_data_usage`

**왜 있는가**  
시스템이 데이터를 올바른 단계에서 올바르게 사용했는지 검증합니다.

```json
{
  "retrieval_uses": "session_only",
  "reranking_uses": ["disliked_keywords", "preferred_categories"],
  "availability_uses": "frequent_libraries"
}
```

예: `reranking_uses`에 `disliked_keywords`가 있는데 실제로 적용 안 됐다면  
`DataUsagePass = false`.

---

### `expected_rag_query`

**왜 있는가**  
RAG Query가 올바르게 생성됐는지 검증합니다. 검색 결과보다 먼저 확인할 수 있는 중간 체크포인트입니다.

```json
{
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
}
```

> 이 gold query는 평가자가 session_data를 보고 **직접 작성**합니다. 시스템이 생성한 쿼리가 아닙니다.  
> 평가 시 expected의 핵심 필드가 실제 query에 포함되어 있으면 `RagQueryPass = true`.  
> 완전 일치를 요구하지 않습니다.

---

### `retrieval_eval`

**왜 있는가**  
검색 성능을 정량적으로 측정합니다.

```json
{
  "methods": ["bm25"],
  "planned_extensions": ["dense", "hybrid"],
  "primary_k": 10,
  "compare_metrics": ["Hit@10", "Recall@10", "MRR@10", "BinaryNDCG@10"]
}
```

- `methods`: 현재 평가할 검색 방식 (MVP는 BM25만)
- 추후 추가할 방식 (코드 구현 후 추가): ["dense", "hybrid"]
- `primary_k`: 상위 몇 개를 볼 것인가

---

### `relevance_labels`

**왜 있는가**  
검색 결과의 정답지입니다. 어떤 책이 이 질의에 맞는 추천인지를 미리 라벨링합니다.

```json
{
  "relevant_isbns": ["9788937460449", "9788932920191", "9788954642507"],
  "hard_negative_isbns": [
    { "isbn": "9788901234567", "reason": "topic_confusion" },
    { "isbn": "9788901111111", "reason": "level_mismatch" },
    { "isbn": "9788901222222", "reason": "anchor_confusion" }
  ]
}
```

> `relevant_isbns`는 정확히 3개, `hard_negative_isbns`는 정확히 3개 작성합니다.

#### `relevant_isbns`
이 질의에 추천 결과로 나와도 적절한 책들입니다.  
평가 지표 계산의 기준이 됩니다.

#### `hard_negative_isbns`
겉보기에는 관련 있어 보이지만 실제로는 부적합한 책입니다.  
일반 오답과 달리 별도로 추적합니다.

```
예: "지쳐있을 때 위로가 되는 에세이" 질의에
    → 에세이 형식이지만 내용이 매우 어둡고 무거운 책
    → 분류(에세이)는 맞지만 분위기가 완전히 반대
    → reason: "level_mismatch" (분위기/톤 불일치)
```

**왜 hard negative를 따로 추적하는가**  
시스템이 어떤 종류의 실수를 하는지 파악하기 위해서입니다.  
`topic_confusion`이 많으면 → 카테고리 필터 개선  
`level_mismatch`가 많으면 → 분위기 태그 활용 개선

---

### `availability_expectation`

**왜 있는가**  
대출 가능 여부 처리 로직이 시나리오에 따라 다르기 때문에, 어떤 출력 구조를 기대하는지 명시합니다.

#### 출력 시나리오 3가지

```
리랭킹 결과 Top5 확정
        ↓
  1등 도서가 대출 가능?
   ┌────┴────┐
  Yes        No
   ↓          ↓
[Scenario A] [Scenario B]    ┌── 사용자가 "지금 당장 대출가능"처럼 명시 요청?
대출가능       대출가능                  [Scenario C]
Top3만       Top3 출력               
출력          +               
              리랭킹 1등 추가 출력
```

| Scenario | mode | 조건 | 출력 |
|----------|------|------|------|
| **A** | `standard` | 리랭킹 1등이 대출 가능 | 대출가능 Top3만 |
| **B** | `standard` | 리랭킹 1등이 대출 불가 | 대출가능 Top3 + 1등 추가 |
| **C** | `strict` | 사용자 query에 "지금 당장" 등 명시 | 대출가능 Top3만 (추가 없음) |

#### 스키마

```json
"availability_expectation": {
  "library": "마포구립서강도서관",
  "mode": "standard",
  "top1_rerank_available": true,
  "expected_output_structure": "available_top3"
}
```

| 필드 | 값 | 의미 |
|------|----|------|
| `library` | 도서관명 | 대출 가능 여부를 체크할 도서관 |
| `mode` | `standard` \| `strict` | standard = 기본 로직 / strict = 사용자가 대출가능 명시 |
| `top1_rerank_available` | `true` \| `false` | 리랭킹 1등 도서의 대출 가능 여부 |
| `expected_output_structure` | `available_top3` \| `available_top3_plus_best` | 최종 출력이 어떤 형태여야 하는가 |

#### 시나리오별 작성 예시

**Scenario A** — 1등이 대출 가능, 대출가능 Top3만 출력
```json
{
  "library": "마포구립서강도서관",
  "mode": "standard",
  "top1_rerank_available": true,
  "expected_output_structure": "available_top3"
}
```

**Scenario B** — 1등이 대출 불가, 대출가능 Top3 + 1등 추가 출력
```json
{
  "library": "마포구립서강도서관",
  "mode": "standard",
  "top1_rerank_available": false,
  "expected_output_structure": "available_top3_plus_best"
}
```

**Scenario C** — 사용자가 "지금 당장 대출가능한" 명시, 추가 출력 없음
```json
{
  "library": "마포구립서강도서관",
  "mode": "strict",
  "top1_rerank_available": false,
  "expected_output_structure": "available_top3"
}
```

#### 평가 지표 매핑

| 지표 | 적용 시나리오 | 의미 |
|------|--------------|------|
| `AvailableTop3Pass` | A, B, C 공통 | 출력 Top3가 모두 대출 가능한가 |
| `BestAppendedPass` | **B 전용** | 리랭킹 1등 도서가 4번째로 추가됐는가 |
| `StrictNoAppendPass` | **C 전용** | strict 모드에서 추가 출력이 없는가 |

> `availability_expectation`이 `null`인 케이스 (availability 관련 없는 일반 질의)에서는  
> 위 세 지표를 계산하지 않습니다.

---

### `explanation_checklist`

> ⚠️ **Generation 미구현으로 현재 평가 보류.**  
> Generation 기능 구현 완료 후 활성화합니다. 그 전까지 `session_eval.jsonl`에 포함하지 않습니다.

**왜 있는가** (구현 후 활성화)  
최종 추천 설명(메시지)의 품질을 체크합니다.  
검색 결과가 좋아도 설명이 엉뚱하면 사용자 경험이 나쁩니다.

```json
{
  "mentions_mood":              true,
  "mentions_topic":             true,
  "mentions_reading_level":     true,
  "uses_onboarding_signal":     false,
  "avoids_disliked_keywords":   true
}
```

| 항목 | 의미 |
|------|------|
| `mentions_mood` | 사용자 기분/상태를 언급했는가 |
| `mentions_topic` | 주제를 언급했는가 |
| `mentions_reading_level` | 난이도/분량을 언급했는가 |
| `uses_onboarding_signal` | 장기 취향을 보조적으로 언급했는가 |
| `avoids_disliked_keywords` | 싫어하는 키워드를 설명에서 피했는가 |

---

## 전체 데이터 흐름 요약

```
  ┌─────────────────────────────┐
  │   session_eval.jsonl        │
  │                             │
  │  conversation_script        │  ← 멀티턴 대화 재현 (정성 평가용)
  │  session_data               │
  │  onboarding_data            │
  │      ↓                      │
  │  expected_data_usage        │  ← DataUsagePass
  │  expected_rag_query         │  ← gold query (evaluate.py 입력)
  │      ↓                      │
  │  retrieval_eval             │  ← Hit@10, Recall@10, MRR@10, NDCG@10
  │  relevance_labels           │  ← 정답지
  │  hard_negative_isbns        │  ← HardNegativeNotTop3
  │      ↓                      │
  │  availability_expectation   │  ← AvailableTop3Pass / BestAppendedPass / StrictNoAppendPass
  └─────────────────────────────┘
              ↓
        evaluate.py
    (run_bm25_search, run_reranker)
              ↓
  results/retrieval_results.jsonl
  results/rerank_results.jsonl
              ↓
  qualitative_scoring.xlsx  ← 정성 채점 (Human + LLM-judge)
              ↓
  results/summary.csv
```
