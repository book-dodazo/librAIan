# -*- coding: utf-8 -*-
# ============================================================
# app/modules/llm/prompts.py
#
# 변경 이력:
#   v0.1 - 최초 작성
#   v0.2 - 히스토리 최근 6턴 → 4턴으로 축소
#           (HCX-DASH-002 컨텍스트 절약, 데모 환경 토큰 비용 절감)
# ============================================================
"""
M1 모듈 프롬프트 정의

비즈니스 로직(intent_extractor.py) 과 프롬프트 문자열을 분리하는 이유:
    - 프롬프트만 따로 버전 관리 & A/B 테스트 가능
    - Python 코드 몰라도 프롬프트 수정 가능
    - 프롬프트 변경이 로직 파일에 영향 없음

제공:
    INTENT_SYSTEM_PROMPT : 의도 분류 시스템 프롬프트
    build_intent_messages: LLM 에 넘길 messages 배열 생성 함수
"""

# ── 시스템 프롬프트 ────────────────────────────────────────────
# 중요: 반드시 JSON 만 반환하도록 명시해야 chat_complete_json 파싱이 안정됨

INTENT_SYSTEM_PROMPT = """당신은 도서관 도서 추천 시스템의 의도 분석 전문가입니다.
사용자의 발화를 분석하여 반드시 아래 JSON 형식으로만 응답하세요.
절대로 JSON 외의 텍스트, 설명, 코드블록을 포함하지 마세요.

## 의도 유형 (intent_type)
- "book_recommendation": 책 추천을 원하는 경우
  예) "SF 소설 추천해줘", "요즘 인기 있는 책 알려줘", "심리학 입문서 추천"
- "book_info": 특정 책이나 저자에 대한 정보를 묻는 경우
  예) "채식주의자 어떤 책이야?", "한강 작가 다른 작품은?"
- "general_chat": 책과 무관한 일반 대화
  예) "안녕", "고마워", "오늘 날씨가 좋네"
- "clarification_needed": 의도가 불분명해서 추가 질문이 필요한 경우
  예) "좋은 책", "재미있는 거", "뭔가 읽고 싶어"

## 필터 추출 (filters) — 해당 정보가 있을 때만 포함
- genre  : 장르 (예: "소설", "자기계발", "역사", "과학", "에세이")
- mood   : 분위기 (예: "힐링", "긴장감", "유머", "감동")
- level  : 독자 수준 (예: "입문", "중급", "전문가")
- period : 시대/출판 시기 (예: "최신", "고전")
- purpose: 읽는 목적 (예: "학습", "취미", "선물")

## 응답 JSON 형식 (이 형식 그대로만 출력)
{
  "intent_type": "<위 4가지 중 하나>",
  "search_query": "<RAG 검색에 최적화된 한국어 쿼리, book_recommendation/book_info 일 때만>",
  "clarification_question": "<추가 질문 문장, clarification_needed 일 때만>",
  "filters": {<추출된 필터들, 없으면 빈 객체 {}>},
  "confidence": <0.0~1.0 사이 숫자>
}"""


def build_intent_messages(
    query: str,
    history: list[dict],
    user_profile: dict | None,
) -> list[dict]:
    """
    LLM 에 넘길 messages 배열을 생성합니다.

    구성:
        [최근 대화 히스토리 (최대 4턴)] + [현재 사용자 발화]

    user_profile 이 있으면 발화 앞에 컨텍스트로 추가합니다.

    Args:
        query       : 현재 사용자 발화
        history     : 이전 대화 목록 [{"role": ..., "content": ...}]
        user_profile: 온보딩 선호 정보 딕셔너리 (없으면 None)

    Returns:
        messages 배열
    """
    messages = []

    # 1. 이전 대화 히스토리 (최근 4턴만 — 토큰 절약)
    # [v0.2 변경] 6턴 → 4턴: 데모 환경 토큰 비용 절감
    for turn in history[-4:]:
        messages.append({"role": turn["role"], "content": turn["content"]})

    # 2. 현재 발화 (사용자 프로필 컨텍스트 포함)
    user_content = query
    if user_profile:
        profile_lines = []
        if user_profile.get("preferred_genres"):
            genres = ", ".join(user_profile["preferred_genres"])
            profile_lines.append(f"선호 장르: {genres}")
        if user_profile.get("reading_level"):
            profile_lines.append(f"독서 수준: {user_profile['reading_level']}")
        if user_profile.get("purpose"):
            profile_lines.append(f"독서 목적: {user_profile['purpose']}")

        if profile_lines:
            profile_ctx = "[사용자 프로필]\n" + "\n".join(profile_lines)
            user_content = f"{profile_ctx}\n\n[사용자 발화]\n{query}"

    messages.append({"role": "user", "content": user_content})
    return messages
