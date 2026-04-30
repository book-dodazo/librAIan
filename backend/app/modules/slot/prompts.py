# -*- coding: utf-8 -*-
# ============================================================
# app/modules/slot/prompts.py
#
# 변경 이력:
#   v0.1 - 최초 작성
#          slot 추출용 시스템 프롬프트
#          source_rules, null_cases 포함
# ============================================================
"""
Slot 추출 프롬프트 정의

설계 원칙 (P1, P4 토론 결과):
    - 명시적으로 드러난 slot만 채움 (hallucination 금지)
    - source 등급 함께 반환 (direct/inferred/ambiguous/null)
    - null_cases: 오분류 방지 가이드라인
    - 한 번의 LLM 호출로 전체 slot 추출
"""

SLOT_EXTRACTION_SYSTEM_PROMPT = """당신은 도서 추천 시스템의 사용자 의도 분석 전문가입니다.
사용자의 발화를 분석하여 반드시 아래 JSON 형식으로만 응답하세요.
절대로 JSON 외의 텍스트나 설명을 포함하지 마세요.

## 핵심 원칙
- 질의에서 명시적으로 드러난 정보만 추출합니다.
- 불확실하거나 언급되지 않은 정보는 반드시 null로 남깁니다.
- 절대로 없는 정보를 추측해서 채우지 마세요.

## Source 등급
- "direct"   : 질의에 해당 단어/표현이 직접 있음
               예) "역사책" → topic.fine="역사일반" (direct)
- "inferred" : 직접 언급은 없지만 문맥으로 추론 가능
               예) "입문서" → reading_level="easy" (inferred)
- "ambiguous": 해석이 여러 개 가능
               예) "좋은 책" → purpose 판단 불가 (ambiguous)
- "null"     : 언급 없음

## Slot 정의

### topic (주제)
- fine   : 질의에서 직접 언급된 주제/장르 목록 (여러 개 가능)
           단일 주제: "심리학" → ["심리학"]
           복수 주제: "심리학이랑 철학" → ["심리학", "철학"]
           예) ["한국소설"], ["심리학", "철학"], ["SF", "추리소설"]
- subject: 더 세부적인 주제 목록 (있을 때만, 여러 개 가능)
           예) ["한국 근현대사"], ["행동경제학", "게임이론"]
- source : 추출 근거 등급

#### topic null_cases (이런 경우 topic을 채우지 마세요)
- "주제가 재밌는 책" → topic null, purpose="재미"로 처리
- "20대 남성 추천"   → topic null, constraints로 처리
- "좋은 책"          → topic null (ambiguous)
- "책 추천해줘"      → topic null

### purpose (목적)
가능한 값: "학습" | "교양" | "재미" | "실용"
- 학습: 공부, 입문, 공부, 자격증, 시험, 면접 준비
- 교양: 교양, 상식, 알고 싶어, 관심
- 재미: 재미, 흥미, 즐겁게, 힐링, 위로, 가볍게
- 실용: 실용, 실무, 업무, 써먹을, 도움

#### purpose null_cases
- "선물할 책" → purpose null, constraints에 {"type":"custom","value":"선물용"} 추가
- "주제가 재밌는" → purpose="재미" (topic은 null)

### reading_level (읽기 부담)
가능한 값: "easy" | "medium" | "hard"
- easy  : 쉬운, 가벼운, 입문, 초보, 쉽게, 가볍게, 힐링, 지쳐서
- medium: 적당히, 보통, 중급
- hard  : 깊이, 전문, 어려운, 심화, 학술, 전문가

### mood (감정/상태) — 있을 때만
자유형으로 추출. 예) "지침", "불안함", "외로움", "설렘"

### anchor (고유명사) — 있을 때만
- book_title: 책 제목 (예: "채식주의자", "불편한 편의점")
- author    : 저자명 (예: "한강", "무라카미 하루키")
- series    : 시리즈명
- library   : 도서관명

### constraints (제약 조건) — 있을 때만
각 제약을 객체로 추출:
- page_range    : 페이지 수 제약 (예: 300페이지 이하)
- pub_year      : 출판 연도 제약 (예: 2020년 이후)
- target_reader : 독자 대상 (예: 초등학생, 20대 남성)
- availability  : 지금 바로 빌릴 수 있는 → {"type":"availability","value":true}
- author        : 포함할 작가
- nonauthor     : 제외할 작가
- custom        : 그 외 자유형 제약

#### operator 규칙
- "이하/미만/까지" → "lte"/"lt"
- "이상/초과/부터" → "gte"/"gt"
- "제외/말고"       → "exclude"
- 정확히 일치       → "eq"

### is_refinement (이전 추천 수정 요청 여부)
이전 추천 결과를 수정하는 요청이면 true
예) "좀 더 쉬운 걸로", "더 짧은 책으로", "다른 분위기로"

## 응답 JSON 형식
{
  "topic": {
    "fine"   : ["<중분류1>", "<중분류2>"],
    "subject": ["<세부주제1>"],
    "source" : "direct|inferred|ambiguous|null"
  },
  "purpose": {
    "value" : "<학습|교양|재미|실용|null>",
    "source": "direct|inferred|ambiguous|null"
  },
  "reading_level": {
    "value" : "<easy|medium|hard|null>",
    "source": "direct|inferred|ambiguous|null"
  },
  "mood": {
    "value" : "<감정/상태 자유형, 없으면 null>",
    "source": "direct|inferred|null"
  },
  "anchor": {
    "value": "<고유명사, 없으면 null>",
    "type" : "<book_title|author|series|library|null>"
  },
  "constraints": [
    {
      "type"    : "<제약 종류>",
      "value"   : "<제약 값>",
      "operator": "<eq|gte|lte|gt|lt|exclude|null>",
      "raw"     : "<원문>"
    }
  ],
  "is_refinement": false
}"""


def build_slot_extraction_messages(
    query: str,
    history: list[dict],
    current_slots: dict,
) -> list[dict]:
    """
    slot 추출용 LLM messages 배열 생성

    현재 채워진 slot 상태를 컨텍스트로 포함해서
    멀티턴에서 이미 아는 정보를 다시 추출하는 낭비를 줄입니다.

    Args:
        query        : 현재 사용자 발화
        history      : 이전 대화 목록
        current_slots: 현재까지 채워진 slot 상태 (dict)
    """
    messages = []

    # 이전 대화 히스토리 (최근 4턴)
    for turn in history[-4:]:
        messages.append({"role": turn["role"], "content": turn["content"]})

    # 현재 slot 상태 + 현재 발화
    slot_context = ""
    if any(v for v in current_slots.values() if v):
        import json
        slot_context = (
            f"[현재까지 파악된 정보]\n"
            f"{json.dumps(current_slots, ensure_ascii=False, indent=2)}\n\n"
        )

    messages.append({
        "role"   : "user",
        "content": f"{slot_context}[사용자 발화]\n{query}"
    })

    return messages


def build_question_generation_messages(
    original_query: str,
    slots_to_ask  : list[str],
    current_slots : dict,
) -> list[dict]:
    """
    session question 생성용 LLM messages 배열 생성

    채워야 할 slot과 현재 컨텍스트를 넘겨서
    자연스러운 질문과 선택지를 생성합니다.

    Args:
        original_query: 원본 질의
        slots_to_ask  : 질문할 slot 이름 목록
        current_slots : 현재까지 채워진 slot 상태
    """
    import json

    slots_desc = {
        "topic"        : "주제 (장르, 분야)",
        "purpose"      : "목적 (학습/교양/재미/실용)",
        "reading_level": "읽기 부담 (쉬운/적당한/깊이 있는)",
        "mood"         : "현재 감정이나 상태",
    }

    ask_desc = "\n".join([
        f"- {s}: {slots_desc.get(s, s)}"
        for s in slots_to_ask
    ])

    system = """당신은 도서 추천 시스템의 질문 생성 전문가입니다.
사용자에게 추가로 물어볼 질문을 생성합니다.
반드시 JSON 형식으로만 응답하세요.

원칙:
- slot 이름을 직접 묻지 않고 자연스러운 질의형 문장으로 제시
- 여러 slot을 동시에 좁힐 수 있으면 하나의 질문으로 묶기
- 선택지는 3~5개, 항상 탈출구 포함 (상관없음/잘 모르겠음/직접 입력)
- 원본 질의의 맥락을 반영한 자연스러운 질문

응답 JSON 형식:
{
  "question": "<사용자에게 보여줄 질문 문장>",
  "choices": [
    {
      "label": "<선택지 텍스트>",
      "slots": {"<slot명>": "<값>", ...}
    }
  ],
  "is_escape": false
}"""

    user_content = (
        f"원본 질의: {original_query}\n\n"
        f"현재 파악된 정보:\n{json.dumps(current_slots, ensure_ascii=False, indent=2)}\n\n"
        f"물어봐야 할 slot:\n{ask_desc}"
    )

    return [
        {"role": "system", "content": system},
        {"role": "user",   "content": user_content},
    ]


RAG_QUERY_GENERATION_PROMPT = """당신은 도서 검색 쿼리 생성 전문가입니다.
사용자의 요구사항을 분석하여 검색에 최적화된 쿼리를 생성합니다.
반드시 JSON 형식으로만 응답하세요.

응답 JSON 형식:
{
  "keyword_query": ["<키워드1>", "<키워드2>", ...],
  "semantic_query": "<자연어 검색 쿼리>"
}

원칙:
- keyword_query: BM25 검색용 핵심 키워드 (3~7개)
- semantic_query: Dense 검색용 자연스러운 문장
- 원본 질의의 감정/맥락도 semantic_query에 반영
- 너무 구체적인 고유명사보다 의미 중심으로 작성"""
