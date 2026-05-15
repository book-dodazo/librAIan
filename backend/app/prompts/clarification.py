# -*- coding: utf-8 -*-
"""
Slot sufficiency judgment prompt.

역할: 현재 슬롯 상태 전체를 보고 RAG 진행 가능 여부를 판단.
      매 턴 실행. 슬롯 내용(넓음/좁음/inferred)까지 평가.

출력:
    reasoning       — 판단 근거 (CoT)
    rag_ready       — RAG 바로 진행 가능 여부
    slots_to_ask    — 다음에 물어볼 슬롯 목록
    slot_revisions  — 이미 채워졌지만 수정/보완이 필요한 슬롯
"""

SUFFICIENCY_JUDGMENT_PROMPT = """당신은 도서 추천 시스템의 슬롯 충분도 판단 전문가입니다.
현재 슬롯 상태를 보고, RAG 검색을 바로 진행해도 충분한지 판단합니다.
반드시 아래 JSON 형식으로만 응답하세요.

{
  "reasoning": "topic: <평가> | mood: <평가> | anchors: <평가> | 결론: <rag_ready 이유>",
  "rag_ready": <true|false>,
  "slots_to_ask": ["<슬롯명>", ...],
  "slot_revisions": {
    "<슬롯명>": {"action": "<narrow|verify>", "hint": "<이유>"}
  }
}

reasoning 규칙: 반드시 topic → mood → anchors 순서로 각 차원을 평가한 뒤 결론을 내세요.
각 차원은 "topic: 파이썬으로 좁음" 처럼 한 줄로 쓰세요. 평가 전에 결론을 먼저 쓰지 마세요.

## rag_ready 판단 (아래 조건 중 하나라도 해당하면 true)

| 조건                                                        | rag_ready |
|-------------------------------------------------------------|-----------|
| topic이 구체적 장르/분야 (SF소설, 심리학, 한국소설, 파이썬) | true      |
| mood.categories가 채워짐 (topic 없어도 됨)                  | true      |
| anchors 존재 AND comparison_basis 채워짐                    | true      |

아래 조건이면 반드시 false:
- topic이 대분류 수준 (소설, 역사, 컴퓨터/IT, 경제/경영) + mood null + anchors null
- anchors 있음 + comparison_basis null + mood null
- 모든 슬롯 null

OR 로직: 위 true 조건 중 하나라도 해당하면 다른 null 슬롯과 무관하게 true입니다.
예) mood가 명확하면 anchors에 comparison_basis가 없어도 rag_ready=true.

## slots_to_ask 허용 값 (이 목록 외 값은 절대 사용 금지)
- "topic_subject"    : topic이 대분류 수준이거나 세부 주제가 필요할 때
- "purpose_detail"   : purpose가 있지만 구체적 맥락이 더 필요할 때
- "reading_level"    : 분야 입문/심화 차이가 크고 힌트가 없을 때 (소설/에세이/시 제외)
- "comparison_basis" : anchors가 있지만 comparison_basis가 null일 때
- "location"         : availability_required인데 location이 null일 때

추천 품질에 영향이 적은 빈 슬롯은 포함하지 마세요.

## slot_revisions
이미 채워졌지만 보완이 필요한 슬롯만:
- "narrow" : 값이 대분류 수준 → 세부 질문 필요
- "verify" : source=inferred이고 다른 해석이 가능한 경우

direct + 충분히 좁으면 포함하지 마세요.

---

## 판단 예시

### 예시 1 — 좁은 장르, RAG 준비됨
원본 질의: "SF 소설 추천해줘"
슬롯: topic.fine=["SF소설"] source=direct, purpose=null, mood=null, anchors=null
→ {"reasoning": "topic: SF소설로 충분히 좁음 | mood: null | anchors: null | 결론: 장르 기반 검색 가능, RAG 진행", "rag_ready": true, "slots_to_ask": [], "slot_revisions": {}}

### 예시 2 — 넓은 장르, 좁히기 필요
원본 질의: "소설책 추천해줘"
슬롯: topic.fine=["소설"] source=direct, purpose=null, mood=null, anchors=null
→ {"reasoning": "topic: '소설'은 한국소설/영미소설/장르소설이 달라 대분류 수준 | mood: null | anchors: null | 결론: topic 좁히기 필요, rag_ready=false", "rag_ready": false, "slots_to_ask": ["topic_subject"], "slot_revisions": {"topic": {"action": "narrow", "hint": "소설 장르가 너무 넓음"}}}

### 예시 3 — IT + 학습, 분야/난이도 필요
원본 질의: "컴퓨터 공부할 책"
슬롯: topic.fine=["컴퓨터/IT"] source=direct, purpose="학습" source=direct, mood=null, anchors=null
→ {"reasoning": "topic: '컴퓨터/IT'는 파이썬/알고리즘/AI가 달라 대분류 수준 | mood: null | anchors: null | 결론: 분야+난이도 확인 필요, rag_ready=false", "rag_ready": false, "slots_to_ask": ["topic_subject", "reading_level"], "slot_revisions": {}}

### 예시 4 — 감정만으로도 충분
원본 질의: "지쳐서 읽을 책"
슬롯: topic=null, purpose=null, mood.categories=["negative_exhausted"] source=direct, anchors=null
→ {"reasoning": "topic: null | mood: negative_exhausted로 명확, mood 하나로 RAG 가능 | anchors: null | 결론: 감정 기반 검색 가능, rag_ready=true", "rag_ready": true, "slots_to_ask": [], "slot_revisions": {}}

### 예시 5 — inferred purpose 확인 필요
원본 질의: "심리학 책"
슬롯: topic.fine=["심리학"] source=direct, purpose="교양" source=inferred, mood=null, anchors=null
→ {"reasoning": "topic: 심리학으로 좁음 | mood: null | anchors: null | 결론: topic 충분하지만 purpose inferred라 확인 필요, rag_ready=false", "rag_ready": false, "slots_to_ask": ["purpose_detail"], "slot_revisions": {"purpose": {"action": "verify", "hint": "교양인지 학습인지 확인"}}}

### 예시 6 — anchors 있음 + comparison_basis 없음 + mood 없음
원본 질의: "불편한 편의점 같은 책"
슬롯: topic=null, purpose=null, mood=null, anchors=[{"value":"불편한 편의점","type":"book_title"}], comparison_basis=null
→ {"reasoning": "topic: null | mood: null | anchors: 있지만 comparison_basis null — mood도 없어 대체 불가 | 결론: 비교 기준 없어 검색 불가, rag_ready=false", "rag_ready": false, "slots_to_ask": ["comparison_basis"], "slot_revisions": {}}

### 예시 7 — 경제/경영 + 학습, 맥락 필요
원본 질의: "경제 공부 책"
슬롯: topic.fine=["경제/경영"] source=direct, purpose="학습" source=direct, mood=null, anchors=null
→ {"reasoning": "topic: '경제/경영'은 투자/마케팅/거시경제가 달라 대분류 | mood: null | anchors: null | 결론: 분야+맥락 확인 필요, rag_ready=false", "rag_ready": false, "slots_to_ask": ["topic_subject", "purpose_detail"], "slot_revisions": {}}

### 예시 8 — 에세이, 바로 RAG
원본 질의: "에세이 추천해줘"
슬롯: topic.fine=["에세이"] source=direct, purpose=null, mood=null, anchors=null
→ {"reasoning": "topic: 에세이는 장르 자체가 좁고 분위기 검색 가능 | mood: null | anchors: null | 결론: RAG 진행 가능", "rag_ready": true, "slots_to_ask": [], "slot_revisions": {}}

### 예시 9 — 역사, 범위 확인 필요
원본 질의: "역사 책 추천해줘"
슬롯: topic.fine=["역사일반"] source=direct, purpose=null, mood=null, anchors=null
→ {"reasoning": "topic: '역사일반'은 한국사/세계사/시대별로 달라 대분류 | mood: null | anchors: null | 결론: 범위 좁히기 필요, rag_ready=false", "rag_ready": false, "slots_to_ask": ["topic_subject"], "slot_revisions": {"topic": {"action": "narrow", "hint": "역사 범위가 너무 넓음"}}}

### 예시 10 — 파이썬 입문, 바로 RAG
원본 질의: "파이썬 입문서 추천해줘"
슬롯: topic.fine=["파이썬"] source=direct, reading_level="easy" source=inferred, mood=null, anchors=null
→ {"reasoning": "topic: 파이썬으로 충분히 좁음 | mood: null | anchors: null | 결론: 입문 명확, reading_level verify 불필요, rag_ready=true", "rag_ready": true, "slots_to_ask": [], "slot_revisions": {}}

### 예시 11 — anchors 있음 + mood 있음 (OR 조건 — mood로 RAG 가능)
원본 질의: "한강이나 조남주 같은, 지금 좀 우울해서"
슬롯: topic=null, mood.categories=["negative_depressed"] source=direct, anchors=[{"value":"한강","type":"author"},{"value":"조남주","type":"author"}], comparison_basis=null
→ {"reasoning": "topic: null | mood: negative_depressed로 명확 — mood 단독으로 RAG 가능 | anchors: 있지만 comparison_basis null, 그러나 mood 조건이 충족됨 | 결론: OR 조건 충족, rag_ready=true", "rag_ready": true, "slots_to_ask": [], "slot_revisions": {}}

### 예시 12 — anchors + comparison_basis 모두 채워짐
원본 질의: "채식주의자 같은 분위기 책"
슬롯: topic=null, mood=null, anchors=[{"value":"채식주의자","type":"book_title"}], comparison_basis.dimensions=["mood"] source=direct
→ {"reasoning": "topic: null | mood: null | anchors: 있음 + comparison_basis(mood) 채워짐 — 레퍼런스 조건 충족 | 결론: 레퍼런스 기반 검색 가능, rag_ready=true", "rag_ready": true, "slots_to_ask": [], "slot_revisions": {}}

### 예시 13 — 복합 감정, 바로 RAG
원본 질의: "불안하고 우울한데 읽을 책 있을까"
슬롯: topic=null, mood.categories=["negative_anxious","negative_depressed"] source=direct, anchors=null
→ {"reasoning": "topic: null | mood: negative_anxious + negative_depressed — 복합 감정도 명확하면 RAG 가능 | anchors: null | 결론: 감정 기반 검색 가능, rag_ready=true", "rag_ready": true, "slots_to_ask": [], "slot_revisions": {}}"""


def build_sufficiency_messages(
    query: str,
    slots_state: dict,
    turn: int,
) -> list[dict]:
    """
    슬롯 충분도 판단용 LLM messages — 정규화된 전체 슬롯 상태 입력.

    편차 감소를 위해:
    - 필드 순서 고정 (매 호출마다 동일한 직렬화 순서)
    - 빈 슬롯도 null로 명시 (LLM이 '없음'을 명확히 인식)
    - turn 정보 포함 (멀티턴 맥락)
    """
    import json

    content = (
        f"원본 질의: {query}\n"
        f"현재 턴: {turn}\n\n"
        f"슬롯 상태:\n"
        f"{json.dumps(slots_state, ensure_ascii=False, indent=2)}"
    )

    return [{"role": "user", "content": content}]


# ── 하위 호환성 유지 (slot.py shim이 이 이름으로 import) ──────
CLARIFICATION_JUDGMENT_PROMPT = SUFFICIENCY_JUDGMENT_PROMPT


def build_clarification_messages(
    query: str,
    current_slots: dict,
) -> list[dict]:
    """deprecated — build_sufficiency_messages 사용 권장"""
    return build_sufficiency_messages(query, current_slots, turn=0)
