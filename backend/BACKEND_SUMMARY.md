# Book돋아조 백엔드 C파트 — 최종 정리

## 개요

사용자의 자유 질의를 받아 slot을 채우고, RAG 검색 쿼리를 생성해서 넘겨주는 파이프라인입니다.

```
사용자 질의
  → slot 추출 (LLM)
  → 부족한 slot → session question 생성
  → 사용자 답변 → slot 업데이트 (멀티턴)
  → slot 충분히 채워짐 → RAG 쿼리 생성 → 반환
```

---

## 전체 파일 구조

```
backend/
├── .env.example                          ← API 키 등 환경변수 설정 예시
├── requirements.txt                      ← pip 설치용 의존성
├── pyproject.toml                        ← Poetry 설치용 의존성
│
├── app/
│   ├── main.py                           ← FastAPI 앱 진입점, CORS 설정
│   │
│   ├── core/
│   │   ├── config.py                     ← 환경변수 로드 (CLOVA_API_KEY 등)
│   │   └── exceptions.py                 ← 커스텀 예외 (LLMCallError 등)
│   │
│   ├── schemas/
│   │   └── chat_schema.py                ← API 입출력 타입 정의 (DTO)
│   │                                        ChatRequest, SlotChatResponse
│   │
│   ├── api/
│   │   └── routes/
│   │       └── chat.py                   ← HTTP 엔드포인트
│   │                                        POST /api/chat
│   │                                        GET  /api/health
│   │
│   ├── services/
│   │   └── chat_service.py               ← 파이프라인 오케스트레이션
│   │                                        slot filling → question or RAG 분기
│   │
│   └── modules/
│       ├── llm/
│       │   ├── clova_client.py           ← CLOVA Studio API 호출 래퍼
│       │   ├── category_mapper.py        ← 중분류 → 대분류 자동 매핑
│       │   ├── category_tree.json        ← 카테고리 트리 데이터
│       │   ├── intent_extractor.py       ← (구버전, 현재 미사용)
│       │   └── prompts.py                ← (구버전, 현재 미사용)
│       │
│       └── slot/
│           ├── schema.py                 ← slot 스키마 및 SessionContext 정의
│           ├── filler.py                 ← slot 추출 + 우선순위 결정
│           ├── question_generator.py     ← session question 생성
│           ├── rag_query_builder.py      ← RAG 쿼리 생성
│           └── prompts.py               ← slot 추출 / 질문 생성 프롬프트
│
└── tests/
    └── test_intent_extractor.py          ← (구버전 테스트, 참고용)
```

---

## 핵심 개념

### Slot

추천을 만들기 위해 시스템이 채워야 하는 정보 칸입니다.

| 종류 | Slot | 설명 |
|------|------|------|
| 핵심 | topic | 주제 (대분류/중분류/세부주제) |
| 핵심 | purpose | 목적 (학습/교양/재미/실용) |
| 핵심 | reading_level | 읽기 부담 (easy/medium/hard) |
| 조건부 | mood | 감정/상태 |
| 제약 | constraints | 페이지 수, 출판연도, availability 등 |

### Anchor

질의에서 감지되는 고유명사입니다. slot이 아니므로 비어있어도 질문하지 않습니다.

```
book_title : "불편한 편의점"
author     : "한강"
series     : "해리포터"
library    : "마포중앙도서관"
```

### Source 등급

slot 값의 신뢰도를 나타냅니다.

```
direct    → 질의에 직접 명시됨 → 채워진 것으로 판단
inferred  → 문맥으로 추론 가능 → 중요도에 따라 조건부 판단
ambiguous → 해석이 여러 개 가능 → 질문 생성
null      → 언급 없음 → 필수 slot이면 질문 생성
```

### SessionContext

세션 전체를 관통하는 컨텍스트 객체입니다. 매 턴마다 프론트엔드에서 보관했다가 다음 요청에 포함합니다.

```python
{
  "original_query": "SF 소설 추천해줘",
  "anchor": null,
  "slots": {
    "topic": {"coarse": "과학/기술", "fine": "SF", "source": "direct"},
    "purpose": {"value": null, "source": "null"},
    "reading_level": {"value": null, "source": "null"},
    "mood": {"value": null, "source": "null"},
    "constraints": [],
    "availability_required": false
  },
  "turn_count": 1,
  "asked_slots": []
}
```

---

## 파이프라인 상세

### 1. Slot 추출 (filler.py)

LLM이 질의를 분석해서 명시적으로 드러난 slot만 채웁니다.

```
"요즘 지쳐있어서 SF 소설 가볍게 읽고 싶어"
  → topic.fine    = "SF"           (direct)
  → mood          = "지침"          (direct)
  → reading_level = "easy"         (inferred - "가볍게"에서)
  → purpose       = null           (언급 없음)
```

### 2. 우선순위 결정 (filler.py - priority_conditions)

채워진 slot 패턴으로 다음에 질문할 slot을 결정합니다.

```
topic=filled, purpose=empty → purpose 1순위 질문
mood=filled, topic=empty    → reading_level 1순위 질문
topic=filled, purpose=filled → reading_level 1순위 질문
```

### 3. Session Question 생성 (question_generator.py)

```
단일 slot 질문:
  선택지 → 사전 정의 값 사용
  질문 텍스트 → LLM이 맥락 반영해서 동적 생성

복수 slot 동시 질문:
  질문 텍스트 + 선택지 → LLM이 통째로 생성
  각 선택지가 어떤 slot을 채우는지 매핑 정보 포함
```

### 4. RAG 쿼리 생성 (rag_query_builder.py)

```python
{
  "keyword_query": ["SF", "소설", "재미", "가벼운"],   # BM25용
  "semantic_query": "가볍고 재미있게 읽을 수 있는 SF 소설",  # Dense용
  "filters": {
    "coarse_category": "과학/기술"    # 대분류 메타데이터 필터
  },
  "score_boost": {
    "fine_category": "SF"             # 중분류 Reranking 스코어
  },
  "availability_required": false,
  "anchor": null
}
```

---

## 멀티턴 흐름

```
1턴: "SF 소설 추천해줘"
  → context=null 로 요청
  → topic 채워짐, purpose 비어있음
  → 응답: needs_clarification=true, question="목적이 어떻게 되세요?"
  → context 반환 (프론트에서 보관)

2턴: 사용자가 "재미있게" 버튼 선택
  → selected_choice={"label":"재미있게", "slots":{"purpose":"재미"}}
  → pending_slots=["purpose"]
  → context=이전 턴 context
  → purpose 채워짐, reading_level 비어있음
  → 응답: needs_clarification=true, question="어떤 느낌이 좋으세요?"

3턴: "가볍게" 선택
  → reading_level="easy" 채워짐
  → is_ready_for_rag() = True
  → 응답: ready_for_rag=true, rag_query={...}
```

---

## API 사용법

### 서버 실행

```bash
# Anaconda Prompt에서
conda activate book
cd backend
pip install -r requirements.txt

# .env 파일 생성
copy .env.example .env
# .env 열어서 CLOVA_API_KEY 입력

# 서버 실행
uvicorn app.main:app --reload --port 8000
```

### 엔드포인트

```
POST http://localhost:8000/api/chat
GET  http://localhost:8000/api/health
GET  http://localhost:8000/docs         ← Swagger UI
```

### 요청 예시 (첫 턴)

```json
{
  "query": "요즘 지쳐있어서 SF 소설 가볍게 읽고 싶어",
  "history": [],
  "context": null
}
```

### 응답 예시 (추가 질문)

```json
{
  "needs_clarification": true,
  "ready_for_rag": false,
  "message": "어떤 목적으로 읽으실 건가요?",
  "clarification_question": "어떤 목적으로 읽으실 건가요?",
  "clarification_choices": [
    {"label": "재미있게 읽고 싶어요", "slots": {"purpose": "재미"}},
    {"label": "공부·입문용으로",      "slots": {"purpose": "학습"}},
    {"label": "잘 모르겠어요",        "slots": {}}
  ],
  "pending_slots": ["purpose"],
  "context": {...},
  "filled_slots": ["topic", "reading_level"]
}
```

### 응답 예시 (RAG 준비 완료)

```json
{
  "needs_clarification": false,
  "ready_for_rag": true,
  "message": "좋아요! SF · 재미 · 가볍고 쉽게 읽히는 관련 도서를 찾아볼게요 📚",
  "rag_query": {
    "keyword_query": ["SF", "소설", "재미", "가벼운"],
    "semantic_query": "가볍고 재미있게 읽을 수 있는 SF 소설",
    "filters": {"coarse_category": "과학/기술"},
    "score_boost": {"fine_category": "SF"},
    "availability_required": false,
    "anchor": null
  },
  "context": {...},
  "filled_slots": ["topic", "purpose", "reading_level"]
}
```

---

## 카테고리 매핑

`category_tree.json` 기준으로 중분류 → 대분류 자동 매핑합니다.

```
"한국소설"   → "소설"
"심리학"     → "인문"
"물리학"     → "과학"
"SF"         → None (매핑 없음 → LLM 판단 또는 null)
```

매핑 없는 경우 LLM이 대분류 목록을 보고 판단하고,
그래도 모호하면 `coarse=null` (전체 범위 검색) 로 처리합니다.

---

## 수정/확장 포인트

| 목적 | 수정 파일 |
|------|-----------|
| slot 추가 | slot/schema.py + slot/filler.py + slot/prompts.py |
| 질문 선택지 변경 | slot/question_generator.py (_PREDEFINED_CHOICES) |
| LLM 프롬프트 튜닝 | slot/prompts.py |
| source_rules 키워드 추가 | slot/prompts.py (SLOT_EXTRACTION_SYSTEM_PROMPT) |
| 카테고리 변경 | modules/llm/category_tree.json |
| 모델 변경 | core/config.py (CLOVA_MODEL) |
| RAG 쿼리 구조 변경 | slot/rag_query_builder.py |
