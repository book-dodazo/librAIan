"""Prompt builders for session question generation.

함수 목록:
  build_question_generation_messages — 범용 session question 생성 (LLM에 system+user 반환)
  build_topic_category_messages      — topic 대분류 선택 질문 생성
  build_detail_question_messages     — 세부 분야 / 목적 맥락 질문 생성
  build_question_text_messages       — 단일 질문 문장 생성
"""

TOPIC_CATEGORY_SYSTEM_PROMPT = """당신은 도서 추천 도우미입니다.
현재까지 파악된 사용자 정보를 보고 아래 JSON 형식으로만 응답하세요.

{
  "question": "<어떤 분야나 장르의 책을 찾는지 묻는 짧은 질문. 반드시 물음표로 끝내세요. 답을 미리 가정하지 마세요.>",
  "extra_categories": ["<대분류명>", "<대분류명>"]
}

extra_categories 규칙:
- 파악된 정보 맥락에서 고정 목록에 없는 관련 대분류가 있으면 1~2개만 추가하세요.
- 고정 목록: 소설, 인문, 경제/경영, 자기계발, 과학, 역사/문화, 에세이
- 맥락상 추가할 것이 없으면 빈 배열 []을 반환하세요.
- category_tree의 대분류명을 그대로 사용하세요.
"""

DETAIL_QUESTION_SYSTEM_PROMPTS = {
    "topic_subject": """당신은 도서 추천 도우미입니다.
사용자가 선택한 주제 분야 안에서 더 구체적인 세부 분야를 묻는 질문을 생성합니다.
반드시 아래 JSON 형식으로만 응답하세요.

{
  "question": "<세부 분야를 묻는 짧은 질문. 반드시 물음표로 끝내세요.>",
  "choices": [
    {"label": "<세부 분야명>", "slots": {"topic_subject": "<값>"}}
  ]
}

선택지 규칙:
- 해당 분야에서 실제 추천 결과를 가를 만한 세부 분야명 3~5개를 만드세요.
- 선택지는 반드시 세부 분야명으로만 작성하세요 — 실제 책 제목, 작가 이름, 시리즈명은 절대 포함하지 마세요.
- 주어진 주제 분야와 직접 관련된 세부 분야만 생성하고, 관련 없는 분야는 추가하지 마세요.
- 마지막에는 반드시 {"label": "상관없어요", "slots": {}}를 추가하세요.
- 선택지 label은 짧고 명확하게 작성하세요.
""",
    "purpose_detail": """당신은 도서 추천 도우미입니다.
사용자의 독서 목적에 맞는 구체적인 맥락을 묻는 질문을 생성합니다.
반드시 아래 JSON 형식으로만 응답하세요.

{
  "question": "<독서 맥락을 묻는 짧은 질문. 반드시 물음표로 끝내세요.>",
  "choices": [
    {"label": "<맥락 설명>", "slots": {"purpose_context": "<값>"}}
  ]
}

선택지 규칙:
- 해당 목적에서 추천 방향이 달라지는 맥락 3~5개를 만드세요.
- 마지막에는 반드시 {"label": "잘 모르겠어요", "slots": {}}를 추가하세요.
""",
}

QUESTION_TEXT_SYSTEM_PROMPT = (
    "당신은 도서 추천 도우미입니다. "
    "지시한 형식의 질문 문장 하나만 출력하세요."
)

QUESTION_TEXT_SLOT_LABELS = {
    "purpose": "목적 (학습/교양/여가/실용)",
    "reading_level": "읽기 부담",
    "topic": "주제나 장르",
    "comparison_basis": "기준 책의 어떤 점이 비슷하면 좋은지",
    "location": "대출 가능 여부를 확인할 지역이나 도서관",
}


def build_topic_category_messages(current_slots: dict) -> tuple[str, list[dict]]:
    """Return the system prompt and user messages for topic category generation."""
    import json

    messages = [{
        "role": "user",
        "content": f"현재 파악된 정보: {json.dumps(current_slots, ensure_ascii=False)}",
    }]
    return TOPIC_CATEGORY_SYSTEM_PROMPT, messages


def build_detail_question_messages(
    slot_name: str,
    current_slots: dict,
) -> tuple[str, list[dict]]:
    """Return the system prompt and messages for detail question generation."""
    import json

    system = DETAIL_QUESTION_SYSTEM_PROMPTS[slot_name]

    if slot_name == "topic_subject":
        topic_info = current_slots.get("topic", {})
        fine_list = topic_info.get("fine", []) if isinstance(topic_info, dict) else []
        coarse_list = topic_info.get("coarse", []) if isinstance(topic_info, dict) else []
        topic_str = ", ".join(fine_list) if fine_list else "해당 분야"
        coarse_str = ", ".join(coarse_list) if coarse_list else ""
        content = (
            f"선택한 주제: {topic_str}"
            + (f" (대분류: {coarse_str})" if coarse_str else "")
        )
    else:
        purpose_val = current_slots.get("purpose", "학습")
        content = (
            f"독서 목적: {purpose_val}\n"
            f"현재 파악된 정보: {json.dumps(current_slots, ensure_ascii=False)}"
        )

    return system, [{"role": "user", "content": content}]


def build_question_text_messages(
    slot_name: str,
    current_slots: dict,
    choices: list[dict] | None = None,
) -> tuple[str, list[dict]]:
    """Return the system prompt and messages for one short question sentence."""
    import json

    context_str = json.dumps(current_slots, ensure_ascii=False) if current_slots else "없음"

    choices_str = ""
    if choices:
        labels = [c["label"] for c in choices if c.get("label")]
        if labels:
            choices_str = f"\n제시할 선택지: {json.dumps(labels, ensure_ascii=False)}"

    messages = [{
        "role": "user",
        "content": (
            f"현재 파악된 정보: {context_str}"
            f"{choices_str}\n\n"
            "위 맥락에서 아래 선택지로 자연스럽게 이어지는 짧은 질문 문장 하나를 작성하세요.\n"
            "규칙:\n"
            "- 반드시 물음표로 끝나는 의문문\n"
            "- 선택지 내용을 미리 언급하거나 가정하지 않기\n"
            "- 현재 파악된 주제·감정 등과 자연스럽게 연결되는 질문\n"
            "- 질문 문장 하나만 출력"
        ),
    }]
    return QUESTION_TEXT_SYSTEM_PROMPT, messages


_GENERAL_QUESTION_SYSTEM = """당신은 도서 추천 시스템의 질문 생성 전문가입니다.
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
}"""

_SLOTS_DESC = {
    "topic"        : "주제 (장르, 분야)",
    "purpose"      : "목적 (학습/교양/재미/실용)",
    "reading_level": "읽기 부담 (쉬운/적당한/깊이 있는)",
    "mood"         : "현재 감정이나 상태",
}


def build_question_generation_messages(
    original_query: str,
    slots_to_ask  : list[str],
    current_slots : dict,
) -> list[dict]:
    """
    범용 session question 생성용 messages 배열.

    반환 형식: [{"role": "system", ...}, {"role": "user", ...}]
    호출부에서 system/user를 분리해서 chat_complete_json에 전달.
    """
    import json

    ask_desc = "\n".join([
        f"- {s}: {_SLOTS_DESC.get(s, s)}"
        for s in slots_to_ask
    ])

    user_content = (
        f"원본 질의: {original_query}\n\n"
        f"현재 파악된 정보:\n{json.dumps(current_slots, ensure_ascii=False, indent=2)}\n\n"
        f"물어봐야 할 slot:\n{ask_desc}"
    )

    return [
        {"role": "system", "content": _GENERAL_QUESTION_SYSTEM},
        {"role": "user",   "content": user_content},
    ]

