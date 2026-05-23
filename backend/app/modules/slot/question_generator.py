# -*- coding: utf-8 -*-
# ============================================================
# app/modules/slot/question_generator.py
#
# 변경 이력:
#   v0.1 - 최초 작성
#          slot 목록 기반 세션 질문 생성 (LLM + predefined 선택지)
#          SessionQuestion 데이터 클래스, apply_choice 처리
#   v0.2 - HCX-007 사전 생성 질문/선택지 우선 사용 구조로 변경
#          generate_question: 4단계 우선순위 처리 (location→predefined→HCX007→fallback)
#          purpose/reading_level: predefined 선택지 + HCX-007 질문 문장 결합
#          topic_subject: HCX-007 사전 생성값 우선, 없으면 별도 LLM 호출
#          _sanitize_choices: LLM이 slots 키 생략한 선택지 자동 복구
#          generate_personalization_question: 개인화 체크인용 mood 질문 추가
#          apply_choice: mood 버튼 선택 처리 추가
# ============================================================
"""
세션 질문 생성 모듈

역할:
    get_slots_to_ask()가 반환한 슬롯 목록을 보고
    사용자에게 보여줄 SessionQuestion (질문 문장 + 선택지)을 생성합니다.

처리 우선순위:
    1. location / comparison_basis
       → 항상 코드 기반 (온보딩·anchor 데이터 필요 — LLM 불필요)
    2. purpose / reading_level
       → HCX-007이 충분도 판단 시 미리 생성한 질문 문장 우선 사용
          + 코드 기반 predefined 선택지 결합
    3. topic_subject / 복수 슬롯
       → HCX-007 사전 생성값(llm_question + llm_choices) 우선 사용.
          없으면 별도 LLM 호출(fallback)

SelectionQuestion 구조:
    question : 사용자에게 보여줄 질문 문장
    choices  : [{"label": "...", "slots": {"slot_name": "value"}}, ...]
               버튼 선택 시 apply_choice()로 슬롯에 반영
    slots    : 이 질문이 채우려는 슬롯 목록 (pending_slots로 프론트에 전달)

apply_choice():
    선택지의 slots 딕셔너리를 파싱해 SessionContext에 반영.
    특수 슬롯 처리:
        topic_fine         : fine → coarse 역방향 매핑 후 TopicSlot 채움
        comparison_basis_dim: ComparisonDimension Enum으로 변환
        location_region / location_library: LocationSlot 채움
        mood               : MoodCategory Enum으로 변환
"""
import logging
from typing import Any, Optional

from app.core.exceptions import IntentParseError, LLMCallError
from app.modules.llm.clova_client import chat_complete_json
from app.modules.slot.schema import SessionContext
from app.prompts.question_generation import (
    build_detail_question_messages,
    build_question_text_messages,
    build_topic_category_messages,
)
from app.prompts.slot import build_question_generation_messages

logger = logging.getLogger(__name__)

_PURPOSE_ALL: list[dict] = [
    {"label": "공부나 입문용으로", "slots": {"purpose": "학습"}},
    {"label": "교양으로 읽고 싶어요", "slots": {"purpose": "교양"}},
    {"label": "재미있게 읽고 싶어요", "slots": {"purpose": "재미"}},
    {"label": "실생활에 도움되는 걸", "slots": {"purpose": "실용"}},
    {"label": "잘 모르겠어요", "slots": {}},
]

_PURPOSE_BY_TOPIC: dict[str, list[str]] = {
    "소설": ["재미있게 읽고 싶어요", "교양으로 읽고 싶어요", "잘 모르겠어요"],
    "시/에세이": ["재미있게 읽고 싶어요", "교양으로 읽고 싶어요", "잘 모르겠어요"],
    "경제/경영": ["공부나 입문용으로", "실생활에 도움되는 걸", "교양으로 읽고 싶어요", "잘 모르겠어요"],
    "자기계발": ["실생활에 도움되는 걸", "공부나 입문용으로", "재미있게 읽고 싶어요", "잘 모르겠어요"],
    "컴퓨터/IT": ["공부나 입문용으로", "실생활에 도움되는 걸", "교양으로 읽고 싶어요", "잘 모르겠어요"],
    "기술/공학": ["공부나 입문용으로", "실생활에 도움되는 걸", "교양으로 읽고 싶어요", "잘 모르겠어요"],
    "외국어": ["공부나 입문용으로", "실생활에 도움되는 걸", "잘 모르겠어요"],
    "건강": ["실생활에 도움되는 걸", "공부나 입문용으로", "잘 모르겠어요"],
    "요리": ["실생활에 도움되는 걸", "재미있게 읽고 싶어요", "잘 모르겠어요"],
}
_PURPOSE_LABEL_MAP = {c["label"]: c for c in _PURPOSE_ALL}

_HEAVY_MOOD_CATEGORIES = {
    "negative_exhausted", "negative_depressed", "negative_passive", "negative_empty",
    "negative_anxious", "negative_angry", "negative_stressed",
    "recovery_comfort", "recovery_relax", "recovery_escape", "recovery_meaning",
}

_READING_LEVEL_ALL: list[dict] = [
    {"label": "가볍고 쉽게 읽히는 책", "slots": {"reading_level": "easy"}},
    {"label": "적당히 생각할 거리가 있는 책", "slots": {"reading_level": "medium"}},
    {"label": "깊이 있어도 괜찮아요", "slots": {"reading_level": "hard"}},
    {"label": "상관없어요", "slots": {}},
]
_READING_LEVEL_LABEL_MAP = {c["label"]: c for c in _READING_LEVEL_ALL}

_PREDEFINED_CHOICES: dict[str, list[dict]] = {
    "comparison_basis": [
        {"label": "분위기가 비슷한", "slots": {"comparison_basis_dim": "mood"}},
        {"label": "비슷한 주제나 소재", "slots": {"comparison_basis_dim": "topic"}},
        {"label": "문체나 문장 스타일", "slots": {"comparison_basis_dim": "style"}},
        {"label": "쉽게 읽히는 정도", "slots": {"comparison_basis_dim": "difficulty"}},
        {"label": "생각할 거리나 깊이", "slots": {"comparison_basis_dim": "depth"}},
        {"label": "직접 입력", "slots": {}},
    ],
}

_PERSONALIZATION_QUESTION = "지금 어떤 기분으로 읽고 싶으세요?"

_PERSONALIZATION_MOOD_CHOICES: list[dict] = [
    {"label": "바로 추천해줘", "slots": {}},
    {"label": "가볍고 즐겁게", "slots": {"mood": "positive_relaxed"}},
    {"label": "따뜻한 위로가 필요해요", "slots": {"mood": "recovery_comfort"}},
    {"label": "빠져들고 싶어요", "slots": {"mood": "recovery_escape"}},
    {"label": "뭔가 배우고 싶은 기분", "slots": {"mood": "recovery_meaning"}},
]

_TOPIC_BASE_CHOICES: list[dict] = [
    {"label": "소설", "slots": {"topic_fine": "소설"}},
    {"label": "인문", "slots": {"topic_fine": "인문"}},
    {"label": "경제/경영", "slots": {"topic_fine": "경제/경영"}},
    {"label": "자기계발", "slots": {"topic_fine": "자기계발"}},
    {"label": "과학", "slots": {"topic_fine": "과학"}},
    {"label": "역사/문화", "slots": {"topic_fine": "역사/문화"}},
    {"label": "시/에세이", "slots": {"topic_fine": "시/에세이"}},
]
_TOPIC_ESCAPE = {"label": "직접 입력", "slots": {}}


class SessionQuestion:
    """Session question shown to the user."""

    def __init__(self, question: str, choices: list[dict[str, Any]], slots: list[str]):
        self.question = question
        self.choices = choices
        self.slots = slots

    def to_dict(self) -> dict:
        return {"question": self.question, "choices": self.choices, "slots": self.slots}


def _sanitize_choices(choices: list) -> list[dict]:
    """LLM이 slots 키를 생략한 선택지를 자동 복구.

    올바른 형식: {"label": "X", "slots": {"mood": "Y"}}
    잘못된 형식: {"label": "X", "mood": "Y"}  ← slots 키 없이 평탄 구조
    """
    sanitized = []
    for c in choices:
        if not isinstance(c, dict):
            continue
        if "slots" not in c:
            # slots 키 없이 나머지 키가 slot명으로 들어온 경우 → 래핑
            inner = {k: v for k, v in c.items() if k != "label"}
            c = {"label": c.get("label", ""), "slots": inner}
        sanitized.append(c)
    return sanitized


def generate_personalization_question() -> SessionQuestion:
    """대분류 요청 시 mood 체크인용 경량 개인화 질문."""
    return SessionQuestion(
        _PERSONALIZATION_QUESTION,
        _PERSONALIZATION_MOOD_CHOICES,
        ["mood"],
    )


async def generate_question(
    slots_to_ask: list[str],
    context: SessionContext,
) -> Optional[SessionQuestion]:
    """슬롯 목록을 보고 사용자에게 보여줄 SessionQuestion을 반환합니다.

    처리 우선순위:
      1. location / comparison_basis → 항상 코드 기반 (온보딩·anchor 데이터 필요)
      2. purpose / reading_level    → HCX-007이 미리 생성한 question 문장 사용
                                       + 코드 기반 predefined 선택지 결합
      3. topic_subject / 복수 슬롯  → HCX-007이 미리 생성한 question + choices 사용
                                       (없으면 별도 LLM 호출로 fallback)
    """
    if not slots_to_ask:
        return None

    current_slots = _context_to_dict(context)

    # ── 항상 코드 기반 (온보딩·anchor 데이터 필요 — LLM 불필요) ──
    if len(slots_to_ask) == 1 and slots_to_ask[0] == "location":
        return _generate_location_question(context)

    if len(slots_to_ask) == 1 and slots_to_ask[0] == "comparison_basis":
        return _generate_comparison_basis_question(current_slots)

    # ── predefined 선택지 슬롯: choices는 코드, question은 템플릿 사용 ──
    # purpose / reading_level 은 context.llm_question을 절대 재사용하지 않음.
    # llm_question은 이전 턴(topic_subject 등)에서 만든 문장이 남아 있을 수 있어서
    # 엉뚱한 질문 텍스트 + 올바른 선택지 조합이 표시되는 버그가 발생함.
    if len(slots_to_ask) == 1 and slots_to_ask[0] in ("purpose", "reading_level"):
        slot_name = slots_to_ask[0]
        predefined = _get_predefined_choices(slot_name, current_slots)
        question_text = _make_template_question(slot_name, current_slots)
        logger.info("predefined 질문 (%s): %s [source=template]", slot_name, question_text)
        return SessionQuestion(question_text, predefined, [slot_name])

    # ── topic_subject / 복수 슬롯: HCX-007 사전 생성값 우선 사용 ──
    if context.llm_question and context.llm_choices:
        choices = _sanitize_choices(context.llm_choices)
        if not choices:
            choices = [{"label": "잘 모르겠어요", "slots": {}}]
        logger.info(
            "HCX-007 사전 생성 질문 사용: %s (선택지 %d개)",
            context.llm_question,
            len(choices),
        )
        return SessionQuestion(context.llm_question, choices, slots_to_ask)

    # ── fallback: HCX-007 사전 생성값이 없는 경우 별도 LLM 호출 ──
    logger.info("HCX-007 사전 생성 질문 없음 — fallback LLM 호출: %s", slots_to_ask)
    if len(slots_to_ask) == 1 and slots_to_ask[0] == "topic_subject":
        return await _generate_detail_question(slots_to_ask[0], context)

    return await _generate_multi_question(slots_to_ask, context.original_query, current_slots)


async def _generate_single_question(
    slot_name: str,
    original_query: str,
    current_slots: dict,
) -> Optional[SessionQuestion]:
    if slot_name == "topic":
        return await _generate_topic_question(current_slots)

    if slot_name == "comparison_basis":
        return _generate_comparison_basis_question(current_slots)

    predefined = _get_predefined_choices(slot_name, current_slots)
    if not predefined:
        return await _generate_llm_question([slot_name], original_query, current_slots)

    # reading_level / purpose 같이 선택지가 고정된 슬롯은 LLM 질문 생성 불필요.
    # LLM이 선택지 단어를 미리 질문에 노출하거나 어색한 문장을 만드는 문제 방지.
    question_text = _make_template_question(slot_name, current_slots)
    return SessionQuestion(question_text, predefined, [slot_name])


def _generate_comparison_basis_question(current_slots: dict) -> SessionQuestion:
    """anchor 이름을 활용한 comparison_basis 질문 — LLM 불필요."""
    anchor = current_slots.get("anchor", {})
    anchor_name = anchor.get("value") if isinstance(anchor, dict) else None
    if anchor_name:
        question_text = f"'{anchor_name}'의 어떤 점과 비슷한 책을 찾으시나요?"
    else:
        question_text = _default_question_text("comparison_basis")
    return SessionQuestion(question_text, _PREDEFINED_CHOICES["comparison_basis"], ["comparison_basis"])


def _get_mood_category(current_slots: dict) -> str:
    mood = current_slots.get("mood", {})
    if not isinstance(mood, dict):
        return ""
    cats = mood.get("categories", [])
    return cats[0] if cats else ""


def _get_predefined_choices(slot_name: str, current_slots: dict) -> Optional[list[dict]]:
    if slot_name == "purpose":
        return _get_purpose_choices(current_slots)
    if slot_name == "reading_level":
        return _get_reading_level_choices(current_slots)
    return _PREDEFINED_CHOICES.get(slot_name)


def _get_purpose_choices(current_slots: dict) -> list[dict]:
    topic = current_slots.get("topic", {})
    coarse_list = topic.get("coarse", []) if isinstance(topic, dict) else []
    mood_cat = _get_mood_category(current_slots)

    base_labels: list[str] | None = None
    for coarse in coarse_list:
        if coarse in _PURPOSE_BY_TOPIC:
            base_labels = _PURPOSE_BY_TOPIC[coarse]
            break
    if base_labels is None:
        base_labels = [c["label"] for c in _PURPOSE_ALL]

    if mood_cat in _HEAVY_MOOD_CATEGORIES:
        base_labels = [
            label for label in base_labels
            if label not in {"공부나 입문용으로", "실생활에 도움되는 걸"}
        ]
        if "잘 모르겠어요" not in base_labels:
            base_labels.append("잘 모르겠어요")

    return [_PURPOSE_LABEL_MAP[label] for label in base_labels if label in _PURPOSE_LABEL_MAP]


def _get_reading_level_choices(current_slots: dict) -> list[dict]:
    mood_cat = _get_mood_category(current_slots)
    purpose = current_slots.get("purpose")

    if mood_cat in _HEAVY_MOOD_CATEGORIES:
        labels = ["가볍고 쉽게 읽히는 책", "적당히 생각할 거리가 있는 책", "상관없어요"]
        return [_READING_LEVEL_LABEL_MAP[label] for label in labels]

    if purpose in ("학습", "실용"):
        labels = ["깊이 있어도 괜찮아요", "적당히 생각할 거리가 있는 책", "가볍고 쉽게 읽히는 책", "상관없어요"]
        return [_READING_LEVEL_LABEL_MAP[label] for label in labels]

    return _READING_LEVEL_ALL


async def _generate_topic_question(current_slots: dict) -> SessionQuestion:
    base_labels = {c["label"] for c in _TOPIC_BASE_CHOICES}

    if not current_slots:
        return SessionQuestion(
            _default_question_text("topic"),
            _TOPIC_BASE_CHOICES + [_TOPIC_ESCAPE],
            ["topic"],
        )

    system, messages = build_topic_category_messages(current_slots)
    extra_categories: list[str] = []
    question_text = _default_question_text("topic")

    try:
        raw = await chat_complete_json(
            system_prompt=system,
            messages=messages,
            temperature=0.3,
            max_tokens=None,   # HCX-007은 max_tokens 파라미터 미지원
            model="HCX-007",
        )
        llm_question = raw.get("question") or ""
        if llm_question.endswith("?"):
            question_text = llm_question
        extra_categories = [
            c for c in (raw.get("extra_categories") or [])
            if isinstance(c, str) and c not in base_labels
        ]
    except Exception as e:
        logger.warning("topic extra choices generation failed, using defaults: %s", e)

    extra_choices = [{"label": cat, "slots": {"topic_fine": cat}} for cat in extra_categories]
    return SessionQuestion(question_text, extra_choices + _TOPIC_BASE_CHOICES + [_TOPIC_ESCAPE], ["topic"])


async def _generate_detail_question(slot_name: str, context: SessionContext) -> SessionQuestion:
    current_slots = _context_to_dict(context)
    system, messages = build_detail_question_messages(slot_name, current_slots)
    fallback_question = (
        "어떤 세부 분야의 책을 찾고 계신가요?"
        if slot_name == "topic_subject"
        else "어떤 목적에 맞춰 읽을 책인지 조금 더 알려주실 수 있나요?"
    )

    try:
        raw = await chat_complete_json(
            system_prompt=system,
            messages=messages,
            temperature=0.4,
            max_tokens=None,   # HCX-007은 max_tokens 파라미터 미지원
            model="HCX-007",
        )
        question = raw.get("question") or ""
        if not question.endswith("?"):
            question = fallback_question
        choices = _sanitize_choices(raw.get("choices") or [])
    except Exception as e:
        logger.warning("detail question generation failed (%s): %s", slot_name, e)
        question = fallback_question
        choices = [{"label": "잘 모르겠어요", "slots": {}}]

    if not choices:
        choices = [{"label": "잘 모르겠어요", "slots": {}}]

    return SessionQuestion(question, choices, [slot_name])


def _generate_location_question(context: SessionContext) -> SessionQuestion:
    onboarding = context.onboarding or {}
    choices: list[dict[str, Any]] = []

    seen_libraries = set()
    for library in onboarding.get("frequent_libraries") or []:
        if not library or library in seen_libraries:
            continue
        seen_libraries.add(library)
        choices.append({"label": f"{library} 기준", "slots": {"location_library": library}})

    region = onboarding.get("region")
    if region:
        choices.append({"label": f"{region} 지역 기준", "slots": {"location_region": region}})

    choices.append({"label": "직접 입력", "slots": {}})
    return SessionQuestion(_default_question_text("location"), choices, ["location"])


async def _generate_multi_question(
    slots_to_ask: list[str],
    original_query: str,
    current_slots: dict,
) -> Optional[SessionQuestion]:
    return await _generate_llm_question(slots_to_ask, original_query, current_slots)


async def _generate_llm_question(
    slots_to_ask: list[str],
    original_query: str,
    current_slots: dict,
) -> Optional[SessionQuestion]:
    messages = build_question_generation_messages(
        original_query=original_query,
        slots_to_ask=slots_to_ask,
        current_slots=current_slots,
    )
    system_msg = next((m["content"] for m in messages if m["role"] == "system"), "")
    user_msgs = [m for m in messages if m["role"] != "system"]

    try:
        raw = await chat_complete_json(
            system_prompt=system_msg,
            messages=user_msgs,
            temperature=0.4,
            max_tokens=None,   # HCX-007은 max_tokens 파라미터 미지원
            model="HCX-007",
        )
        return SessionQuestion(
            raw.get("question", _default_question_text(slots_to_ask[0])),
            _sanitize_choices(raw.get("choices") or []),
            slots_to_ask,
        )
    except (LLMCallError, IntentParseError) as e:
        logger.error("question generation failed: %s", e)
        slot = slots_to_ask[0]
        return SessionQuestion(
            _default_question_text(slot),
            _get_predefined_choices(slot, current_slots) or [],
            [slot],
        )


async def _generate_question_text(
    slot_name: str,
    current_slots: dict,
    choices: Optional[list[dict]] = None,
) -> Optional[str]:
    system_prompt, messages = build_question_text_messages(slot_name, current_slots, choices=choices)

    try:
        from app.modules.llm.clova_client import chat_complete
        text = await chat_complete(
            system_prompt=system_prompt,
            messages=messages,
            temperature=0.4,
            max_tokens=80,
        )
        text = text.strip()
        return text if text.endswith("?") else None
    except Exception:
        return None


def _make_template_question(slot_name: str, current_slots: dict) -> str:
    """predefined 선택지용 질문 문장 — LLM 없이 템플릿으로 생성.

    topic 정보가 있으면 주제를 자연스럽게 언급하고,
    없으면 generic 기본 문장으로 폴백.
    선택지 단어를 미리 노출하지 않도록 설계됨.
    """
    topic = current_slots.get("topic", {})
    fine  = topic.get("fine", []) if isinstance(topic, dict) else []
    # 최대 2개, 너무 길면 잘라냄
    topic_str = ", ".join(fine[:2]) if fine else ""

    if slot_name == "reading_level":
        if topic_str:
            return f"{topic_str} 책을 어느 정도 깊이로 보고 싶으세요?"
        return "어느 정도 깊이의 책을 원하시나요?"

    if slot_name == "purpose":
        if topic_str:
            return f"{topic_str} 책을 어떤 목적으로 읽으실 건가요?"
        return "이번에는 어떤 목적으로 책을 읽으실 건가요?"

    # 그 외 predefined가 생기면 기본 텍스트로
    return _default_question_text(slot_name)


def _default_question_text(slot_name: str) -> str:
    defaults = {
        "purpose": "이번에는 어떤 목적으로 책을 읽으실 건가요?",
        "reading_level": "어떤 느낌의 책이 편하신가요?",
        "topic": "어떤 분야나 장르의 책을 찾고 계신가요?",
        "comparison_basis": "그 책에서 어떤 점이 특히 좋으셨나요?",
        "location": "어느 지역이나 도서관 기준으로 대출 가능 여부를 확인할까요?",
    }
    return defaults.get(slot_name, "조금 더 알려주실 수 있나요?")


def apply_choice(
    context: SessionContext,
    choice: dict[str, Any],
    asked_slots: list[str],
) -> SessionContext:
    from app.modules.llm.category_mapper import get_coarse_category
    from app.modules.slot.schema import (
        ComparisonBasisSlot,
        ComparisonDimension,
        Constraint,
        LocationSlot,
        PurposeValue,
        ReadingLevelValue,
        SlotSource,
        SlotValue,
        TopicSlot,
    )

    slot_updates = choice.get("slots", {})
    slots = context.slots

    for slot_name, value in slot_updates.items():
        if slot_name == "purpose" and value:
            try:
                slots.purpose = SlotValue(value=PurposeValue(value), source=SlotSource.direct)
            except ValueError:
                pass

        elif slot_name == "reading_level" and value:
            try:
                slots.reading_level = SlotValue(value=ReadingLevelValue(value), source=SlotSource.direct)
            except ValueError:
                pass

        elif slot_name == "topic_fine" and value:
            fine_list = [value] if isinstance(value, str) else list(value)
            coarse_list = list(dict.fromkeys(filter(None, [get_coarse_category(f) for f in fine_list])))
            slots.topic = TopicSlot(coarse=coarse_list, fine=fine_list, source=SlotSource.direct)

        elif slot_name == "comparison_basis_dim" and value:
            try:
                new_dim = ComparisonDimension(value)
                existing_dims = list(slots.comparison_basis.dimensions)
                if new_dim not in existing_dims:
                    existing_dims.append(new_dim)
                slots.comparison_basis = ComparisonBasisSlot(
                    dimensions=existing_dims,
                    raw=slots.comparison_basis.raw,
                    source=SlotSource.direct,
                )
            except ValueError:
                pass

        elif slot_name == "topic_subject" and value:
            subject_list = [value] if isinstance(value, str) else list(value)
            slots.topic = TopicSlot(
                coarse=slots.topic.coarse,
                fine=slots.topic.fine,
                subject=subject_list,
                source=SlotSource.direct,
            )
            context.needs_subject_clarification = False

        elif slot_name == "purpose_context" and value:
            if not any(c.type == "purpose_context" for c in slots.constraints):
                slots.constraints.append(Constraint(type="purpose_context", value=value, raw=value))
            context.needs_purpose_clarification = False

        elif slot_name == "location_region" and value:
            slots.location = LocationSlot(
                region=str(value),
                library=slots.location.library,
                source=SlotSource.direct,
            )

        elif slot_name == "location_library" and value:
            slots.location = LocationSlot(
                region=slots.location.region,
                library=str(value),
                source=SlotSource.direct,
            )

        elif slot_name == "mood" and value:
            from app.modules.slot.schema import MoodCategory, MoodSlot
            try:
                slots.mood = MoodSlot(
                    categories=[MoodCategory(value)],
                    source=SlotSource.direct,
                )
            except ValueError:
                pass

    context.slots = slots
    context.asked_slots.extend(asked_slots)
    return context


def _context_to_dict(context: SessionContext) -> dict:
    slots = context.slots
    result: dict[str, Any] = {}

    if slots.topic.is_filled():
        result["topic"] = {
            "coarse": slots.topic.coarse,
            "fine": slots.topic.fine,
            "subject": slots.topic.subject,
        }
    if slots.purpose.is_filled():
        result["purpose"] = slots.purpose.value.value if hasattr(slots.purpose.value, "value") else slots.purpose.value
    if slots.reading_level.is_filled():
        result["reading_level"] = slots.reading_level.value.value if hasattr(slots.reading_level.value, "value") else slots.reading_level.value
    if slots.mood.is_filled():
        result["mood"] = {
            "categories": [c.value for c in slots.mood.categories],
            "raw"       : slots.mood.raw,
        }
    if slots.comparison_basis.is_filled():
        result["comparison_basis"] = {
            "dimensions": [d.value for d in slots.comparison_basis.dimensions],
            "raw": slots.comparison_basis.raw,
        }
    if slots.location.is_filled():
        result["location"] = {
            "region": slots.location.region,
            "library": slots.location.library,
        }
    return result