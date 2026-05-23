# C파트 모듈 설명서

> 작성 기준: 현재 구현 코드 기반  
> 대상 독자: 팀 전체 (A/B/C파트 모두)

---

## 전체 흐름 요약

```
사용자 발화
  → [API] POST /api/chat
  → [chat_service] 컨텍스트 복원 + 온보딩 로드
  → [signal detector] 휴리스틱 신호 감지
  → [filler] LLM Call 1 — 슬롯 추출
  → [filler] LLM Call 2 — 슬롯 충분도 판단
      ├── 충분하지 않음 → [question_generator] 세션 질문 생성 → 응답 반환
      └── 충분함 → [rag_query_builder] LLM Call 3 — RAG 쿼리 생성 → 응답 반환
```

멀티턴: 프론트가 응답의 `context`를 저장했다가 다음 요청에 그대로 포함.  
세션 저장소 없음 — stateless.

---

## 1. API 레이어

### `app/api/routes/chat.py`

| 항목 | 내용 |
|------|------|
| 역할 | HTTP 엔드포인트 정의. 요청 수신 후 chat_service로 위임 |
| 엔드포인트 | `POST /api/chat`, `GET /api/health` |
| 입력 | `ChatRequest` (아래 스키마 참조) |
| 출력 | `SlotChatResponse` (아래 스키마 참조) |
| 타임아웃 | 90초 초과 시 504 반환 |

---

## 2. 스키마

### `app/schemas/chat_schema.py`

**ChatRequest** — 프론트 → 백엔드 요청 바디

| 필드 | 타입 | 설명 |
|------|------|------|
| `query` | str | 사용자 발화 (필수) |
| `history` | list | 이전 대화 목록 `[{role, content}]` |
| `user_profile` | dict\|null | 온보딩 식별자 `{"user_id": "P001-A"}` |
| `context` | dict\|null | 이전 턴 컨텍스트 (첫 턴은 null) |
| `selected_choice` | dict\|null | 버튼 선택 시 선택 내용 |
| `pending_slots` | list\|null | 선택지가 채우려던 슬롯 목록 |
| `confirm_inferred` | bool\|null | 추론 슬롯 확인 여부 (True=맞음, False=수정) |

**SlotChatResponse** — 백엔드 → 프론트 응답 바디

| 필드 | 타입 | 설명 |
|------|------|------|
| `needs_clarification` | bool | 추가 질문 필요 여부 |
| `ready_for_rag` | bool | RAG 쿼리 생성 완료 여부 |
| `message` | str | 사용자에게 보여줄 텍스트 |
| `is_confirmation` | bool | 추론 슬롯 확인 카드 여부 |
| `inferred_summary` | list\|null | 확인 카드 내용 (슬롯명/값/레이블) |
| `clarification_choices` | list\|null | 선택지 버튼 목록 |
| `pending_slots` | list\|null | 이번에 질문한 슬롯 목록 |
| `rag_query` | dict\|null | RAG 검색 쿼리 (ready_for_rag=True일 때) |
| `context` | dict\|null | 다음 턴에 포함할 컨텍스트 |
| `search_results` | list\|null | BM25 검색 결과 (A파트 연동 시) |
| `availability_index` | dict\|null | 대출 가능 여부 (정보나루 API 연동 시) |
| `filled_slots` | list | 현재 채워진 슬롯 이름 목록 (디버깅용) |

---

### `app/modules/slot/schema.py`

세션 전체를 관통하는 데이터 모델 정의.

**SessionContext** — 세션 상태 전체

| 필드 | 타입 | 설명 |
|------|------|------|
| `original_query` | str | 첫 턴 원본 발화 |
| `anchors` | list[Anchor] | 고유명사 참조점 목록 (책 제목/작가명 등) |
| `slots` | SlotState | 슬롯 전체 상태 |
| `turn_count` | int | 현재 턴 수 |
| `asked_slots` | list[str] | 이미 질문한 슬롯 목록 |
| `slot_importance` | dict | 슬롯별 importance (signal 모듈 계산) |
| `slot_uncertainty` | dict | 슬롯별 uncertainty (signal 모듈 계산) |
| `onboarding` | dict\|null | 사용자 온보딩 데이터 (user_metadata.json) |
| `rag_ready_from_llm` | bool | LLM 충분도 판단 결과 |
| `llm_slots_to_ask` | list[str] | LLM이 다음에 물어야 한다고 판단한 슬롯 |
| `slot_revision_hints` | dict | LLM이 수정 필요하다고 판단한 슬롯 힌트 |
| `llm_reasoning` | str\|null | LLM 충분도 판단 근거 (디버깅용) |

**SlotState** — 슬롯 전체

| 슬롯 | 유형 | 활성화 조건 |
|------|------|------------|
| `topic` | 핵심 | 항상 활성 |
| `purpose` | 핵심 | 항상 활성 |
| `reading_level` | 핵심 | 항상 활성 (LLM 판단 시에만 질문) |
| `mood` | 조건부 | 정서/상태 신호(CAT1) 감지 시 |
| `comparison_basis` | 조건부 | anchor + 유사도 표현 동시 감지 시 |
| `location` | 조건부 | 대출 가능(CAT6) 또는 지역(CAT7) 감지 시 |
| `avoid_mood` | 조건부 | 회피 신호(CAT9) 감지 시 |
| `length` | 예외 | 체감 분량 단서 직접 언급 시 |
| `constraints` | 제약 | page_range / pub_year / author / nonauthor 등 |
| `availability_required` | 플래그 | 대출 가능 요구 시 True |

**SlotSource** — 슬롯 값의 신뢰도 등급

| 값 | 의미 |
|----|------|
| `direct` | 발화에 직접 명시 → 잠금 (덮어쓰기 불가) |
| `inferred` | 문맥 추론 → 확인 턴 필요 |
| `ambiguous` | 해석 여러 개 가능 → 세션 질문 |
| `null` | 언급 없음 |

**LengthLevel** — 분량 슬롯 값 (절대 기준 아님, 상대적 소프트 신호)

| 값 | 해당 표현 |
|----|----------|
| `short` | "짧은", "가볍게", "금방 읽히는" |
| `medium` | "적당한", "보통 분량" |
| `long` | "두꺼운", "묵직한", "장편" |

---

## 3. 서비스 레이어

### `app/services/chat_service.py`

| 항목 | 내용 |
|------|------|
| 역할 | 매 턴의 파이프라인 오케스트레이션 |
| 입력 | `ChatRequest` |
| 출력 | `SlotChatResponse` |

**처리 순서 (매 턴)**

1. 컨텍스트 복원 (`_restore_or_create_context`) — `user_metadata.json`에서 온보딩 로드
2. 선택지 응답이면 `apply_choice()` 처리
3. 자유 발화면 `extract_slots()` 호출 (LLM Call 1+2)
4. inferred 슬롯 분류 — HIGH uncertainty → 리셋 후 세션 질문, LOW → 확인 카드
5. `get_slots_to_ask()` → 슬롯이 남으면 `generate_question()` → 질문 응답 반환
6. 슬롯이 없으면 `run_rag_query()` → RAG 응답 반환

**온보딩 로드 (`_load_onboarding`)**

- `user_profile.user_id`로 `user_metadata.json` 조회
- `context.onboarding`에 저장
- `rag_query_builder`의 `_build_onboarding_signals()`에서 참조

---

### `app/services/pipeline.py`

| 항목 | 내용 |
|------|------|
| 역할 | RAG 이후 단계 (BM25 → Reranker → 대출 조회) 순서 실행 |
| 입력 | `SessionContext` |
| 출력 | `(PipelineResult, PipelineLog)` |

**단계별 함수**

| 함수 | 역할 | 연동 모듈 |
|------|------|----------|
| `run_rag_query()` | RAG 쿼리 생성 | `rag_query_builder.py` |
| `run_bm25_search()` | BM25 키워드 검색 | A파트 `BM25.py` |
| `run_reranker()` | CLOVA Reranker 재정렬 | B파트 `clova_reranker.py` |
| `run_availability()` | 정보나루 API 대출 가능 여부 조회 | `loan_availability.py` |

각 단계는 실패해도 graceful skip (빈 리스트 반환) — 파이프라인 전체가 멈추지 않음.

---

## 4. Signal 모듈

### `app/modules/signal/detector.py`

| 항목 | 내용 |
|------|------|
| 역할 | LLM 호출 전 휴리스틱으로 쿼리 특성을 미리 파악 |
| 입력 | 쿼리 문자열 |
| 출력 | `SignalResult` |
| 형태소 분석 | Kiwi (모듈 로드 시 1회 초기화, 이후 재사용) |

**SignalResult 구조**

```python
SignalResult(
    needs_llm_fallback = False,   # True면 신호 미감지 → LLM에 전적으로 위임
    scores = SlotScores(          # 슬롯별 importance + uncertainty
        topic     = SlotScore(importance=HIGH, uncertainty=LOW),
        purpose   = SlotScore(importance=MEDIUM, uncertainty=HIGH),
        ...
    ),
    categories = DetectedCategories(  # 카테고리별 감지 여부
        cat1_negative=True, cat2_learn=False, cat5_leisure=True, ...
    )
)
```

**카테고리 정의**

| 카테고리 | 감지 대상 | 영향 |
|----------|----------|------|
| CAT1 | 정서/감정 상태 ("지쳐서", "불안해서") | mood 슬롯 활성화 |
| CAT2 | 독서 목적 ("공부", "위로", "재미") | purpose uncertainty 낮춤 |
| CAT3 | 분량 단서 ("짧은", "두꺼운") | length 슬롯 활성화 |
| CAT4 | 난이도 단서 ("쉬운", "깊이 있는") | reading_level uncertainty 낮춤 |
| CAT5 | 장르/포맷/레저 ("소설", "에세이") | topic uncertainty 낮춤 / purpose uncertainty 낮춤 |
| CAT6 | 대출 가능 요구 ("빌릴 수 있는") | availability_required 활성화 |
| CAT7 | 지역/도서관 언급 | location 슬롯 활성화 |
| CAT8 | 레퍼런스 신호 ("같은", "비슷한") | comparison_basis 활성화 |
| CAT9 | 회피/부정 ("싫어", "제외") | avoid_mood 슬롯 활성화 |

**교차 규칙 예시**
- CAT5_LEISURE 감지 → purpose.uncertainty = LOW (소설/에세이면 목적 안 물어봐도 됨)
- CAT1 + CAT3 동시 감지 → length.uncertainty는 HIGH 유지 (정서형이라고 짧은 책을 원한다고 단정 불가)

---

## 5. Slot 모듈

### `app/modules/slot/filler.py`

| 항목 | 내용 |
|------|------|
| 역할 | LLM으로 슬롯 추출 + 충분도 판단 |
| 입력 | `query: str`, `context: SessionContext`, `history: list` |
| 출력 | 업데이트된 `SessionContext` |

**내부 LLM 호출 2회**

| 호출 | 프롬프트 | 역할 | 출력 |
|------|----------|------|------|
| Call 1 | `SLOT_EXTRACTION_SYSTEM_PROMPT` | 슬롯 값 추출 | `{topic, purpose, mood, length, ...}` |
| Call 2 | `SUFFICIENCY_JUDGMENT_PROMPT` | 슬롯 충분도 판단 | `{rag_ready, slots_to_ask, slot_revisions, reasoning}` |

**RAG 진행 여부 판단**

`is_ready_for_rag()`는 LLM holistic judgment 결과(`rag_ready_from_llm`)만 사용.  
topic/purpose 등 핵심 슬롯이 비어있어도 LLM이 `rag_ready=True`로 판단하면 RAG로 넘어감.  
LLM 판단 실패 시에만 rule-based fallback(`_get_slots_to_ask_fallback`)이 동작하며, 이때는 topic/purpose를 항상 필수로 처리.

**슬롯 잠금 정책**
- `source=direct`인 슬롯은 덮어쓰지 않음
- `is_refinement=True` + 새 값도 `direct`이면 예외적으로 덮어씀
- `mood`는 한 번 채워지면 같은 세션에서 업데이트 안 함

**주요 함수**

| 함수 | 입력 | 출력 | 설명 |
|------|------|------|------|
| `extract_slots()` | query, context, history | SessionContext | LLM Call 1+2 실행 |
| `is_ready_for_rag()` | context | bool | `context.rag_ready_from_llm` 그대로 반환 |
| `get_slots_to_ask()` | context | list[str] | LLM 판단 우선, 실패 시 rule-based fallback |

---

### `app/modules/slot/question_generator.py`

| 항목 | 내용 |
|------|------|
| 역할 | 비어있는 슬롯에 대한 세션 질문 생성 |
| 입력 | `slots_to_ask: list[str]`, `context: SessionContext` |
| 출력 | `SessionQuestion(question: str, choices: list[dict])` |

**질문 유형**

| 슬롯 | 질문 방식 | 선택지 |
|------|----------|--------|
| `topic` | LLM 생성 (맥락 반영) | 없음 (자유 발화) |
| `purpose` | 고정 선택지 | 학습 / 교양 / 재미 / 실용 |
| `reading_level` | mood 감지 여부에 따라 문구 조정 | 가볍게 / 적당히 / 깊이 있게 |
| `comparison_basis` | 고정 선택지 | 분위기 / 주제 / 문체 / 난이도 / 깊이 / 직접 입력 |
| `location` | 온보딩 도서관 목록 포함 | 자주 가는 도서관 1~2 + 직접 입력 |

---

### `app/modules/slot/rag_query_builder.py`

| 항목 | 내용 |
|------|------|
| 역할 | SlotState → RAG 쿼리 dict 변환 |
| 입력 | `context: SessionContext` |
| 출력 | RAG 쿼리 dict (아래 구조 참조) |

**RAG 쿼리 구조**

```json
{
  "keyword_query"        : ["키워드1", "키워드2"],
  "semantic_query"       : "자연어 검색 쿼리 문장",
  "filters": {
    "cate_depth1"         : ["소설", "인문"],
    "target_reader"       : ["초등학생"],
    "custom_constraints"  : ["번역서 제외"]
  },
  "constraints": {
    "page_range"  : [{"operator": "lte", "value": 300}],
    "pub_year"    : [{"operator": "gte", "value": 2015}],
    "author"      : ["한강"],
    "author_non"  : ["무라카미 하루키"]
  },
  "score_boost": {
    "cate_depth2" : ["한국소설", "심리학"],
    "subject"     : ["번아웃", "자존감"]
  },
  "availability_required": false,
  "anchors": [
    {"value": "불편한 편의점", "type": "book_title"}
  ],
  "session_signals": {
    "purpose"         : "재미",
    "reading_level"   : "easy",
    "mood"            : ["negative_exhausted"],
    "avoid_mood"      : ["너무 무거운"],
    "length"          : "short",
    "location"        : {"region": "서울 마포구", "library": null},
    "comparison_basis": {"dimensions": ["mood"], "raw": "따뜻한"}
  },
  "onboarding_signals": {
    "topic"             : ["소설", "인문"],
    "page_range_soft"   : {"operator": "lte", "value": 300},
    "disliked_keywords" : ["dark", "tense"],
    "frequent_libraries": ["마포구립서강도서관"]
  }
}
```

**필드 역할 요약**

| 필드 | 역할 | 소비자 |
|------|------|--------|
| `keyword_query` | BM25 키워드 검색 입력 | A파트 BM25 |
| `semantic_query` | Dense 검색 / Reranker query | B파트 Reranker |
| `filters.cate_depth1` | 대분류 하드 필터 | A파트 BM25, B파트 Reranker |
| `filters.target_reader` | 독자 대상 필터 | A파트 (미구현) |
| `filters.custom_constraints` | 자연어 제약 (후처리용) | A파트 (미구현) |
| `constraints.page_range` | 페이지 수 범위 필터 | A파트 BM25 |
| `constraints.pub_year` | 출판연도 필터 | A파트 BM25 |
| `constraints.author` | 포함 작가 하드 필터 | A파트 BM25 |
| `constraints.author_non` | 제외 작가 필터 | A파트 BM25 |
| `score_boost.cate_depth2` | 중분류 점수 가중 | A파트 BM25 |
| `score_boost.subject` | 소분류 임베딩 유사도 부스트 | A파트 BM25 |
| `availability_required` | 대출 가능 도서 조회 트리거 | 정보나루 API |
| `anchors` | 참조 고유명사 (책/작가) 목록 | A/B파트 (구현 시 참조) |
| `session_signals` | 세션에서 직접 추출한 슬롯 값 (높은 가중치) | B파트 Reranker |
| `onboarding_signals` | 온보딩 기반 약한 보조 신호 (낮은 가중치) | B파트 Reranker |

**session_signals vs onboarding_signals 차이**

| | session_signals | onboarding_signals |
|--|--|--|
| 출처 | 현재 세션 발화 | 회원가입 온보딩 데이터 |
| 가중치 | 높음 | 낮음 |
| 사용 조건 | 슬롯이 채워진 경우 | 세션에 없고 uncertainty HIGH인 경우 |
| 목적 | 강한 신호 전달 | 방향 보정 |

**onboarding_signals 생성 조건**

| 필드 | 조건 |
|------|------|
| `topic` | topic 슬롯 미채움 + uncertainty HIGH |
| `page_range_soft` | 세션에 page_range constraint 없을 때 preferred_length 숫자로 전달 |
| `disliked_keywords` | 세션 topic/purpose와 충돌 없을 때 |
| `frequent_libraries` | `availability_required=True`일 때만 |

---

## 6. LLM 모듈

### `app/modules/llm/clova_client.py`

| 항목 | 내용 |
|------|------|
| 역할 | CLOVA Studio LLM API 호출 래퍼 |
| 사용 SDK | OpenAI Python SDK (base_url만 CLOVA로 변경) |

| 함수 | 입력 | 출력 | 설명 |
|------|------|------|------|
| `chat_complete()` | system_prompt, messages | str | 텍스트 응답 |
| `chat_complete_json()` | system_prompt, messages | dict | JSON 파싱 응답 (코드블록 자동 제거) |

공통 파라미터: `temperature` (낮을수록 일관성), `max_tokens`

에러 처리:
- `AuthenticationError` → `LLMCallError` (API 키 오류)
- `APITimeoutError` → `LLMCallError` (45초 초과)
- `JSONDecodeError` → `IntentParseError` (파싱 실패)

---

### `app/modules/llm/category_mapper.py`

| 항목 | 내용 |
|------|------|
| 역할 | LLM이 추출한 중분류를 카테고리 트리 기준값으로 정규화 |
| 입력 | 중분류 문자열 (예: "SF소설", "SF") |
| 출력 | 정규화된 중분류 + 역방향 대분류 |

| 함수 | 설명 |
|------|------|
| `get_canonical_fine(text)` | 중분류 정규화 (매칭 실패 시 원본 반환) |
| `get_coarse_category(fine)` | 중분류 → 대분류 역방향 매핑 |

---

## 7. 프롬프트

### `app/prompts/extraction.py`

- **역할**: LLM Call 1 (슬롯 추출) 시스템 프롬프트
- **출력 JSON 형식**:

```json
{
  "topic"           : {"fine": [...], "subject": [...], "source": "direct|inferred|null"},
  "purpose"         : {"value": "학습|교양|재미|실용|null", "source": "..."},
  "reading_level"   : {"value": "easy|medium|hard|null", "source": "..."},
  "mood"            : {"categories": ["negative_exhausted", ...], "raw": "...", "source": "..."},
  "comparison_basis": {"dimensions": ["mood|topic|style|difficulty|depth|custom"], "raw": "...", "source": "..."},
  "avoid_mood"      : {"keywords": [...], "source": "..."},
  "length"          : {"level": "short|medium|long|null", "source": "..."},
  "location"        : {"region": "...", "library": "...", "source": "..."},
  "anchor"          : {"value": "...", "type": "book_title|author|series|library|null"},
  "constraints"     : [{"type": "...", "value": "...", "operator": "...", "raw": "..."}],
  "is_refinement"   : false
}
```

### `app/prompts/clarification.py`

- **역할**: LLM Call 2 (슬롯 충분도 판단) 시스템 프롬프트
- **출력 JSON 형식**:

```json
{
  "reasoning"     : "판단 근거 설명",
  "rag_ready"     : true,
  "slots_to_ask"  : ["topic_subject", "purpose_detail"],
  "slot_revisions": {"topic": {"action": "narrow", "hint": "장르가 너무 넓음"}}
}
```

### `app/prompts/rag.py` / `question_generation.py`

- **역할**: LLM Call 3 (RAG 쿼리 생성), 세션 질문 텍스트 생성 프롬프트

---

## 8. 핵심 모듈

### `app/core/session_logger.py`

| 항목 | 내용 |
|------|------|
| 역할 | 세션 단위 로그를 `logs/` 디렉토리에 JSONL 파일로 저장 |
| 입력 | session_id, user_id, 슬롯 상태, RAG 쿼리, 파이프라인 결과 |
| 출력 | `logs/{session_id}.jsonl` |

---

## 9. 외부 연동 모델

### `app/models/clova_reranker.py`

| 항목 | 내용 |
|------|------|
| 역할 | BM25 후보 도서를 CLOVA Reranker로 재정렬 |
| 입력 | `rag_query` (dict), `bm25_results` (list[{rank, isbn, score}]) |
| 출력 | `[{isbn, title, author, final_rank, final_score, ...}]` |

**처리 순서**

1. ISBN으로 PostgreSQL에서 도서 메타데이터 조회
2. `build_clova_query()` — rag_query → Reranker query 문자열 변환
   - `semantic_query`, `keyword_query`, `filters.cate_depth1`, `score_boost` 사용
3. CLOVA Reranker API 호출
4. `clova_relevance_score` + `retrieval_score` 결합해 최종 정렬

### `app/models/loan_availability.py`

| 항목 | 내용 |
|------|------|
| 역할 | 정보나루 API로 도서관 대출 가능 여부 조회 |
| 입력 | ISBN 목록, 도서관 코드, API 키 |
| 출력 | `{"isbn": {"has_book": "Y", "loan_available": "Y"}, ...}` |
| 트리거 조건 | `availability_required=True`일 때만 실행 |

---

## 10. 환경 변수 (`.env`)

| 변수 | 설명 |
|------|------|
| `CLOVA_API_KEY` | CLOVA Studio API 키 (필수) |
| `CLOVA_BASE_URL` | CLOVA Studio 엔드포인트 URL |
| `CLOVA_MODEL` | 사용할 모델 ID |
| `POSTGRES_DB` | PostgreSQL 데이터베이스명 |
| `POSTGRES_HOST` | PostgreSQL 호스트 |
| `POSTGRES_PORT` | PostgreSQL 포트 |
| `POSTGRES_USER` | PostgreSQL 사용자 |
| `POSTGRES_PASSWORD` | PostgreSQL 비밀번호 |
| `NARU_API_KEY` | 정보나루 API 키 |
| `NARU_LIB_CODE` | 기준 도서관 코드 |

---

## 서버 실행

```bash
# backend/ 디렉토리에서
uvicorn app.main:app --reload --port 8000
```

- Swagger UI: `http://localhost:8000/docs`
- Health check: `http://localhost:8000/api/health`
