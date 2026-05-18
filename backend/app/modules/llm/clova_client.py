# -*- coding: utf-8 -*-
# ============================================================
# app/modules/llm/clova_client.py
#
# 변경 이력:
#   v0.1 - 최초 작성
#   v0.2 - [FIX] CLOVA_API_KEY 미설정 시 즉시 명확한 에러 메시지 출력
#           (기존: OpenAI SDK가 401 에러를 뱉어 원인 파악 어려움)
#   v0.3 - [FIX] JSON 파싱 시 ```json 코드블록 제거 로직 보강
# ============================================================
"""
CLOVA Studio LLM 클라이언트 래퍼

CLOVA Studio 는 OpenAI 호환 엔드포인트를 제공합니다.
base_url 만 바꿔서 openai Python SDK 를 그대로 재사용합니다.

장점:
    - 나중에 다른 모델로 교체할 때 이 파일만 수정하면 됩니다.
    - 서비스 레이어는 변경 불필요.

제공 함수:
    chat_complete      : 텍스트 응답 반환
    chat_complete_json : JSON 응답 파싱 후 dict 반환
"""
import json
import logging
import re

from openai import AsyncOpenAI, APIError, AuthenticationError, APITimeoutError

from app.core.config import settings
from app.core.exceptions import IntentParseError, LLMCallError

logger = logging.getLogger(__name__)


def _make_client() -> AsyncOpenAI:
    """
    AsyncOpenAI 클라이언트 생성.

    비동기(Async) 를 쓰는 이유:
        FastAPI 는 비동기 서버입니다. 동기 HTTP 호출을 쓰면
        한 요청이 LLM 응답을 기다리는 동안 다른 요청을 처리 못합니다.
        비동기 클라이언트를 쓰면 대기 중에 다른 요청을 처리할 수 있습니다.
    """
    # [FIX] API 키 미설정 시 서버 시작 단계에서 바로 알 수 있도록 검증
    if not settings.CLOVA_API_KEY:
        raise ValueError(
            "CLOVA_API_KEY 가 설정되지 않았습니다. "
            ".env 파일에 CLOVA_API_KEY=... 를 추가해주세요."
        )
    return AsyncOpenAI(
        api_key=settings.CLOVA_API_KEY,
        base_url=settings.CLOVA_BASE_URL,
        timeout=45.0,
    )


# 모듈 레벨 싱글턴 — HTTP 연결을 재사용해 성능 향상
# [잠재적 위험] 앱 시작 시 API 키 없으면 ValueError 발생 → main.py 에서 try/except 처리
try:
    _client = _make_client()
except ValueError as e:
    logger.warning("LLM 클라이언트 초기화 실패: %s", e)
    _client = None  # type: ignore


async def chat_complete(
    system_prompt: str,
    messages: list[dict],
    *,
    temperature: float = 0.3,
    max_tokens: int = 512,
) -> str:
    """
    CLOVA Studio 에 채팅 완성 요청을 보내고 텍스트 응답을 반환합니다.

    Args:
        system_prompt: 모델의 역할/지시사항을 정의하는 시스템 메시지
        messages     : [{"role": "user"|"assistant", "content": "..."}, ...]
        temperature  : 낮을수록 일관된 답변 (의도 분류엔 0.2 권장)
        max_tokens   : 최대 출력 토큰 수

    Returns:
        모델이 생성한 텍스트 문자열

    Raises:
        LLMCallError: API 호출 실패 (네트워크 오류, 인증 실패 등)
    """
    # [FIX] 클라이언트 초기화 실패 상태에서 호출 시 명확한 에러 반환
    if _client is None:
        raise LLMCallError(
            "LLM 클라이언트가 초기화되지 않았습니다. CLOVA_API_KEY 를 확인하세요."
        )

    full_messages = [{"role": "system", "content": system_prompt}] + messages

    try:
        response = await _client.chat.completions.create(
            model=settings.CLOVA_MODEL,
            messages=full_messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content or ""

    except AuthenticationError as e:
        logger.error("CLOVA 인증 실패. API 키를 확인하세요: %s", e)
        raise LLMCallError("CLOVA Studio API 키가 올바르지 않습니다.") from e

    except APITimeoutError as e:
        logger.error("CLOVA API 타임아웃 (45s 초과)")
        raise LLMCallError("CLOVA Studio 응답 시간 초과 (45초). 잠시 후 다시 시도해 주세요.") from e

    except APIError as e:
        logger.error("CLOVA API 오류: status=%s body=%s", e.status_code, e.body)
        raise LLMCallError(f"CLOVA Studio API 오류 (status={e.status_code})") from e


def _clean_json_response(raw: str) -> str:
    """LLM 응답에서 JSON만 추출 (코드블록·인라인 주석 제거)."""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    cleaned = re.sub(r"\s*//[^\n]*", "", cleaned)
    return cleaned


async def chat_complete_json(
    system_prompt: str,
    messages: list[dict],
    max_retries: int = 2,
    **kwargs,
) -> dict:
    """
    JSON 응답을 기대할 때 쓰는 편의 함수.

    빈 응답 또는 JSON 파싱 실패 시 max_retries 횟수만큼 재시도합니다.
    """
    last_error: Exception | None = None

    for attempt in range(max_retries + 1):
        raw = await chat_complete(system_prompt, messages, **kwargs)
        cleaned = _clean_json_response(raw)

        if not cleaned:
            last_error = IntentParseError("LLM 응답이 비어있습니다.")
            logger.warning("LLM 빈 응답 (attempt %d/%d) — 재시도", attempt + 1, max_retries + 1)
            continue

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            last_error = IntentParseError(f"LLM 응답을 JSON으로 파싱 실패: {e}")
            logger.warning(
                "JSON 파싱 실패 (attempt %d/%d).\n원본:\n%s\n정제 후:\n%s",
                attempt + 1, max_retries + 1, raw, cleaned,
            )

    raise last_error  # type: ignore[misc]
