# -*- coding: utf-8 -*-
# ============================================================
# app/modules/slot/question_generator.py
#
# 변경 이력:
#   v0.1 - 최초 작성
#          P4 토론 결과 기반 session question 생성
#   v0.2 - topic 선택지: 고정 대분류 + LLM 맥락 추가 방식으로 변경
# ============================================================
"""
Session Question 생성기

P4 결론:
    단일 slot 질문:
        질문 텍스트 → LLM이 맥락 반영해서 동적 생성
        선택지      → slot별 사전 정의 값 사용

    복수 slot 동시 질문:
        질문 텍스트 + 선택지 → LLM이 통째로 생성
        각 선택지가 어떤 slot을 채우는지 매핑 반환

    공통:
        탈출구(상관없음/잘 모르겠음/직접 입력) slot 성격에 따라 포함
"""
import logging
from typing import Any, Optional

from app.core.exceptions import IntentParseError, LLMCallError
from app.modules.llm.clova_client import chat_complete_json
from app.modules.slot.prompts import build_question_generation_messages
from app.modules.slot.schema import SessionContext

logger = logging.getLogger(__name__)


# ── 단일 slot 사전 정의 선택지 ────────────────────────────────

_PREDEFINED_CHOICES: dict[str, list[dict]] = {
    "purpose": [
        {"label": "공부·입문용으로",     "slots": {"purpose": "학습"}},
        {"label": "교양으로 읽고 싶어요", "slots": {"purpose": "교양"}},
        {"label": "재미있게 읽고 싶어요", "slots": {"purpose": "재미"}},
        {"label": "실생활에 도움되는 걸", "slots": {"purpose": "실용"}},
        {"label": "잘 모르겠어요",        "slots": {}},
    ],
    "reading_level": [
        {"label": "가볍고 쉽게 읽히는 책",      "slots": {"reading_level": "easy"}},
        {"label": "적당히 생각할 거리가 있는 책", "slots": {"reading_level": "medium"}},
        {"label": "깊이 있어도 괜찮아요",        "slots": {"reading_level": "hard"}},
        {"label": "상관없어요",                  "slots": {}},
    ],
}

# topic 고정 기저 선택지 — 항상 포함되는 자주 쓰이는 대분류
# LLM이 맥락에 따라 추가 선택지를 붙이고 마지막에 직접 입력이 붙음
_TOPIC_BASE_CHOICES: list[dict] = [
    {"label": "소설",      "slots": {"topic_fine": "소설"}},
    {"label": "인문",      "slots": {"topic_fine": "인문"}},
    {"label": "경제/경영", "slots": {"topic_fine": "경제/경영"}},
    {"label": "자기계발",  "slots": {"topic_fine": "자기계발"}},
    {"label": "과학",      "slots": {"topic_fine": "과학"}},
    {"label": "역사/문화", "slots": {"topic_fine": "역사/문화"}},
    {"label": "시/에세이", "slots": {"topic_fine": "시/에세이"}},
]

# topic 직접 입력 탈출구 (항상 마지막)
_TOPIC_ESCAPE = {"label": "직접 입력", "slots": {}}

# slot별 탈출구 정의
_ESCAPE_OPTIONS: dict[str, str] = {
    "purpose"      : "잘 모르겠어요",
    "reading_level": "상관없어요",
    "topic"        : "직접 입력",
    "mood"         : "상관없어요",
}


class SessionQuestion:
    """사용자에게 보여줄 session question"""

    def __init__(
        self,
        question: str,
        choices : list[dict[str, Any]],
        slots   : list[str],  # 이 질문이 채우려는 slot 목록
    ):
        self.question = question
        self.choices  = choices
        self.slots    = slots

    def to_dict(self) -> dict:
        return {
            "question": self.question,
            "choices" : self.choices,
            "slots"   : self.slots,
        }


async def generate_question(
    slots_to_ask  : list[str],
    context       : SessionContext,
) -> Optional[SessionQuestion]:
    """
    비어있는 slot에 대한 session question을 생성합니다.

    단일 slot이면 사전 정의 선택지 + LLM 질문 텍스트 생성
    복수 slot이면 LLM이 전부 생성

    Args:
        slots_to_ask: 질문할 slot 목록
        context     : 현재 세션 컨텍스트

    Returns:
        SessionQuestion 또는 None (생성 실패 시)
    """
    if not slots_to_ask:
        return None

    current_slots = _context_to_dict(context)

    if len(slots_to_ask) == 1:
        return await _generate_single_question(
            slot_name     = slots_to_ask[0],
            original_query= context.original_query,
            current_slots = current_slots,
        )
    else:
        return await _generate_multi_question(
            slots_to_ask  = slots_to_ask,
            original_query= context.original_query,
            current_slots = current_slots,
        )


async def _generate_single_question(
    slot_name     : str,
    original_query: str,
    current_slots : dict,
) -> Optional[SessionQuestion]:
    """
    단일 slot 질문 생성

    topic: 고정 기저 선택지 + LLM 맥락 추가 선택지 합산
    나머지: 사전 정의 선택지 + LLM 질문 텍스트
    """
    # topic은 별도 처리 (기저 + LLM 추가)
    if slot_name == "topic":
        return await _generate_topic_question(
            original_query= original_query,
            current_slots = current_slots,
        )

    predefined = _PREDEFINED_CHOICES.get(slot_name)

    if not predefined:
        # 사전 정의 없으면 LLM이 전부 생성
        return await _generate_llm_question(
            slots_to_ask  = [slot_name],
            original_query= original_query,
            current_slots = current_slots,
        )

    # 질문 텍스트만 LLM에게 요청
    question_text = await _generate_question_text(
        slot_name     = slot_name,
        original_query= original_query,
        current_slots = current_slots,
    )

    if not question_text:
        question_text = _default_question_text(slot_name)

    return SessionQuestion(
        question = question_text,
        choices  = predefined,
        slots    = [slot_name],
    )


async def _generate_topic_question(
    original_query: str,
    current_slots : dict,
) -> SessionQuestion:
    """
    topic 선택지 생성 (v0.2 — 고정 기저 + LLM 맥락 추가)

    흐름:
        1. 고정 기저 선택지 (_TOPIC_BASE_CHOICES) 로 시작
        2. LLM에게 맥락 보고 추가할 대분류 1~2개 요청
        3. 기저에 없는 것만 앞에 삽입
        4. 직접 입력 탈출구를 마지막에 추가
        5. 질문 텍스트도 LLM이 맥락 반영해서 생성
    """
    import json

    # 이미 기저에 포함된 라벨 집합
    base_labels = {c["label"] for c in _TOPIC_BASE_CHOICES}

    # LLM에게 맥락 기반 추가 선택지 + 질문 텍스트 요청
    system = """당신은 도서 추천 도우미입니다.
사용자의 질의 맥락을 보고 아래 JSON 형식으로만 응답하세요.

{
  "question": "<어떤 분야나 장르의 책을 찾는지 묻는 자연스러운 질문>",
  "extra_categories": ["<대분류명1>", "<대분류명2>"]
}

extra_categories 규칙:
- 질의 맥락에서 아래 고정 목록에 없는 관련 대분류가 있으면 1~2개만 추가
- 고정 목록: 소설, 인문, 경제/경영, 자기계발, 과학, 역사/문화, 시/에세이
- 맥락상 추가할 게 없으면 빈 배열 []
- 반드시 category_tree의 대분류명 그대로 사용
  가능한 대분류: 종교, 건강, 가정/육아, 요리, 여행, 만화, 컴퓨터/IT, 기술/공학, 외국어, 취미/실용/스포츠"""

    messages = [{
        "role": "user",
        "content": (
            f"원본 질의: {original_query}\n"
            f"현재 파악된 정보: {json.dumps(current_slots, ensure_ascii=False)}"
        )
    }]

    extra_categories: list[str] = []
    question_text = _default_question_text("topic")

    try:
        raw = await chat_complete_json(
            system_prompt = system,
            messages      = messages,
            temperature   = 0.3,
            max_tokens    = 150,
        )
        question_text    = raw.get("question") or question_text
        extra_categories = [
            c for c in (raw.get("extra_categories") or [])
            if isinstance(c, str) and c not in base_labels
        ]
    except Exception as e:
        logger.warning("topic 추가 선택지 생성 실패, 기저만 사용: %s", e)

    # 선택지 조합: 추가 → 기저 → 직접 입력
    extra_choices = [
        {"label": cat, "slots": {"topic_fine": cat}}
        for cat in extra_categories
    ]
    choices = extra_choices + _TOPIC_BASE_CHOICES + [_TOPIC_ESCAPE]

    return SessionQuestion(
        question = question_text,
        choices  = choices,
        slots    = ["topic"],
    )


async def _generate_multi_question(
    slots_to_ask  : list[str],
    original_query: str,
    current_slots : dict,
) -> Optional[SessionQuestion]:
    """
    복수 slot 동시 질문 생성

    LLM이 질문 텍스트 + 선택지 전부 생성
    각 선택지가 어떤 slot을 어떤 값으로 채우는지 매핑 포함
    """
    return await _generate_llm_question(
        slots_to_ask  = slots_to_ask,
        original_query= original_query,
        current_slots = current_slots,
    )


async def _generate_llm_question(
    slots_to_ask  : list[str],
    original_query: str,
    current_slots : dict,
) -> Optional[SessionQuestion]:
    """LLM으로 질문 전체 생성"""
    messages = build_question_generation_messages(
        original_query= original_query,
        slots_to_ask  = slots_to_ask,
        current_slots = current_slots,
    )

    # build_question_generation_messages 는 [system, user] 구조로 반환
    # clova_client 는 system_prompt 를 별도로 받으므로 분리
    system_msg = next((m["content"] for m in messages if m["role"] == "system"), "")
    user_msgs  = [m for m in messages if m["role"] != "system"]

    try:
        raw = await chat_complete_json(
            system_prompt = system_msg,
            messages      = user_msgs,
            temperature   = 0.4,
            max_tokens    = 400,
        )

        return SessionQuestion(
            question = raw.get("question", _default_question_text(slots_to_ask[0])),
            choices  = raw.get("choices", []),
            slots    = slots_to_ask,
        )

    except (LLMCallError, IntentParseError) as e:
        logger.error("질문 생성 실패: %s", e)
        # 폴백: 사전 정의 사용
        slot = slots_to_ask[0]
        return SessionQuestion(
            question = _default_question_text(slot),
            choices  = _PREDEFINED_CHOICES.get(slot, []),
            slots    = [slot],
        )


async def _generate_question_text(
    slot_name     : str,
    original_query: str,
    current_slots : dict,
) -> Optional[str]:
    """질문 텍스트만 LLM으로 생성"""
    import json

    slot_labels = {
        "purpose"      : "목적 (학습/교양/재미/실용)",
        "reading_level": "읽기 부담",
        "topic"        : "주제나 장르",
        "mood"         : "현재 감정이나 상태",
    }

    messages = [{
        "role": "user",
        "content": (
            f"원본 질의: {original_query}\n"
            f"현재 파악된 정보: {json.dumps(current_slots, ensure_ascii=False)}\n"
            f"물어봐야 할 것: {slot_labels.get(slot_name, slot_name)}\n\n"
            f"위 맥락에 맞는 자연스러운 질문을 한 문장으로만 작성하세요. "
            f"JSON 없이 질문 문장만 답하세요."
        )
    }]

    try:
        from app.modules.llm.clova_client import chat_complete
        text = await chat_complete(
            system_prompt = "당신은 도서 추천 도우미입니다. 질문 문장만 답하세요.",
            messages      = messages,
            temperature   = 0.4,
            max_tokens    = 80,
        )
        return text.strip()
    except Exception:
        return None


def _default_question_text(slot_name: str) -> str:
    """LLM 실패 시 사용할 기본 질문 텍스트"""
    defaults = {
        "purpose"      : "이번에는 어떤 목적으로 책을 읽으실 건가요?",
        "reading_level": "어떤 느낌의 책이 편하신가요?",
        "topic"        : "어떤 분야나 장르의 책을 찾고 계신가요?",
        "mood"         : "지금 어떤 기분이신가요?",
    }
    return defaults.get(slot_name, "조금 더 알려주실 수 있나요?")


def apply_choice(
    context   : SessionContext,
    choice    : dict[str, Any],
    asked_slots: list[str],
) -> SessionContext:
    """
    사용자가 선택한 선택지를 컨텍스트에 반영합니다.

    Args:
        context    : 현재 세션 컨텍스트
        choice     : 사용자가 선택한 선택지 {"label": ..., "slots": {...}}
        asked_slots: 이 질문이 물어본 slot 목록

    Returns:
        업데이트된 SessionContext
    """
    from app.modules.slot.schema import SlotSource, SlotValue, PurposeValue, ReadingLevelValue

    slot_updates = choice.get("slots", {})
    slots = context.slots

    for slot_name, value in slot_updates.items():
        if slot_name == "purpose" and value:
            try:
                slots.purpose = SlotValue(
                    value  = PurposeValue(value),
                    source = SlotSource.direct,
                )
            except ValueError:
                pass

        elif slot_name == "reading_level" and value:
            try:
                slots.reading_level = SlotValue(
                    value  = ReadingLevelValue(value),
                    source = SlotSource.direct,
                )
            except ValueError:
                pass

        elif slot_name == "topic_fine" and value:
            from app.modules.llm.category_mapper import get_coarse_category
            from app.modules.slot.schema import TopicSlot
            # 선택지에서 단일 값이 오므로 리스트로 감싸서 저장
            fine_list   = [value] if isinstance(value, str) else value
            coarse_list = list(filter(None, [get_coarse_category(f) for f in fine_list]))
            slots.topic = TopicSlot(
                coarse = coarse_list,
                fine   = fine_list,
                source = SlotSource.direct,
            )

    context.slots = slots
    # 이미 질문한 slot으로 기록
    context.asked_slots.extend(asked_slots)
    return context


def _context_to_dict(context: SessionContext) -> dict:
    """SessionContext → LLM 컨텍스트용 dict"""
    slots = context.slots
    result = {}
    if slots.topic.is_filled():
        result["topic"] = {
            "coarse": slots.topic.coarse,
            "fine"  : slots.topic.fine,
        }
    if slots.purpose.is_filled():
        result["purpose"] = slots.purpose.value
    if slots.reading_level.is_filled():
        result["reading_level"] = slots.reading_level.value
    if slots.mood.is_filled():
        result["mood"] = slots.mood.value
    return result
