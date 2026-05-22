# librAIan 백엔드 아키텍처 문서

> **대상 독자**: 처음 이 프로젝트를 보는 개발자  
> **목적**: 백엔드 전체 구조, 각 모듈의 역할·입출력·설계 고려사항을 한 곳에서 이해할 수 있도록 정리

---

## 목차

1. [프로젝트 개요](#1-프로젝트-개요)
2. [전체 아키텍처 흐름](#2-전체-아키텍처-흐름)
3. [핵심 데이터 구조 (스키마)](#3-핵심-데이터-구조-스키마)
4. [슬롯 설계 상세](#4-슬롯-설계-상세)
   - 4-1. [슬롯 설계 철학](#4-1-슬롯-설계-철학)
   - 4-2. [슬롯 분류 체계](#4-2-슬롯-분류-체계)
   - 4-3. [Source 등급 시스템](#4-3-source-등급-시스템)
   - 4-4. [Anchor — 슬롯과 다른 개념](#4-4-anchor--슬롯과-다른-개념)
   - 4-5. [각 슬롯 상세 설계](#4-5-각-슬롯-상세-설계)
   - 4-6. [슬롯 간 상호작용 규칙](#4-6-슬롯-간-상호작용-규칙)
   - 4-7. [슬롯 → RAG 연결 구조](#4-7-슬롯--rag-연결-구조)
5. [모듈별 상세 설명](#5-모듈별-상세-설명)
   - 5-1. [진입점 & API 레이어](#5-1-진입점--api-레이어)
   - 5-2. [ChatService — 파이프라인 오케스트레이터](#5-2-chatservice--파이프라인-오케스트레이터)
   - 5-3. [Signal Detector — 쿼리 특성 사전 감지](#5-3-signal-detector--쿼리-특성-사전-감지)
   - 5-4. [Anchor Extractor — 비교 앵커 정규식 사전 추출](#5-4-anchor-extractor--비교-앵커-정규식-사전-추출)
   - 5-5. [Slot Filler — LLM 슬롯 추출 & 충분도 판단](#5-5-slot-filler--llm-슬롯-추출--충분도-판단)
   - 5-6. [Question Generator — 세션 질문 생성](#5-6-question-generator--세션-질문-생성)
   - 5-7. [RAG Query Builder — RAG 쿼리 생성](#5-7-rag-query-builder--rag-쿼리-생성)
   - 5-8. [Pipeline — 검색 파이프라인 실행](#5-8-pipeline--검색-파이프라인-실행)
   - 5-9. [Category Mapper — 카테고리 정규화](#5-9-category-mapper--카테고리-정규화)
   - 5-10. [CLOVA LLM Client — LLM API 래퍼](#5-10-clova-llm-client--llm-api-래퍼)
   - 5-11. [Prompts — LLM 프롬프트 모음](#5-11-prompts--llm-프롬프트-모음)
6. [LLM 모델 사용 전략](#6-llm-모델-사용-전략)
7. [슬롯 채움 정책 및 우선순위 결정](#7-슬롯-채움-정책-및-우선순위-결정)
8. [멀티턴 대화 흐름](#8-멀티턴-대화-흐름)
9. [온보딩 데이터 연동](#9-온보딩-데이터-연동)
10. [설계 시 주요 고려사항 및 Trade-off](#10-설계-시-주요-고려사항-및-trade-off)
11. [환경 변수 & 실행 방법](#11-환경-변수--실행-방법)

---

## 1. 프로젝트 개요

librAIan은 **도서관 AI 큐레이션 서비스**다.  
사용자가 자연어로 책을 요청하면 다음 과정을 거쳐 맞춤 도서를 추천한다.

```
사용자 발화
  → 슬롯(정보 칸) 추출  → 부족하면 세션 질문 반복
  → 슬롯 충분  → RAG 쿼리 생성 → BM25 검색 → Reranker → 대출 가능 여부 필터 → 최종 추천
```

**핵심 특징**

| 특징 | 설명 |
|------|------|
| Stateless 멀티턴 | 컨텍스트를 서버가 저장하지 않고 프론트에서 매 요청마다 전달 |
| 슬롯 기반 대화 | 정해진 정보 칸(슬롯)을 채우면서 추천 조건을 좁혀가는 구조 |
| 코드 + LLM 혼합 | 쿼리 특성 감지·앵커 추출은 코드(정규식·형태소), 슬롯 값 추출은 LLM |
| HCX-DASH-002 + HCX-007 이중 모델 | 슬롯 추출은 DASH-002(저지연), 충분도 판단·질문 생성은 HCX-007(고성능) |

---

## 2. 전체 아키텍처 흐름

```
프론트엔드 (Next.js)
    │
    │  POST /api/chat  (ChatRequest)
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  API Layer  (app/api/routes/chat.py)                           │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│  ChatService  (app/services/chat_service.py)                   │
│                                                                 │
│  ┌──────────────┐    ┌──────────────┐    ┌───────────────────┐ │
│  │ 선택지 응답? │    │  자유 발화?  │    │  inferred 확인?   │ │
│  │apply_choice()│    │ extract_slots│    │ promote/reset     │ │
│  └──────┬───────┘    └──────┬───────┘    └─────────┬─────────┘ │
│         └────────────────────┴──────────────────────┘           │
│                              │                                   │
│                    get_slots_to_ask()                           │
│                         │         │                              │
│                    슬롯 부족     슬롯 충분                       │
│                    generate_question()  ←→  build_rag_response() │
└─────────────────────────────────────────────────────────────────┘
                         │
         (슬롯 충분 시 RAG 파이프라인 실행)
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│  Pipeline  (app/services/pipeline.py)                          │
│                                                                 │
│  [2] RAG 쿼리 생성  (rag_query_builder.py + LLM)              │
│  [2-1] Anchor 기반 쿼리 재작성  (anchor_book_pipeline.py)     │
│  [3] BM25 검색  (modules/RAG/retriever.py)                     │
│  [4] CLOVA Reranker  (modules/reranker/)                       │
│  [5] 대출 가능 여부  (services/loan_availability.py)           │
└─────────────────────────────────────────────────────────────────┘
                         │
                         ▼
                 SlotChatResponse → 프론트엔드
```

### extract_slots() 내부 흐름

```
사용자 발화
    │
    ├─ [1] Signal Detector  (signal/detector.py)
    │       Kiwi 형태소 분석 → 카테고리 1~9 감지 → importance/uncertainty 계산
    │
    ├─ [1-1] Anchor Extractor  (slot/anchor_extractor.py)
    │         정규식으로 비교 패턴(처럼/같은 등) 감지 → anchor 후보 추출
    │
    ├─ [2] Slot Extraction LLM  (HCX-DASH-002, temp=0.0)
    │       Signal 힌트 + Anchor 힌트를 포함한 프롬프트로 슬롯 값 추출
    │       → topic, purpose, reading_level, mood, anchor, constraints 등
    │
    └─ [3] Sufficiency Judgment LLM  (HCX-007, temp=0.1)
             슬롯 상태 전체를 보고 RAG 진행 가능 여부 + 다음 질문할 슬롯 판단
             → rag_ready, confidence, slots_to_ask, question, choices
```

---

## 3. 핵심 데이터 구조 (스키마)

> **파일**: `app/modules/slot/schema.py`

### 3-1. SlotSource — 슬롯 값의 신뢰도 등급

```python
class SlotSource(str, Enum):
    direct    = "direct"    # 사용자가 명시적으로 언급 → 신뢰
    inferred  = "inferred"  # 맥락에서 추론 → 중요도에 따라 확인 턴 발생 가능
    ambiguous = "ambiguous" # 해석이 여러 개 → 세션 질문 필요
    null      = "null"      # 언급 없음 → 필수 슬롯이면 세션 질문
```

### 3-2. SlotState — 전체 슬롯 상태

| 슬롯 | 유형 | 설명 |
|------|------|------|
| `topic` | 핵심 슬롯 | 대분류(coarse) + 중분류(fine) + 세부주제(subject). 항상 필요. |
| `purpose` | 준핵심 슬롯 | 학습 / 교양 / 재미 / 실용. 목적이 자명한 카테고리(소설·요리 등)는 생략. |
| `reading_level` | 준핵심 슬롯 | easy / medium / hard. 기술/학습 계열에서만 조건부 질문. inferred이면 재질문 안 함. |
| `mood` | 조건부 슬롯 | 감정/상태 (CAT1 신호 감지 시 활성화) |
| `comparison_basis` | 조건부 슬롯 | 비교 기준 (anchor + 유사도 표현 동시 감지 시) |
| `location` | 조건부 슬롯 | 지역/도서관 (CAT6/7 감지 시) |
| `avoid_mood` | 조건부 슬롯 | 피하고 싶은 분위기 |
| `length` | 예외 슬롯 | 분량 단서 직접 있을 때 |
| `constraints` | 제약 슬롯 | 페이지 수, 출판연도, 저자 포함/제외 등 |
| `availability_required` | 플래그 | 대출 가능 여부 조회 필요 여부 |

### 3-3. SessionContext — 세션 전체 상태

```python
class SessionContext(BaseModel):
    original_query      : str               # 첫 발화 원문
    anchors             : list[Anchor]       # 책 제목/저자명 파싱 결과 (슬롯 아님)
    slots               : SlotState          # 슬롯 상태
    turn_count          : int                # 현재 턴 번호
    asked_slots         : list[str]          # 이미 질문한 슬롯 목록
    slot_importance     : dict[str, str]     # signal 모듈 계산 결과
    slot_uncertainty    : dict[str, str]     # signal 모듈 계산 결과
    onboarding          : Optional[dict]     # 온보딩 데이터
    rag_ready_from_llm  : bool               # LLM 충분도 판단 결과
    llm_slots_to_ask    : list[str]          # LLM이 제안한 다음 질문 슬롯
    llm_question        : Optional[str]      # LLM이 미리 생성한 질문 문장
    llm_choices         : list               # LLM이 미리 생성한 선택지
    llm_confidence      : int                # LLM 충분도 판단 신뢰도 (0~100)
```

### 3-4. Anchor — 질의에서 파싱된 고정 기준점

```
Anchor = 슬롯과 다름
  - 비어있어도 세션 질문으로 채우지 않음
  - 있으면 쓰고 없으면 없는 것으로 처리
  - 예시: "채식주의자처럼 감성적인 소설" → Anchor(value="채식주의자", type="book_title")
```

### 3-5. MoodCategory — 감정/상태 분류 (16가지)

```
부정 계열 (low arousal / negative):  부정_소진, 부정_우울, 부정_무기력, 부정_공허
부정 계열 (high arousal / negative): 부정_불안, 부정_분노, 부정_압박
회복/위로 욕구 계열:                  회복_위로, 회복_이완, 회복_도피, 회복_의미
긍정 계열 (low arousal):             긍정_여유, 긍정_그리움
긍정 계열 (high arousal):            긍정_설렘, 긍정_활기
```

> **설계 근거**: arousal-valence 2차원 모델 + KOTE 43 감정 레이블 + 독서 동기 연구  
> (The Reading Agency 2024, PLOS ONE 2022, Koopman 2015, Lazarus & Folkman 대처 이론)

---

---

## 4. 슬롯 설계 상세

### 4-1. 슬롯 설계 철학

**슬롯이란?**  
추천을 만들기 위해 시스템이 채워야 하는 **정보 칸**이다.  
사용자 발화에서 추출하거나, 세션 질문으로 직접 물어보거나, 온보딩 데이터로 보완한다.

**왜 슬롯 기반인가?**

도서 추천에는 "어떤 책이 좋냐"는 정보보다 **"무엇을 원하는지"** 가 더 중요하다.  
순수 LLM에게 "어떤 책 원해?" 를 물으면 단발 응답만 나오지만,  
슬롯을 통해 대화 턴을 거치면서 요구사항을 점진적으로 좁혀갈 수 있다.

```
"책 추천해줘"  → 슬롯 없음 → 방향이 없어 추천 불가능
       ↓  세션 질문
"소설이요"     → topic 채움
       ↓  세션 질문
"위로받고 싶어" → mood 채움
       ↓  충분도 판단 통과
     RAG 검색  → 정확한 추천 가능
```

**슬롯 기반 설계의 핵심 원칙**:

1. **채움 기준 명확화**: 슬롯이 채워졌는지는 `is_filled()` + `is_reliable()`로 판단, LLM 판단 의존 최소화
2. **Source 등급 기반 신뢰도**: 같은 슬롯 값이라도 direct / inferred / ambiguous / null로 신뢰도 구분
3. **슬롯 ≠ anchor**: anchor는 정보 칸이 아니라 질의에서 발견된 고정 기준점. 비어있어도 세션 질문하지 않음
4. **조건부 활성화**: 모든 슬롯을 항상 물어보지 않음. 신호가 감지됐을 때만 해당 슬롯 활성화
5. **추천 실패를 최대한 줄이는 순서로 질문**: 방향 없이 검색하면 완전히 빗나가는 슬롯부터 먼저

---

### 4-2. 슬롯 분류 체계

슬롯은 활성화 조건과 역할에 따라 5가지로 구분한다.

```
┌─────────────────────────────────────────────────────────┐
│                   SlotState                             │
│                                                         │
│  핵심 슬롯 (항상 필요)                                  │
│    topic                                                │
│                                                         │
│  준핵심 슬롯 (대부분 필요, 카테고리·맥락에 따라 스킵)   │
│    purpose ─── reading_level                            │
│                                                         │
│  조건부 슬롯 (신호 감지 시만 활성)                      │
│    mood ─── comparison_basis ─── location ─── avoid_mood│
│                                                         │
│  예외 슬롯 (직접 단서 있을 때만 활성)                   │
│    length                                               │
│                                                         │
│  제약 슬롯 (리스트 구조)                                │
│    constraints: [page_range, pub_year, author, ...]     │
│                                                         │
│  플래그                                                 │
│    availability_required: bool                          │
└─────────────────────────────────────────────────────────┘

별도: Anchor (슬롯 아님 — 세션 질문 대상 외)
  anchors: list[Anchor]
```

#### 핵심 슬롯

`topic`만 해당. 비어있으면 반드시 세션 질문. 온보딩으로 대체하거나 생략하는 경우 없음.

#### 준핵심 슬롯 — 대부분 필요하지만 카테고리·맥락에 따라 스킵

비어있으면 세션 질문. 단 아래 조건에서 생략.

| 슬롯 | 이유 | 생략 조건 |
|------|------|-----------|
| `purpose` | 학습용 vs 재미용은 완전히 다른 책 | 카테고리에서 목적이 자명한 경우 (소설→재미, 요리→실용 등) |
| `reading_level` | 같은 주제도 쉬운 책 vs 깊은 책이 전혀 다름 | 기술/학습 계열에서만 질문. 소설/에세이는 생략. LLM inferred면 재질문 안 함. 온보딩 직접 fallback 없음. |

> `reading_level`은 `get_empty_core_slots()`에서도 제외되어 있으며, `filler.py` Rule [2]에서 직접 처리한다.

#### 조건부 슬롯 — 신호 감지 시만 활성

신호가 없으면 슬롯 자체가 비활성이며, 비어있어도 세션 질문하지 않는다.

| 슬롯 | 활성화 조건 | 채움 방식 |
|------|------------|----------|
| `mood` | CAT1(정서/상태) 신호 감지 | 주로 LLM 추출. 예외: 대분류 topic + 프로파일 있을 때 개인화 체크인 턴에서 선택지 제공 |
| `comparison_basis` | anchor + 유사도 표현 동시 감지 | LLM 추출 또는 세션 질문 버튼 |
| `location` | CAT6(대출가능) 또는 CAT7(지역) 신호 감지 | LLM 추출 또는 세션 질문 |
| `avoid_mood` | CAT9(회피) 직접 감지 또는 CAT1 부정 정서 | LLM 추출, 온보딩 보조 |

#### 예외 슬롯

`length`: 분량 단서가 직접 있거나 Refinement에서 요청할 때만 활성화  
`page_range`(Constraint)와의 차이: "짧은" 같은 **체감 단서** vs "300페이지 이하" 같은 **수치 제약**

#### 제약 슬롯 — Constraint 리스트

리스트 구조로, 여러 제약이 동시에 존재할 수 있다.

| type | 예시 | RAG 처리 |
|------|------|----------|
| `page_range` | "300페이지 이하" | constraints["page_range"] → 하드 필터 |
| `pub_year` | "2020년 이후" | constraints["pub_year"] → 하드 필터 |
| `author` | "한강 작가 포함" | constraints["author"] → 하드 필터 |
| `nonauthor` | "한강 제외" | constraints["author_non"] → 하드 필터 |
| `target_reader` | "중학생용" | filters["target_reader"] → 메타데이터 필터 |
| `availability` | "지금 빌릴 수 있는" | availability_required 플래그로 별도 처리 |
| `custom` | "번역서 제외" | filters["custom_constraints"] → 후처리용 |

---

### 4-3. Source 등급 시스템

모든 슬롯 값에는 **어디서 왔는가**를 나타내는 Source 등급이 붙는다.

```
direct    ─→ 사용자가 발화에서 명시적으로 언급
              예: "SF 소설 추천해줘" → topic.source = direct
              정책: 멀티턴에서 덮어쓰기 금지 (is_locked)

inferred  ─→ 맥락에서 논리적으로 추론 가능
              예: "SF 좋아해요" → purpose=재미(inferred)  [SF → 재미 추론]
              정책: uncertainty LOW이면 inferred 확인 턴 발동
                    uncertainty HIGH이면 세션 질문으로 직접 확인

ambiguous ─→ 해석이 여러 개 가능 (현재 구현에서는 드물게 사용)
              예: "가볍게 읽고 싶어요" → reading_level? length?
              정책: 세션 질문 필요

null      ─→ 언급 없음
              정책: topic/purpose이면 세션 질문 (온보딩으로 슬롯을 직접 채우지는 않음)
                    reading_level은 기술/학습 계열에서만 조건부 질문
```

#### 슬롯 잠금 (is_locked)

```python
def _is_locked(slot_value) -> bool:
    return slot_value.is_filled() and slot_value.source == SlotSource.direct
```

- `direct`로 채워진 슬롯은 멀티턴에서 LLM이 다시 추출해도 덮어쓰지 않음
- 예외: `is_refinement=True` + 새 값도 `direct` → 덮어씀 (사용자 명시적 수정 요청)

#### inferred 확인 턴 발동 조건

```
inferred 슬롯 존재
  + rag_ready=true (LLM 충분도 판단 통과)
  + uncertainty ≠ high (LOW 또는 MEDIUM일 때만)
  → 확인 카드 표시
    "이렇게 파악했어요: 목적: 재미 / 맞아요? / 바꿀게요"
```

> uncertainty HIGH이면 LLM이 rag_ready 판단 시 이미 고려했어야 하므로 별도 확인 생략

---

### 4-4. Anchor — 슬롯과 다른 개념

Anchor는 슬롯이 아니다.

| 항목 | 슬롯 | Anchor |
|------|------|--------|
| 없을 때 | 세션 질문으로 채움 | 없으면 없는 것으로 처리 |
| 목적 | 추천 조건 구성 | 직접 조회 가능한 고정 기준점 |
| 예시 | topic="소설", purpose="재미" | "채식주의자"(책 제목), "한강"(저자명) |
| 세션 질문 대상 | O | X |

**anchor 유형**:

| AnchorType | 예시 | 처리 방식 |
|-----------|------|----------|
| `book_title` | "채식주의자", "불편한 편의점" | DB에서 책 정보 조회 → 쿼리 재작성 |
| `author` | "한강", "무라카미 하루키" | DB에서 저자 작품 조회 → 쿼리 재작성 |
| `series` | "해리포터 시리즈" | 시리즈 전체 범위로 검색 |
| `library` | "마포구립서강도서관" | location 슬롯으로 이전 처리 |

**anchor가 없는데 comparison_basis가 생기면?**  
사후 검증에서 `_extract_anchor_from_raw()`로 comparison_basis.raw에서 역방향 추출 시도.  
추출 실패 시 comparison_basis 초기화 → 논리적 일관성 유지.

---

### 4-5. 각 슬롯 상세 설계

#### TopicSlot — 주제

```python
class TopicSlot(BaseModel):
    coarse : list[str]  # 대분류: "소설", "인문", "경제/경영" ...
    fine   : list[str]  # 중분류: "한국소설", "심리학", "SF" ...
    subject: list[str]  # 세부주제(자유형): "한국 근현대사", "양자역학 입문" ...
    source : SlotSource
```

**3단 계층 구조 이유**:

```
coarse (대분류) → RAG의 cate_depth1 필터 (하드 필터)
  "소설"이면 소설 DB만 검색

fine (중분류) → RAG의 score_boost cate_depth2 (부스트)
  "SF"이면 SF 태그 도서를 상위 노출

subject (세부주제, 자유형) → semantic_query에 포함 (시맨틱 검색)
  "한국 근현대사" → 자연어로 Dense 검색
```

**복수 주제 동시 지원**:  
"심리학이랑 철학 책" → `fine=["심리학", "철학"]`, `coarse=["인문"]`

**topic이 대분류 수준으로 너무 넓을 때** (STILL_BROAD_FINES):  
`topic_subject`를 추가로 질문해 세부 방향 확보.  
예: `fine=["자기계발"]` → STILL_BROAD_FINES 내 → "어떤 종류의 자기계발 책인가요?" 질문

**null_cases** (이런 경우 topic으로 추출하지 않음):  
- "위로받고 싶어요" → topic 아님, purpose 슬롯
- "가볍게 읽고 싶어요" → topic 아님, reading_level 슬롯

---

#### PurposeSlot — 독서 목적

```python
class PurposeValue(str, Enum):
    학습 = "학습"  # 공부, 입문, 배우고 싶어서
    교양 = "교양"  # 알고 싶어서, 교양으로
    재미 = "재미"  # 재미있게, 즐기고 싶어서
    실용 = "실용"  # 실생활에 적용, 써먹으려고
```

**목적이 추천에 실질적으로 영향을 미치는 경우**:
- "심리학 책" + 학습 → 교재/전공서 방향
- "심리학 책" + 교양 → 대중 심리학 방향
- "심리학 책" + 재미 → 스토리텔링 심리학 방향

**생략 조건** (`_SKIP_PURPOSE_COARSE`):  
목적이 카테고리에서 자명할 때:
- 소설, 시/에세이, 만화 → "재미" 전제
- 요리, 여행, 가정/육아 → "실용" 전제
- 외국어, 취업/수험서 → "학습" 전제

---

#### ReadingLevelSlot — 읽기 부담

```python
class ReadingLevelValue(str, Enum):
    easy   = "easy"    # 가볍고 쉽게 읽히는
    medium = "medium"  # 적당히 생각할 거리
    hard   = "hard"    # 깊이 있는
```

**카테고리별 질문 여부**:
- 기술/학습 계열 (컴퓨터/IT, 과학, 경제/경영 등): 난이도 편차가 크므로 **HIGH importance** → 조건부 질문 (null이고 STILL_BROAD_FINES 밖일 때)
- 소설/에세이 계열 (`_SKIP_RL`): 편차가 상대적으로 작아 질문 생략
- inferred로 이미 채워진 경우: 재질문하지 않음 ("파이썬 기초" → easy inferred → 통과)
- 온보딩에서 reading_level을 직접 가져오는 fallback은 현재 없음

**inferred 처리 예시**:
- "파이썬 기초 책 추천해줘" → reading_level=easy(inferred) [기초 → easy 추론]
- uncertainty LOW → inferred 확인 턴 또는 그대로 진행

---

#### MoodSlot — 감정/상태 (조건부)

```python
class MoodSlot(BaseModel):
    categories: list[MoodCategory]  # 복합 감정 지원 (불안하고 우울한 → 2개)
    raw       : Optional[str]       # 원문 표현 보존 ("지쳐서", "번아웃 직전이라")
    source    : SlotSource
```

**활성화 조건**: CAT1(정서/상태) 신호 감지 시  
**채움 방식**: 주로 LLM이 자유 발화에서 추출  
**예외**: 대분류 topic 요청 + 온보딩 프로파일 있을 때, 개인화 체크인 턴에서 선택지로 직접 묻기도 함  
(`chat_service._needs_personalization_turn()` → `generate_personalization_question()`)

**16개 MoodCategory 분류 체계**:

```
Low arousal / Negative (지침·소진 계열)
  부정_소진  : 지쳐서, 번아웃, 피곤해서
  부정_우울  : 우울해서, 슬플 때
  부정_무기력: 의욕없어서, 아무것도 하기 싫을 때
  부정_공허  : 공허할 때, 텅 빈 느낌

High arousal / Negative (긴장·분노 계열)
  부정_불안  : 불안해서, 두려워서, 초조할 때
  부정_분노  : 화나서, 억울해서, 짜증날 때
  부정_압박  : 스트레스받아서, 숨막혀서

회복/위로 욕구 (방향 명시 — arousal 무관)
  회복_위로  : 위로가 필요해, 공감받고 싶어
  회복_이완  : 쉬고 싶어, 숨 쉬고 싶어         ← The Reading Agency: 이완
  회복_도피  : 현실 도피, 잠깐 잊고 싶어        ← The Reading Agency: 현실도피
  회복_의미  : 이 상황을 이해하고 싶어           ← Koopman: 의미만들기

Low arousal / Positive (여유·평온 계열)
  긍정_여유  : 여유로운, 기분 좋은, 홀가분한
  긍정_그리움: 그리운, 감성적인 기분

High arousal / Positive (설렘·활기 계열)
  긍정_설렘  : 설레는, 신나는, 두근거리는
  긍정_활기  : 활기찬, 의욕 넘치는              ← PLOS ONE: 활기
```

> **설계 근거**: 같은 "지쳐서"라도 회복_이완(쉬고 싶어)이냐 회복_의미(이해하고 싶어)냐에 따라  
> 추천 책의 유형(난이도·형식)이 크게 달라진다. 단순 긍정/부정이 아닌 방향까지 구분한 이유.

**null_cases** (mood로 추출하면 안 되는 경우):
- "위로가 되는 책" → mood 아님, purpose 슬롯
- "따뜻한 책" → mood 아님, comparison_basis 또는 constraints
- "가벼운 책" → mood 아님, reading_level = easy

---

#### ComparisonBasisSlot — 비교 기준 (조건부)

```python
class ComparisonBasisSlot(BaseModel):
    dimensions: list[ComparisonDimension]  # 비교 기준 축
    raw       : Optional[str]              # 자유형 원문 또는 custom 보완
    source    : SlotSource
```

**활성화 조건**: anchor(책 제목/저자명) + 유사도 표현("같은", "비슷한", "처럼" 등) **동시** 감지  
anchor 없이 유사도 표현만 있으면 활성화하지 않음.

```
"채식주의자처럼 감성적인 소설"
  → anchor=채식주의자 + 유사도="처럼" → comparison_basis 활성화

"비슷한 분위기 책"
  → anchor 없음 → comparison_basis 비활성화
```

**6가지 ComparisonDimension**:

| dimension | 한국어 | 예시 발화 | RAG 처리 |
|-----------|-------|----------|---------|
| `mood` | 분위기 | "따뜻한 분위기" | 분위기 태그 기반 유사도 |
| `topic` | 주제 | "비슷한 소재" | 주제 벡터 유사도 |
| `style` | 문체 | "문장 스타일이 비슷한" | 문체 태그 유사도 |
| `difficulty` | 난이도 | "쉽게 읽히는 점" | reading_level 필터 |
| `depth` | 깊이 | "생각할 거리가 있는" | score_boost에 반영 |
| `custom` | 직접 입력 | "반전 있는" | semantic_query에 포함 |

**채워지는 경로**:
1. 발화에서 직접 드러날 때 → LLM 추출 (source=direct)  
   예: "채식주의자처럼 따뜻한 책" → dimensions=[분위기]
2. 발화에서 드러나지 않을 때 → 세션 질문 버튼  
   예: "채식주의자 같은 책" → dimensions 비어있음 → "어떤 점이 비슷한?" 질문

---

#### LocationSlot — 지역/도서관 (조건부)

```python
class LocationSlot(BaseModel):
    region  : Optional[str]  # "서울 마포구"
    library : Optional[str]  # "마포구립서강도서관"
    source  : SlotSource
```

**활성화 조건**: CAT6(대출가능) 또는 CAT7(지역/도서관) 신호 감지  
**RAG 연결**: `availability_required=True`일 때 정보나루 API 대출가능 조회에 사용

**세션 질문 3가지 경로**:

| 조건 | 질문 방식 |
|------|----------|
| 온보딩 region 없음 | "어느 지역 기준으로 찾아드릴까요?" + 직접 입력 |
| 온보딩 region 있음 | "오늘은 어느 지역 기준으로 찾으실까요?" + 온보딩 지역 선택지 |
| 발화에서 직접 언급 | location 슬롯 바로 채움 (세션 질문 불필요) |

---

#### AvoidMoodSlot — 피하고 싶은 분위기 (조건부)

```python
class AvoidMoodSlot(BaseModel):
    keywords: list[str]   # ["너무 무거운", "너무 잔인한"]
    source  : SlotSource
```

**활성화 조건**: CAT9(회피/부정 신호) 직접 감지  
**온보딩 연동**: 세션 avoid_mood 없을 때 온보딩 `disliked_keywords` 보조 신호 사용  
단, 세션 topic과 충돌 시 온보딩 비활성 (예: "전쟁 역사책" + 온보딩 "너무 잔인한")

---

#### LengthSlot — 분량 (예외)

```python
class LengthSlot(BaseModel):
    level : Optional[LengthLevel]  # short / medium / long
    source: SlotSource
```

`page_range`(Constraint)와의 차이:

| | LengthSlot | page_range (Constraint) |
|--|-----------|------------------------|
| 표현 | "짧은", "가볍게", "금방 읽히는" | "300페이지 이하" |
| 처리 | Reranker 소프트 신호 | 하드 필터 (메타데이터 필터) |
| 기준 | 독자 체감 (주관적) | 숫자 기준 (객관적) |

**정서형 쿼리와 length의 관계**:  
"지쳐서 가볍게 읽고 싶어요" → CAT1(정서) + CAT3(분량) → length=short  
단, "지쳐서" 만으로는 length를 자동으로 short로 단정하지 않음  
(방향 B 확정: 정서형이라고 해서 짧은 책이 정답이라고 단정할 수 없음)

---

### 4-6. 슬롯 간 상호작용 규칙

슬롯들은 독립적으로 보이지만 실제로는 서로 영향을 미친다.

#### anchor 존재 → topic 질문 면제

```python
if any(a.type in (AnchorType.book_title, AnchorType.author) for a in context.anchors):
    empty.discard("topic")
```

이유: "채식주의자 같은 책" → anchor에서 이미 방향(소설, 한국문학 스타일)을 알 수 있음

#### anchor 존재 → comparison_basis 활성화

```python
if context.anchors and not slots.comparison_basis.is_filled():
    empty.add("comparison_basis")
```

anchor가 있으면 반드시 "어떤 점이 비슷한지" 알아야 의미 있는 검색이 가능

#### mood 부정 계열 → purpose 선택지 필터링

```python
if mood_cat in _HEAVY_MOOD_CATEGORIES:
    base_labels = [
        label for label in base_labels
        if label not in {"공부나 입문용으로", "실생활에 도움되는 걸"}
    ]
```

"지쳐서" + "공부하려고" 는 UX적으로 어울리지 않으므로 해당 선택지 제거

#### mood 부정 계열 → reading_level 선택지 조정

```python
if mood_cat in _HEAVY_MOOD_CATEGORIES:
    labels = ["가볍고 쉽게 읽히는 책", "적당히 생각할 거리가 있는 책", "상관없어요"]
    # "깊이 있어도 괜찮아요" 선택지 제거
```

부정 정서 상태에서 "깊이 있어도 괜찮아요" 는 어울리지 않으므로 제거

#### topic 없음 + anchor 있음 + recent_liked_books → anchor 보강

```python
# topic null + profile override 시 최근 좋아한 책을 anchor(book_title)로 추가
if not context.slots.topic.is_filled() and context.onboarding:
    recent = context.onboarding.get("recent_liked_books") or []
    for book in recent[:5]:
        result.append({"value": title, "type": "book_title"})
```

topic이 없어도 최근 좋아한 책 패턴으로 RAG 방향을 잡을 수 있음

#### availability_required → location 강제 활성화

```python
if slots.availability_required and not slots.location.is_filled():
    empty.add("location")
```

"지금 빌릴 수 있는" 요청이면 어느 도서관인지 반드시 알아야 대출 가능 여부 조회 가능

---

### 4-7. 슬롯 → RAG 연결 구조

각 슬롯이 RAG 쿼리의 어느 필드로 연결되는지 정리한다.

```
슬롯                    RAG 쿼리 필드                 처리 방식
─────────────────────────────────────────────────────────────────
topic.coarse       → filters["cate_depth1"]          하드 필터
topic.fine         → score_boost["cate_depth2"]      부스트
topic.subject      → score_boost["subject"]          부스트 + semantic_query 포함

purpose            → session_signals["purpose"]      Reranker 신호 (높은 가중치)
                   → semantic_query에 자연어로 포함

reading_level      → session_signals["reading_level"] Reranker 신호
                   → semantic_query에 자연어로 포함

mood               → session_signals["mood"]          Reranker 신호
                   → semantic_query에 감정 맥락으로 포함

anchor(book_title) → anchors[{value, type}]          anchor_book_pipeline 쿼리 재작성
anchor(author)     → anchors[{value, type}]          author 작품 기반 쿼리 재작성

comparison_basis   → session_signals["comparison_basis"] Reranker 신호
                   → dimensions별로 검색 전략 분기

location           → session_signals["location"]      availability API 호출
avoid_mood         → session_signals["avoid_mood"]    Reranker 신호 (페널티)

page_range         → constraints["page_range"]        하드 필터
pub_year           → constraints["pub_year"]          하드 필터
author(constraint) → constraints["author"]            하드 필터
nonauthor          → constraints["author_non"]        하드 필터
availability       → availability_required=true       정보나루 API 조회

온보딩 preferred_sub → onboarding_signals["preferred_sub_categories"]  약한 신호
온보딩 disliked     → onboarding_signals["disliked_keywords"]           약한 신호
온보딩 page_range   → onboarding_signals["page_range_soft"]             약한 신호
```

**session_signals vs onboarding_signals 가중치 차이**:

```
session_signals   → Reranker 높은 가중치  (사용자가 이번 세션에서 직접 말한 것)
onboarding_signals → Reranker 낮은 가중치  (프로파일 기반 배경 정보)
```

온보딩 신호는 `uncertainty HIGH` 슬롯에 한해 사용 (세션 신호가 충분하면 온보딩 미사용).

---

## 5. 모듈별 상세 설명

### 5-1. 진입점 & API 레이어

**파일**: `app/main.py`, `app/api/routes/chat.py`

#### main.py

- FastAPI 앱 생성, CORS 설정, 라우터 등록
- 로깅 설정을 앱 생성 **전**에 먼저 실행 (임포트 로그가 설정 전 출력되는 문제 방지)
- DB 테이블 생성은 `try/except`로 감싸 PostgreSQL 없어도 서버 기동 가능

**등록된 라우터**:

| 경로 prefix | 파일 | 역할 |
|-------------|------|------|
| `/api/chat` | routes/chat.py | 메인 도서 추천 대화 |
| `/api/auth` | routes/auth.py | 사용자 인증 |
| `/api/profile` | routes/profile.py | 프로파일 조회/수정 |
| `/api/onboarding` | routes/onboarding.py | 온보딩 데이터 |
| `/api/eval` | routes/eval.py | 평가/로그 |

#### ChatRequest / SlotChatResponse (스키마)

**파일**: `app/schemas/chat_schema.py`

**ChatRequest** (요청):
```
query            : str          # 사용자 발화
history          : list[Message] # 이전 대화 히스토리
context          : Optional[dict]# 이전 턴 SessionContext (stateless 멀티턴)
selected_choice  : Optional[dict]# 사용자가 클릭한 버튼
pending_slots    : Optional[list]# 선택지가 채우는 슬롯 목록
confirm_inferred : Optional[bool]# inferred 확인 턴 응답
user_profile     : Optional[dict]# {"user_id": "P001-A"}
```

**SlotChatResponse** (응답):
```
needs_clarification    : bool       # True면 추가 질문 필요
ready_for_rag          : bool       # True면 RAG 검색 실행 가능
message                : str        # 사용자에게 표시할 메시지
clarification_question : str        # 질문 문장
clarification_choices  : list[dict] # 선택지 버튼 목록
pending_slots          : list[str]  # 이 선택지가 채우는 슬롯 이름
context                : dict       # 업데이트된 SessionContext (다음 턴에 그대로 전달)
filled_slots           : list[str]  # 현재 채워진 슬롯 이름 목록
rag_query              : dict       # RAG 쿼리 (ready_for_rag=True일 때)
is_confirmation        : bool       # True면 inferred 확인 카드
inferred_summary       : list       # 확인 카드에 표시할 슬롯 요약
```

---

### 5-2. ChatService — 파이프라인 오케스트레이터

**파일**: `app/services/chat_service.py`

#### 역할

매 턴마다 사용자 입력의 유형을 판단하고 적절한 처리 경로로 분기하는 메인 컨트롤러.

#### 입력

`ChatRequest` (API 요청 전체)

#### 출력

`SlotChatResponse` (API 응답 전체)

#### 처리 분기

```
입력 유형 판단
  ├─ confirm_inferred 있음 → inferred 확인 턴 처리
  │     confirm=True  → inferred 슬롯 direct로 격상 → RAG 또는 추가 질문
  │     confirm=False → 해당 슬롯 null 초기화 → 재질문
  │
  ├─ selected_choice + pending_slots 있음 → apply_choice() 실행
  │     버튼 클릭 → 슬롯 직접 업데이트
  │
  └─ 자유 발화 → extract_slots() 실행
        → 개인화 체크인 턴 필요 여부 판단
        → 프로파일 기반 RAG override 여부 판단
        → get_slots_to_ask()로 다음 질문 슬롯 결정
             슬롯 있음 → generate_question() → 질문 응답
             슬롯 없음 → inferred 확인 턴 또는 RAG 실행
```

#### 주요 Rule-based 처리

**개인화 체크인 턴** (`_needs_personalization_turn`):
- 조건: 대분류 수준 topic + 온보딩 프로파일 있음 + mood 미채움 + 아직 체크인 안 함
- "지금 어떤 기분으로 읽고 싶으세요?" 질문 — LLM 판단 무관하게 먼저 실행

**프로파일 기반 RAG override** (`_profile_covers_request`):
- 조건: topic/mood/anchor 모두 null + recent_liked_books 2권 이상
- rag_ready_from_llm을 True로 강제 → RAG 바로 실행

**온보딩 데이터 로드** (`_load_onboarding`):
- `user_metadata.json`에서 user_id로 조회 (데모 버전)
- 실서비스에서는 DB 조회로 교체 권장
- 서버 기동 시 한 번만 로드 후 메모리 캐시

---

### 5-3. Signal Detector — 쿼리 특성 사전 감지

**파일**: `app/modules/signal/detector.py`, `app/modules/signal/expressions.py`

#### 역할

LLM 호출 **전**에 Kiwi 형태소 분석으로 쿼리의 특성을 미리 파악한다.  
결과를 LLM 프롬프트에 `importance` 힌트로 전달해 추출 품질을 높인다.

#### 입력

```python
query: str  # 사용자 발화 원문
```

#### 출력

```python
SignalResult:
  categories         : DetectedCategories  # 카테고리 1~9 감지 여부 플래그
  scores             : SlotScores          # 슬롯별 importance(HIGH/MEDIUM/LOW) + uncertainty(HIGH/LOW)
  needs_llm_fallback : bool                # 아무 카테고리도 감지 안 됐으면 True
```

#### 감지 카테고리 (9가지)

| 카테고리 | 신호 예시 | 활성화되는 슬롯 |
|----------|-----------|-----------------|
| CAT1 (정서/상태) | "지쳐서", "불안해서", "설레는" | mood (HIGH importance) |
| CAT2 (목적) | "공부하려고", "위로받고 싶어", "재미있게" | purpose (HIGH importance) |
| CAT3 (분량) | "짧은 책", "두꺼운 책" | length (HIGH importance) |
| CAT4 (난이도) | "쉽게 읽히는", "깊이 있는" | reading_level (HIGH importance) |
| CAT5 (형식/주제) | "소설", "심리학", "SF" | topic (HIGH importance) |
| CAT6 (대출 가능) | "지금 빌릴 수 있는", "대출 가능한" | location (HIGH importance) |
| CAT7 (지역/도서관) | "성북구", "마포구립서강도서관" | location (HIGH importance, LOW uncertainty) |
| CAT8 (레퍼런스) | "같은", "비슷한", "처럼", "스타일의" | comparison_basis (HIGH importance) |
| CAT9 (회피) | "너무 무거운 건 빼줘", "잔인한 건 싫어" | avoid_mood (HIGH importance) |

#### 처리 흐름

```
쿼리
  → _extract_features()   : Kiwi 형태소 분석 → verb_stems, noun_tokens 추출
  → _detect_categories()  : 카테고리별 표현 사전 매칭
  → _compute_scores()     : 감지된 카테고리 조합으로 importance 설정 (단조 증가)
  → _apply_cross_rules()  : uncertainty LOW 확정 + 카테고리 교차 규칙
  → SignalResult 반환
```

#### 설계 포인트

**"처럼"/"만큼" 처리**:
- Kiwi는 이를 JX(보조사)로 분석 → NNG 매칭이 안 됨
- 해결: `_COMPARISON_SUFFIX_PATTERN` 정규식으로 별도 감지
  ```python
  _COMPARISON_SUFFIX_PATTERN = re.compile(r'[가-힣a-zA-Z0-9]{2,}(?:처럼|만큼)', re.UNICODE)
  ```

**uncertainty 결정 원칙**:
- `_compute_scores()`는 importance만 올림 (단조 증가)
- uncertainty를 LOW로 낮추는 작업은 `_apply_cross_rules()`에서만 처리
- 예: CAT2_FUN 감지 → purpose uncertainty=LOW ("재미" 방향 확정), difficulty uncertainty=LOW

**Kiwi 사용자 사전**:
- "자기계발서", "추리소설", "라이트노벨" 등 복합명사를 단일 NNG로 등록
- Kiwi가 여러 형태소로 쪼개는 것을 방지

---

### 5-4. Anchor Extractor — 비교 앵커 정규식 사전 추출

**파일**: `app/modules/slot/anchor_extractor.py`

#### 역할

LLM 단독 처리의 한계(~75-80% 천장)를 돌파하기 위해,  
비교 표현 패턴을 **LLM 호출 전**에 정규식으로 감지해 anchor 후보를 추출한다.  
결과를 LLM 추출 프롬프트에 힌트로 주입 → LLM이 "발견"이 아닌 "확인"만 하면 되는 구조.

#### 입력

```python
query: str  # 사용자 발화 원문
```

#### 출력

```python
AnchorCandidate:
  text        : str    # 추출된 anchor 후보 텍스트 ("채식주의자", "장하준")
  anchor_type : str    # "book_title" | "author" | "ambiguous"
  confidence  : float  # 0.0 ~ 1.0
  pattern     : str    # 트리거된 비교 표현 ("처럼", "같은", "스타일의")
```

None 반환 시: 비교 표현 패턴 없거나 신뢰 가능한 후보 없음.

#### 감지하는 비교 패턴 (13가지)

| 패턴 | 기본 anchor_type | 비고 |
|------|-----------------|------|
| 스타일의 / 스타일로 | ambiguous | 저자 연관성 높음 |
| 처럼 | book_title | 직접 접착, JX 조사 |
| 만큼 | ambiguous | 길이로 판별 |
| 수준으로 / 수준의 | book_title | 품질/깊이 비교 |
| 느낌으로 / 느낌의 | book_title | — |
| 같은 | book_title | — |
| 비슷한 / 유사한 | book_title | — |
| 정도로 / 정도의 | book_title | — |

#### anchor 구 추출 핵심 로직 (`_extract_anchor_phrase`)

**Step 0. 의존명사 패턴 (특수 처리)**  
"지혜롭게 나이 든다는 것처럼" → 마지막 단어가 의존명사(것/수/때/줄) + 직전 단어가 관형형 어미(는/은/ㄴ/을/ㄹ)로 끝나면 전체 구를 통째로 포함.

```
"든다는 것" → last="것" ∈ DEPENDENT_NOUNS + second_last="든다는" endswith "는"
→ "지혜롭게 나이 든다는 것" (전체 5 eojeol, 15자 이하)
```

**Step 1. 관형어 역방향 확장**  
"불편한 편의점같은" → "편의점"이 마지막, "불편한"이 관형사형 어미("한") → 2 eojeol 포함.

**Step 2. 기본: 마지막 단어 반환**  
"채식주의자처럼" → "채식주의자"

#### 관형어 판별 (`_looks_like_adnominal`)

우선순위 순서:
1. 관형사형 어미(`한/은/는/인/된/할/올/생/대`)로 끝나면 True → **2글자 인칭대명사+는/은("나는"/"저는") 예외**
2. 1글자 이하 → False
3. 2글자: 숫자 포함이면 True (20대, 82년)
4. 3글자 이상: 조사 제거 후 2글자 이상 → True ("소년이" → "소년")

#### 저자명 판별 (`_is_likely_author`)

| 조건 | 결과 | confidence |
|------|------|-----------|
| 숫자 포함 | 책 제목 ("82년생 김지영") | 0.85 |
| 공백 있음 + 2-3 파트 + 각 파트 2-4글자 | 외국 저자명 스타일 | 0.65 |
| 2글자 단일어 + 한국 성씨로 시작 | 한국 저자명 (한강, 김훈) | 0.82 |
| 3글자 단일어 + 한국 성씨로 시작 | 한국 저자명 (박경리) | 0.75 |
| 5글자 초과 단일어 | 책 제목 가능성 높음 | 0.30 |

#### false positive 방지 (stopwords)

```python
_ANCHOR_STOPWORDS = frozenset({
    "아무것", "아무거나", "무엇", "무언가",   # 부정 대명사
    "이것", "그것", "저것", "이게", "그게",    # 지시 대명사
    "책", "소설", "에세이", "시집", "작품",    # 장르/형식 일반 명사
    "것", "수", "때", "줄",                    # 의존명사 단독
    ...
})
```

"소설처럼 읽히는 인문서" → "소설"이 stopword → None 반환 (false positive 차단)

#### 알려진 한계

- **외래어 복합 표제어**: "드래곤 라자 같은" → "라자"(마지막 단어만)
- **3단어 이상 외래어**: "엔드 오브 타임 수준으로" → "타임"
- 이 경우에도 LLM에게 partial 힌트를 제공해 성능 향상 효과는 있음

---

### 5-5. Slot Filler — LLM 슬롯 추출 & 충분도 판단

**파일**: `app/modules/slot/filler.py`

#### 역할

1. LLM으로 사용자 발화에서 슬롯 값을 추출해 `SessionContext`에 반영
2. `get_slots_to_ask()`로 다음 질문할 슬롯 우선순위 결정
3. 멀티턴에서 슬롯 누적 업데이트 (이미 direct로 채워진 슬롯은 보존)

#### extract_slots() — 메인 함수

**입력**:
```python
query  : str            # 현재 발화
context: SessionContext # 현재 세션 컨텍스트
history: list[dict]     # 이전 대화 목록
```

**출력**: 업데이트된 `SessionContext`

**내부 처리**:

```
1. signal_result = detect(query)                  # Kiwi 기반 신호 감지
2. anchor_hint = extract_anchor_candidate(query)   # 정규식 앵커 사전 추출

3. LLM Call 1 (HCX-DASH-002, temp=0.0):
   build_slot_extraction_messages() → chat_complete_json()
   → topic, purpose, reading_level, mood, anchor, constraints, comparison_basis 등

4. _apply_extraction(context, raw)
   → LLM 결과를 SessionContext에 반영

5. LLM Call 2 (HCX-007, temp=0.1):
   build_sufficiency_messages() → chat_complete_json()
   → rag_ready, confidence, slots_to_ask, question, choices, reasoning

6. 절대 규칙 강제 적용:
   - slots_to_ask 있으면 rag_ready=false 강제
   - confidence < 70이면 rag_ready=true → false override
```

#### _apply_extraction() — LLM 결과 반영

**슬롯 채움 정책**:
- `direct`로 채워진 슬롯은 덮어쓰지 않음 (`_is_locked`)
- `inferred`/`ambiguous`는 더 나은 정보로 업데이트 가능
- `mood`는 한 번 채워지면 같은 세션에서 업데이트하지 않음
- `is_refinement=True` + 새 값도 `direct`이면 예외적으로 덮어씀 (사용자 명시 변경)

**topic 정규화**:
- `get_canonical_fine()` → 트리 정규 중분류로 정규화
- `get_coarse_category()` → 중분류에서 대분류 역방향 매핑

**사후 검증** (comparison_basis + anchor):
- comparison_basis가 채워졌는데 anchor가 없으면 오류 상황
- `_extract_anchor_from_raw()` → comparison_basis.raw에서 anchor 역추출 시도
- 추출 실패 시 comparison_basis 초기화

#### get_slots_to_ask() — 다음 질문 슬롯 결정

**우선 처리 Rule-based 체크** (LLM 판단보다 먼저 실행):

| Rule | 조건 | 결과 |
|------|------|------|
| [1] | topic 채워짐 + coarse 매핑 실패 + fine이 불명확 | "topic_subject" 강제 질문 |
| [2] | 기술/학습 계열 topic + reading_level null | "reading_level" 강제 질문 |
| [3] | fine ⊆ STILL_BROAD_FINES + mood/anchor 없음 | "topic_subject" 강제 질문 |
| [3-B] | fine specific + 보완 슬롯 모두 null | "purpose" 질문 |
| [4] | anchor + comparison_basis 채워짐 + 미확인 | "comparison_basis" 확인 질문 |

**LLM 판단 적용**:
- rag_ready_from_llm=True → 추가 질문 없음
- llm_slots_to_ask 있으면 우선 사용 (이미 채워진 슬롯 제외)

**Rule-based fallback** (`_get_slots_to_ask_fallback`):
- LLM 판단 실패 시 importance/uncertainty 기반으로 슬롯 우선순위 계산
- `_PRIORITY_CONDITIONS` 패턴 매칭 후 `_group_slots()`으로 묶기

---

### 5-6. Question Generator — 세션 질문 생성

**파일**: `app/modules/slot/question_generator.py`

#### 역할

`slots_to_ask` 목록을 받아 사용자에게 보여줄 질문과 선택지를 생성한다.

#### 입력

```python
slots_to_ask : list[str]      # 질문할 슬롯 목록
context      : SessionContext  # 현재 컨텍스트 (llm_question, llm_choices 포함)
```

#### 출력

```python
SessionQuestion:
  question : str        # 질문 문장
  choices  : list[dict] # 선택지 버튼 목록 [{"label": "...", "slots": {...}}, ...]
  slots    : list[str]  # 이 질문이 채우는 슬롯 이름
```

#### 처리 우선순위

```
1순위: 코드 기반 (온보딩·anchor 데이터 필요 → LLM 불필요)
   - location  → 온보딩 frequent_libraries로 선택지 구성
   - comparison_basis → anchor 이름 활용한 고정 질문

2순위: HCX-007 사전 생성값 + 코드 기반 선택지 결합
   - purpose / reading_level
   → question: context.llm_question (없으면 템플릿 폴백)
   → choices: _get_predefined_choices() (목적/읽기부담 고정 선택지)

3순위: HCX-007 사전 생성값 그대로 사용
   - topic_subject / 복수 슬롯
   → context.llm_question + context.llm_choices

Fallback: 별도 HCX-007 호출
   - 위 모두 실패 시 topic_subject → _generate_detail_question()
```

#### apply_choice() — 선택지 응답 반영

버튼 클릭 응답을 슬롯에 직접 반영한다.

| 선택지 key | 처리 |
|-----------|------|
| `purpose` | PurposeValue Enum 변환 후 slots.purpose 업데이트 |
| `reading_level` | ReadingLevelValue Enum 변환 후 업데이트 |
| `topic_fine` | get_coarse_category()로 coarse 역방향 매핑 후 TopicSlot 생성 |
| `comparison_basis_dim` | ComparisonDimension Enum 변환, 기존 dimensions에 추가 |
| `location_library` / `location_region` | LocationSlot 업데이트 |
| `mood` | MoodCategory Enum 변환 후 MoodSlot 생성 |

---

### 5-7. RAG Query Builder — RAG 쿼리 생성

**파일**: `app/modules/slot/rag_query_builder.py`

#### 역할

슬롯 채움이 완료된 `SessionContext`를 입력받아  
검색 시스템(BM25 + Dense)이 사용할 쿼리 객체를 생성한다.

#### 입력

```python
context: SessionContext  # 슬롯 충분히 채워진 상태
```

#### 출력

```python
{
    "keyword_query"        : list[str],  # BM25용 키워드 목록
    "semantic_query"       : str,        # Dense 검색용 자연어 쿼리
    "filters"              : dict,       # 메타데이터 필터 (cate_depth1 등)
    "constraints"          : dict,       # 하드 필터 (author, page_range 등)
    "score_boost"          : dict,       # Reranker 가중치 (cate_depth2, subject)
    "availability_required": bool,       # 대출 가능 여부 조회 필요 여부
    "anchors"              : list[dict], # anchor 정보
    "session_signals"      : dict,       # 세션 슬롯 신호 (높은 가중치)
    "onboarding_signals"   : dict,       # 온보딩 보조 신호 (낮은 가중치)
    "slot_revision_hints"  : dict,       # 슬롯 수정 힌트 (Reranker용)
}
```

#### 처리 흐름

```
1. _summarize_slots() → 슬롯 상태를 자연어로 요약
2. LLM (HCX-DASH-002, temp=0.2) → keyword_query + semantic_query 생성
3. _build_filters() → cate_depth1 필터 + constraints 구성
4. _build_score_boost() → cate_depth2, subject 목록
5. _apply_refinement() → Refinement 요청이면 이전 쿼리에 수정 사항 반영
6. _anchors_to_list() → anchor + recent_liked_books(topic null 시 fallback)
7. _build_session_signals() → 세션 슬롯 신호 (Reranker 높은 가중치)
8. _build_onboarding_signals() → 온보딩 보조 신호 (Reranker 낮은 가중치)
```

#### 온보딩 신호 활용 조건

```
uncertainty HIGH 슬롯에 한해서만 온보딩 보조 신호 사용.
uncertainty LOW → 세션 신호가 충분하므로 온보딩 미사용.

예)
  topic fine이 대분류 수준(BROAD_TOPICS 내) → preferred_sub_categories 추가
  세션에 page_range 제약 없음 → preferred_length → page_range_soft 추가
  availability_required=True → frequent_libraries 추가
```

#### 온보딩 disliked_keywords 충돌 판단

세션 topic이 온보딩 회피 태그와 연관되면 온보딩 비활성.  
예: "전쟁 역사책" + 온보딩 "너무 잔인한" → 충돌 → 온보딩 비활성

#### Refinement 처리

`_apply_refinement()`:
- 이전 semantic_query + 수정 사항(reading_level/length/availability/avoid_mood 등) 반영
- 처음부터 재생성 X → 이전 쿼리에 prefix/suffix 방식으로 수정

---

### 5-8. Pipeline — 검색 파이프라인 실행

**파일**: `app/services/pipeline.py`

#### 역할

RAG 이후 단계들(BM25 검색 → Reranker → 대출 가능 여부 조회)을 순서대로 실행한다.  
각 단계는 독립 함수로 분리되어 있어 단계별 교체/비활성화/추가가 용이하다.

#### 단계별 설명

| 단계 | 함수 | 입력 | 출력 |
|------|------|------|------|
| [2] | `run_rag_query()` | SessionContext | rag_query dict |
| [2-1] | `run_anchor_query_rewrite()` | rag_query | 재작성된 rag_query |
| [3] | `run_bm25_search()` | rag_query | 검색 결과 list |
| [4] | `run_reranker()` | bm25_results + rag_query | 재순위 결과 list |
| [5] | `run_availability()` | books list | {isbn: {has_book, loan_available}} |

**모든 단계는 graceful skip**: 모듈이 없거나 키 없으면 빈 결과 반환 (서버 다운 없음)

#### PipelineResult.final_results — 3-시나리오 필터링

```
availability_index 없음
  → Top3 그대로 반환

[Scenario C] availability_required=True
  → 대출가능 Top3만

[Scenario A] 1등 대출가능
  → 대출가능 Top3만

[Scenario B] 1등 대출불가
  → 대출가능 Top3 + 1등 추가 (선택권 제공)
```

---

### 5-9. Category Mapper — 카테고리 정규화

**파일**: `app/modules/llm/category_mapper.py`

#### 역할

LLM이 추출한 자유형 topic 값을 `category_tree.json` 기준 대분류(coarse)로 정규화한다.

#### 제공 함수

**`get_coarse_category(fine: str) → Optional[str]`**

```
처리 순서:
  0. _COARSE_ALIASES 직접 매핑 → "에세이" → "시/에세이"
  1. _FINE_TO_COARSE 정확 매핑 → "한국소설" → "소설"
  2. 공백 제거 후 재시도 → "현대 소설" → "현대소설" → "소설"
  3. 부분 매칭 → "SF소설" → "소설"
  4. 실패 → None 반환
```

**`get_canonical_fine(free_form: str) → Optional[str]`**
- 자유형 주제어 → 카테고리 트리의 정규 중분류 값으로 변환

#### 설계 포인트

**fine/coarse 동명 충돌 방지**:
- "대학교재"는 대분류 이름이면서 여러 대분류의 중분류로도 등록됨
- `_build_fine_to_coarse()`에서 대분류 이름과 동일한 중분류는 역방향 매핑 제외
- `_COARSE_ALIASES`에서 별도 처리

**`_COARSE_ALIASES` (42개 별칭)**:
- LLM이 대분류 수준 용어를 fine으로 반환할 때 직접 coarse로 변환
- 예: "에세이" → "시/에세이", "소설" → "소설", "프로그래밍" → "컴퓨터/IT"

---

### 5-10. CLOVA LLM Client — LLM API 래퍼

**파일**: `app/modules/llm/clova_client.py`

#### 역할

CLOVA Studio API를 OpenAI 호환 엔드포인트로 호출하는 래퍼.  
나중에 다른 모델로 교체할 때 이 파일만 수정하면 된다.

#### 제공 함수

**`chat_complete()`**

```python
async def chat_complete(
    system_prompt : str,
    messages      : list[dict],
    temperature   : float = 0.3,
    max_tokens    : int | None = 512,  # None이면 파라미터 자체 생략 (HCX-007 호환)
    model         : str | None = None,
) -> str
```

**`chat_complete_json()`**

```python
async def chat_complete_json(
    system_prompt : str,
    messages      : list[dict],
    max_retries   : int = 2,   # JSON 파싱 실패 시 재시도 횟수
    model         : str | None = None,
    **kwargs
) -> dict
```

- `_clean_json_response()`: LLM 응답에서 ````json` 코드블록 제거 + 인라인 주석(`// ...`) 제거
- `max_retries=2`: 빈 응답 또는 JSON 파싱 실패 시 최대 2회 재시도
- `AsyncOpenAI`: FastAPI 비동기 서버에서 대기 중 다른 요청 처리 가능

#### 에러 처리

| 에러 | 처리 |
|------|------|
| AuthenticationError | LLMCallError("API 키 오류") |
| APITimeoutError | LLMCallError("45초 타임아웃") |
| APIError | LLMCallError("API 오류, status 코드 포함") |
| JSONDecodeError | IntentParseError → max_retries만큼 재시도 |

---

### 5-11. Prompts — LLM 프롬프트 모음

| 파일 | 프롬프트 | 사용 모델 | 역할 |
|------|---------|-----------|------|
| `prompts/extraction.py` | `SLOT_EXTRACTION_SYSTEM_PROMPT` | HCX-DASH-002 | 슬롯 추출 시스템 프롬프트 |
| `prompts/extraction.py` | `build_slot_extraction_messages()` | — | Signal 힌트 + Anchor 힌트 포함한 메시지 구성 |
| `prompts/clarification.py` | `SUFFICIENCY_JUDGMENT_PROMPT` | HCX-007 | 충분도 판단 프롬프트 |
| `prompts/clarification.py` | `build_sufficiency_messages()` | — | 슬롯 상태 전달 메시지 구성 |
| `prompts/rag.py` | `RAG_QUERY_GENERATION_PROMPT` | HCX-DASH-002 | RAG 쿼리 생성 프롬프트 |
| `prompts/question_generation.py` | `build_detail_question_messages()` | HCX-007 | topic_subject 세부 질문 생성 |
| `prompts/question_generation.py` | `build_topic_category_messages()` | HCX-007 | topic 카테고리 질문 생성 |
| `prompts/slot.py` | `build_question_generation_messages()` | HCX-007 | 복수 슬롯 질문 생성 fallback |

#### `build_slot_extraction_messages()` — 핵심 프롬프트 구성

```python
def build_slot_extraction_messages(
    query         : str,
    history       : list[dict],
    current_slots : dict,
    signal_result = None,   # SignalResult → importance 힌트
    anchor_hint   = None,   # AnchorCandidate → 앵커 힌트 (confidence >= 0.55 시 주입)
) -> list[dict]:
```

**anchor_hint 주입 예시** (confidence >= 0.55):
```
[앵커 추출 힌트]
- 비교 표현 '처럼' 감지 → anchor가 존재할 가능성 높음
- 후보: "채식주의자" (추정 타입: 책 제목)
- 위 후보가 실제 책 제목이나 저자명이면 anchor로 추출하세요.
  후보가 불완전하거나 아닌 것 같으면 발화 전체에서 올바른 anchor를 찾으세요.
```

#### 충분도 판단 프롬프트 (`SUFFICIENCY_JUDGMENT_PROMPT`) 출력 형식

```json
{
  "rag_ready"    : false,
  "confidence"   : 85,
  "slots_to_ask" : ["topic_subject"],
  "slot_revisions": {},
  "question"     : "어떤 분야의 소설을 찾으시나요?",
  "choices"      : [
    {"label": "한국 소설", "slots": {"topic_subject": "한국소설"}},
    {"label": "외국 소설", "slots": {"topic_subject": "외국소설"}}
  ],
  "reasoning"    : "topic이 '소설'로만 채워져 있어 세부 방향이 불명확합니다."
}
```

---

## 6. LLM 모델 사용 전략

| 용도 | 모델 | temperature | max_tokens | 이유 |
|------|------|-------------|-----------|------|
| 슬롯 추출 (extraction.py) | HCX-DASH-002 | 0.0 | 900 | JSON 일관성 최우선, 저지연 |
| RAG 쿼리 생성 (rag.py) | HCX-DASH-002 | 0.2 | 300 | 창의적 쿼리 필요, 일관성 유지 |
| 충분도 판단 (clarification.py) | HCX-007 | 0.1 | 생략 | 고성능 판단 필요, HCX-007은 max_tokens 미지원 |
| topic 카테고리 질문 | HCX-007 | 0.3 | 생략 | 자연스러운 질문 생성 |
| 세부 질문 생성 | HCX-007 | 0.4 | 생략 | 다양한 선택지 생성 |
| 복수 슬롯 질문 fallback | HCX-007 | 0.4 | 생략 | — |

**temperature=0.0 선택 이유** (슬롯 추출):
- LLM이 슬롯 값을 임의로 다르게 출력하면 Enum 파싱 실패 발생
- 동일 입력 → 동일 출력 보장으로 JSON 파싱 안정성 최우선

**HCX-007 max_tokens 생략 이유**:
- HCX-007은 `max_tokens` 파라미터를 지원하지 않음 → `None` 전달 시 파라미터 자체를 API 호출에서 제외

---

## 7. 슬롯 채움 정책 및 우선순위 결정

### 슬롯 잠금 정책

```
direct   → 잠금: 멀티턴에서 덮어쓰기 금지
inferred → 열림: 더 나은 정보로 업데이트 가능
ambiguous→ 열림: 명확한 값으로 교체 가능
null     → 열림: 채움 대기 상태
```

예외: `is_refinement=True` + 새 값도 `direct` → 잠금 해제 (사용자 명시적 수정)

### purpose 질문 생략 조건 (`_SKIP_PURPOSE_COARSE`)

목적이 카테고리에서 자명한 경우 purpose 질문 불필요:
- **재미/힐링 전제**: 소설, 시/에세이, 만화
- **실용 전제**: 여행, 요리, 가정/육아, 취미/실용/스포츠
- **학습 전제**: 외국어, 취업/수험서, 대학교재, 참고서

### STILL_BROAD_FINES — 의미상 여전히 대분류 수준인 중분류

```
"장르소설", "세계문학전집", "인문학일반", "역사일반",
"경제일반", "자기계발", "교양과학" 등
```

이 값이 topic.fine에 있으면 `topic_subject`를 강제 질문한다.  
(topic이 채워진 것처럼 보이지만 실제 검색에 방향이 없으므로)

### 슬롯 조합 묶기 (`_group_slots`)

같은 우선순위 슬롯은 한 질문으로 묶는다:
- `(purpose, reading_level)` 조합 가능
- `(topic, purpose)` 조합 가능
- 그 외에는 1순위만 단독 질문 (한 번에 너무 많으면 사용자 부담)

---

## 8. 멀티턴 대화 흐름

```
턴 1: "소설 추천해줘"
  → topic=소설(direct), purpose/reading_level null
  → get_slots_to_ask → ["purpose"] (소설은 purpose 질문 생략 대상 외, coarse=소설 → skip!)
  → 실제: 소설은 _SKIP_PURPOSE_COARSE → purpose 질문 생략
  → "어떤 소설을 찾으세요?" (topic_subject) 또는 개인화 체크인

턴 2: "한국 소설이요"
  → topic.subject=["한국 소설"](direct) 추가
  → rag_ready=true → RAG 실행

------

턴 1: "지쳐서요"
  → mood=부정_소진(direct), topic/purpose null
  → CAT1_NEGATIVE → purpose importance=HIGH, topic importance=LOW
  → "어떤 책이 도움이 될까요?" + 목적 선택지

턴 2: (버튼) "위로받고 싶어요"
  → purpose=재미(direct) apply_choice
  → rag_ready=true → RAG 실행
```

### inferred 확인 턴

```
"SF 좋아해요"
  → topic=SF(direct), purpose=재미(inferred) [SF → 재미 추론]
  → uncertainty LOW → inferred 확인 턴 발동
  → "이렇게 파악했어요: 목적: 재미 / 맞아요? / 바꿀게요"
  → confirm=True → direct 격상 → RAG
  → confirm=False → purpose 재질문
```

---

## 9. 온보딩 데이터 연동

**파일**: `user_metadata.json` (데모), DB (실서비스)

**온보딩 데이터 구조**:
```json
{
  "user_id"             : "P001-A",
  "preferred_categories": [{"main": "소설", "sub": "한국소설"}],
  "preferred_length"    : "300p 이내",
  "disliked_keywords"   : ["dark", "tense"],
  "frequent_libraries"  : ["마포구립서강도서관"],
  "recent_liked_books"  : [{"title": "채식주의자"}, ...],
  "age"                 : 28,
  "region"              : "서울 마포구"
}
```

**활용 위치**:

| 위치 | 활용 방법 |
|------|-----------|
| `_needs_personalization_turn()` | preferred_categories로 mood 체크인 타이밍 결정 |
| `_profile_covers_request()` | recent_liked_books로 RAG override 결정 |
| `_generate_location_question()` | frequent_libraries로 선택지 구성 |
| `_build_onboarding_signals()` | uncertainty HIGH 슬롯에 보조 신호 추가 |
| `_anchors_to_list()` | topic null + recent_liked_books를 anchor로 추가 |

---

## 10. 설계 시 주요 고려사항 및 Trade-off

### 10-1. Stateless vs Stateful

**선택**: Stateless (컨텍스트를 프론트에서 매 요청마다 전달)

**이유**: 데모 환경에서 Redis 등 세션 저장소 없이 동작, 수평 확장 용이  
**Trade-off**: 응답 페이로드가 크고, 프론트가 컨텍스트를 안전하게 보관해야 함

### 10-2. 코드 기반 감지 vs LLM 단독

**선택**: 코드(정규식 + 형태소) 먼저, LLM은 "확인" 역할

**이유**:
- LLM 단독으로 한국어 책 제목 앵커 감지 시 ~75-80% 천장 존재
- "채식주의자" 같은 일반 명사형 책 제목을 LLM이 앵커로 인식 못하는 경우
- 코드 힌트 → LLM 확인 구조로 성능 향상

**Trade-off**: 정규식 패턴 유지 필요, 새 패턴 추가 시 코드 수정 필요

### 10-3. HCX-DASH-002 vs HCX-007

**선택**: 슬롯 추출은 DASH-002, 충분도 판단·질문 생성은 HCX-007

**이유**:
- 슬롯 추출: 정해진 형식의 JSON 출력 → 성능보다 속도/일관성 중요 → DASH-002
- 충분도 판단·질문 생성: 맥락 종합 판단 + 자연스러운 질문 → 고성능 HCX-007

### 10-4. temperature 선택

| 상황 | 선택 | 이유 |
|------|------|------|
| 슬롯 추출 (JSON) | 0.0 | Enum 파싱 실패 방지, 동일 입력 → 동일 출력 |
| RAG 쿼리 생성 | 0.2 | 약간의 다양성으로 키워드 풍부화 |
| 충분도 판단 | 0.1 | 판단의 일관성 유지, 약간의 유연성 |
| 질문 생성 | 0.3~0.4 | 자연스럽고 다양한 질문/선택지 |

### 10-5. 슬롯 채움 순서 / 우선순위

**원칙**: 추천 실패를 가장 크게 줄이는 슬롯을 먼저 질문

```
topic 없음 → 방향 없음 → 최우선
comparison_basis 없음 + anchor 있음 → 비교 기준 불명확 → 높은 우선순위
reading_level → topic 카테고리마다 중요도 다름 (기술/학습 계열 > 소설)
purpose → 일부 카테고리는 자명 (소설 → "재미" 전제) → 생략 가능
```

### 10-6. anchor 처리

**원칙**: 앵커는 슬롯이 아님 → 비어있어도 세션 질문으로 채우지 않음

**이유**: 사용자가 "채식주의자 같은 책" 이라고 했을 때 anchor를 다시 물어보는 건 UX에서 어색함.  
anchor 없이 comparison_basis가 생기면 → 사후 검증에서 comparison_basis 초기화.

---

## 11. 환경 변수 & 실행 방법

### 필수 환경 변수 (`.env`)

```env
CLOVA_API_KEY=...         # CLOVA Studio API 키
CLOVA_BASE_URL=...        # CLOVA Studio OpenAI 호환 엔드포인트
CLOVA_MODEL=HCX-DASH-002  # 기본 LLM 모델
```

### 선택 환경 변수

```env
NARU_API_KEY=...          # 정보나루 API 키 (대출 가능 여부 조회용)
NARU_LIB_CODE=...         # 도서관 코드
AWS_PUBLIC_IP=...         # 배포 시 공개 IP
LOG_LEVEL=INFO            # 로그 레벨
```

### 실행 방법

```bash
# conda 환경 활성화 후 backend 폴더에서
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### API 문서 확인

```
Swagger UI : http://localhost:8000/docs
ReDoc      : http://localhost:8000/redoc
헬스 체크  : http://localhost:8000/api/health
```

---

## 부록: 파일 구조 요약

```
backend/
├── app/
│   ├── main.py                          # FastAPI 진입점
│   ├── api/
│   │   └── routes/
│   │       ├── chat.py                  # POST /api/chat
│   │       ├── auth.py                  # 인증
│   │       ├── profile.py               # 프로파일
│   │       ├── onboarding.py            # 온보딩
│   │       └── eval.py                  # 평가/로그
│   ├── services/
│   │   ├── chat_service.py              # 파이프라인 오케스트레이터
│   │   ├── pipeline.py                  # BM25→Reranker→대출가능 파이프라인
│   │   └── loan_availability.py         # 정보나루 API 대출 가능 조회
│   ├── modules/
│   │   ├── llm/
│   │   │   ├── clova_client.py          # CLOVA Studio LLM 클라이언트
│   │   │   ├── category_mapper.py       # 카테고리 정규화
│   │   │   └── category_tree.json       # 대분류 → 중분류 트리
│   │   ├── signal/
│   │   │   ├── detector.py              # Kiwi 기반 신호 감지
│   │   │   └── expressions.py           # 카테고리별 표현 사전
│   │   ├── slot/
│   │   │   ├── schema.py                # 슬롯 스키마 (SessionContext 등)
│   │   │   ├── filler.py                # LLM 슬롯 추출 + 우선순위 결정
│   │   │   ├── anchor_extractor.py      # 정규식 앵커 사전 추출
│   │   │   ├── question_generator.py    # 세션 질문 생성
│   │   │   └── rag_query_builder.py     # RAG 쿼리 생성
│   │   ├── RAG/
│   │   │   ├── retriever.py             # BM25 검색
│   │   │   └── anchor_book_pipeline.py  # anchor 기반 쿼리 재작성
│   │   └── reranker/
│   │       └── clova_reranker.py        # CLOVA Reranker
│   ├── prompts/
│   │   ├── extraction.py                # 슬롯 추출 프롬프트
│   │   ├── clarification.py             # 충분도 판단 프롬프트
│   │   ├── rag.py                       # RAG 쿼리 생성 프롬프트
│   │   ├── question_generation.py       # 질문 생성 프롬프트
│   │   └── slot.py                      # 질문 생성 fallback 프롬프트
│   ├── schemas/
│   │   └── chat_schema.py               # ChatRequest / SlotChatResponse
│   ├── core/
│   │   ├── config.py                    # 환경 변수 로드
│   │   ├── exceptions.py                # 커스텀 예외
│   │   └── session_logger.py            # 세션 로그
│   └── db/
│       ├── database.py                  # SQLAlchemy 설정
│       └── create_db.py                 # DB 초기화
└── BACKEND_ARCHITECTURE.md             # 이 문서
```

---

*최종 업데이트: 2026-05-22 (슬롯 설계 섹션 추가)*  
*작성 기준 브랜치: `feat/moduler`*
