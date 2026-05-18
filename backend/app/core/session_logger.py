# -*- coding: utf-8 -*-
# ============================================================
# app/core/session_logger.py
#
# 세션 로그 수집기
#
# 목적:
#   1. 디버깅: 슬롯 추출 오류, 세션 질문 흐름, signal 감지 결과 확인
#   2. 성능 분석: 파이프라인 단계별 소요시간, 후보 수 추이
#   3. 추후 개선: 온보딩 활용 여부, 세션-추천 결과 상관관계 분석
#
# 저장 방식:
#   turns/turns.jsonl    — 턴마다 append (실시간, 세션 중단 시에도 보존)
#   sessions/sessions.jsonl — 세션 완료 시 요약본 저장 (분석용)
#
# 환경변수:
#   SESSION_LOG_DIR : 로그 디렉토리 (기본: logs/)
#   SESSION_LOG_ENABLED : 로깅 활성화 여부 (기본: true)
# ============================================================

from __future__ import annotations

import json
import logging
import os
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ── 환경 설정 ─────────────────────────────────────────────────

_LOG_DIR     = Path(os.getenv("SESSION_LOG_DIR", "logs"))
_LOG_ENABLED = os.getenv("SESSION_LOG_ENABLED", "true").lower() == "true"

_TURN_LOG_PATH    = _LOG_DIR / "turns" / "turns.jsonl"
_SESSION_LOG_PATH = _LOG_DIR / "sessions" / "sessions.jsonl"


# ── 로그 데이터 클래스 ────────────────────────────────────────

@dataclass
class SignalLog:
    """signal.detect() 결과"""
    categories : dict[str, bool]  # {"cat1_negative": true, ...}
    importance : dict[str, str]   # {"topic": "low", "purpose": "high", ...}
    uncertainty: dict[str, str]


@dataclass
class PipelineLog:
    """파이프라인 각 단계 결과"""
    bm25_count        : int   = 0  # BM25 검색 후보 수
    reranker_count    : int   = 0  # Reranking 후 수
    availability_count: int   = 0  # 대출가능 필터 후 수
    elapsed_ms        : dict  = field(default_factory=dict)
    # {"bm25": 120, "reranker": 340, "availability": 80, "total": 540}


@dataclass
class TurnLog:
    """단일 턴 로그 — turns.jsonl에 한 줄로 저장"""
    session_id   : str
    user_id      : Optional[str]
    turn         : int
    timestamp    : str
    query        : str

    # signal 결과
    signal       : Optional[dict] = None  # SignalLog.asdict()

    # 슬롯 상태
    slots_before : dict = field(default_factory=dict)  # 이 턴 시작 시 슬롯 상태
    slots_after  : dict = field(default_factory=dict)  # LLM 추출 후 슬롯 상태

    # 세션 질문
    slots_asked  : list[str] = field(default_factory=list)  # 이 턴에서 질문한 슬롯
    user_choice  : Optional[dict] = None  # 사용자가 선택한 선택지

    # RAG 쿼리 (추천 발생 시)
    rag_query    : Optional[dict] = None

    # 파이프라인 결과 (추천 발생 시)
    pipeline     : Optional[dict] = None  # PipelineLog.asdict()

    # 온보딩 활용 여부 (추천 발생 시)
    onboarding_applied: Optional[dict] = None

    # 추천 결과 (마지막 턴)
    result       : Optional[list] = None


@dataclass
class SessionLog:
    """세션 전체 요약 — sessions.jsonl에 한 줄로 저장"""
    session_id  : str
    user_id     : Optional[str]
    started_at  : str
    ended_at    : str
    total_turns : int
    original_query: str

    # 최종 슬롯 상태
    slot_summary: dict = field(default_factory=dict)

    # 온보딩 활용 여부
    onboarding_applied: dict = field(default_factory=dict)

    # 최종 추천 결과
    final_result: list = field(default_factory=list)

    # 세션 완료 여부
    completed   : bool = False  # 추천 결과 반환까지 완료했으면 True


# ── 직렬화 헬퍼 ──────────────────────────────────────────────

def _serialize(obj: Any) -> Any:
    """dataclass, Enum, 복잡한 객체를 JSON 직렬화 가능한 형태로 변환"""
    if hasattr(obj, "__dataclass_fields__"):
        return asdict(obj)
    if hasattr(obj, "value"):  # Enum
        return obj.value
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_serialize(v) for v in obj]
    return obj


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── 슬롯 상태 직렬화 ─────────────────────────────────────────

def _serialize_slots(slots) -> dict:
    """SlotState → 로그용 dict 변환"""
    result = {}

    if slots.topic.is_filled():
        result["topic"] = {
            "coarse": slots.topic.coarse,
            "fine"  : slots.topic.fine,
            "source": slots.topic.source.value,
        }
    if slots.purpose.is_filled():
        val = slots.purpose.value
        result["purpose"] = {
            "value" : val.value if hasattr(val, "value") else str(val),
            "source": slots.purpose.source.value,
        }
    if slots.reading_level.is_filled():
        val = slots.reading_level.value
        result["reading_level"] = {
            "value" : val.value if hasattr(val, "value") else str(val),
            "source": slots.reading_level.source.value,
        }
    if slots.mood.is_filled():
        result["mood"] = {
            "categories": [c.value for c in slots.mood.categories],
            "raw"       : slots.mood.raw,
            "source"    : slots.mood.source.value,
        }
    if slots.comparison_basis.is_filled():
        result["comparison_basis"] = {
            "dimensions": [d.value for d in slots.comparison_basis.dimensions],
            "raw"       : slots.comparison_basis.raw,
            "source"    : slots.comparison_basis.source.value,
        }
    if slots.location.is_filled():
        result["location"] = {
            "region" : slots.location.region,
            "library": slots.location.library,
            "source" : slots.location.source.value,
        }
    if slots.avoid_mood.is_filled():
        result["avoid_mood"] = {
            "keywords": slots.avoid_mood.keywords,
            "source"  : slots.avoid_mood.source.value,
        }
    if slots.length.is_filled():
        result["length"] = {
            "level" : slots.length.level.value if slots.length.level else None,
            "source": slots.length.source.value,
        }

    return result


def _serialize_onboarding_applied(rag_query: dict) -> dict:
    """RAG 쿼리의 onboarding_signals에서 어떤 슬롯에 온보딩이 적용됐는지 추출"""
    ob_signals = rag_query.get("onboarding_signals", {})
    return {
        "topic"            : "topic" in ob_signals,
        "reading_level"    : "reading_level" in ob_signals,
        "disliked_keywords": "disliked_keywords" in ob_signals,
        "length_soft"      : "length_soft" in ob_signals,
        "frequent_libraries": "frequent_libraries" in ob_signals,
    }


# ── 파일 기록 ─────────────────────────────────────────────────

def _write_jsonl(path: Path, data: dict) -> None:
    """JSON Lines 형식으로 파일에 append"""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(data, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.error("로그 기록 실패 (%s): %s", path, e)


# ── 공개 인터페이스 ───────────────────────────────────────────

class SessionLogger:
    """
    세션 로그 수집기

    사용 방법:
        # chat_service.py에서
        sl = SessionLogger(session_id=..., user_id=..., original_query=...)

        # 매 턴 시작 시
        sl.log_turn(turn=1, query=..., signal_result=..., slots_before=...)

        # LLM 추출 후
        sl.update_turn(slots_after=..., slots_asked=...)

        # 세션 질문 응답 시
        sl.update_turn(user_choice=...)

        # 추천 발생 시
        sl.log_recommendation(rag_query=..., pipeline_log=..., result=...)

        # 세션 완료 시
        sl.finalize(slots=..., completed=True)
    """

    def __init__(
        self,
        session_id   : Optional[str] = None,
        user_id      : Optional[str] = None,
        original_query: str = "",
    ):
        self.session_id    = session_id or str(uuid.uuid4())[:8]
        self.user_id       = user_id
        self.original_query= original_query
        self.started_at    = _now()
        self._current_turn : Optional[TurnLog] = None
        self._turn_count   = 0

    def start_turn(
        self,
        turn         : int,
        query        : str,
        signal_result: Any = None,
        slots_before : Any = None,
    ) -> None:
        """
        새 턴 시작. 이전 턴이 있으면 먼저 flush.

        Args:
            turn        : 현재 턴 번호
            query       : 사용자 발화
            signal_result: SignalResult (있으면 로깅)
            slots_before : 이 턴 시작 시 SlotState (LLM 추출 전)
        """
        if not _LOG_ENABLED:
            return

        # 이전 턴 flush
        if self._current_turn:
            self._flush_turn()

        signal_log = None
        if signal_result:
            signal_log = {
                "categories" : {
                    k: v for k, v in vars(signal_result.categories).items()
                    if isinstance(v, bool) and v  # True인 것만
                },
                "importance" : signal_result.scores and {
                    k: getattr(signal_result.scores, k.replace("reading_level", "difficulty"), None)
                    and getattr(signal_result.scores, "difficulty" if k == "reading_level" else k).importance.value
                    for k in ["topic", "purpose", "reading_level", "mood",
                              "avoid_mood", "comparison_basis", "location", "length"]
                },
                "uncertainty": signal_result.scores and {
                    k: getattr(signal_result.scores, "difficulty" if k == "reading_level" else k).uncertainty.value
                    for k in ["topic", "purpose", "reading_level", "mood",
                              "avoid_mood", "comparison_basis", "location", "length"]
                    if hasattr(signal_result.scores, "difficulty" if k == "reading_level" else k)
                },
            }

        self._current_turn = TurnLog(
            session_id   = self.session_id,
            user_id      = self.user_id,
            turn         = turn,
            timestamp    = _now(),
            query        = query,
            signal       = signal_log,
            slots_before = _serialize_slots(slots_before) if slots_before else {},
        )
        self._turn_count = turn

    def update_turn(
        self,
        slots_after : Any  = None,
        slots_asked : list = None,
        user_choice : dict = None,
    ) -> None:
        """
        현재 턴 정보 업데이트.

        Args:
            slots_after : LLM 추출 후 SlotState
            slots_asked : 이 턴에서 질문한 슬롯 목록
            user_choice : 사용자가 선택한 선택지 dict
        """
        if not _LOG_ENABLED or not self._current_turn:
            return

        if slots_after is not None:
            self._current_turn.slots_after = _serialize_slots(slots_after)
        if slots_asked is not None:
            self._current_turn.slots_asked = slots_asked
        if user_choice is not None:
            self._current_turn.user_choice = user_choice

    def log_recommendation(
        self,
        rag_query   : dict,
        pipeline_log: Optional[PipelineLog] = None,
        result      : Optional[list] = None,
    ) -> None:
        """
        추천 결과 로깅. 추천이 발생한 턴에 호출.

        Args:
            rag_query   : build_rag_query() 결과
            pipeline_log: 파이프라인 각 단계 결과
            result      : 최종 추천 결과 리스트
        """
        if not _LOG_ENABLED or not self._current_turn:
            return

        self._current_turn.rag_query = {
            "keyword_query" : rag_query.get("keyword_query"),
            "semantic_query": rag_query.get("semantic_query"),
        }
        self._current_turn.onboarding_applied = _serialize_onboarding_applied(rag_query)

        if pipeline_log:
            self._current_turn.pipeline = asdict(pipeline_log)

        if result:
            self._current_turn.result = result

    def finalize(
        self,
        slots    : Any,
        completed: bool = True,
        result   : Optional[list] = None,
    ) -> None:
        """
        세션 완료. turns.jsonl에 마지막 턴 flush + sessions.jsonl에 요약 저장.

        Args:
            slots    : 최종 SlotState
            completed: 추천 결과 반환까지 완료했으면 True
            result   : 최종 추천 결과 (있으면 세션 요약에 포함)
        """
        if not _LOG_ENABLED:
            return

        # 마지막 턴 flush
        if self._current_turn:
            if result and not self._current_turn.result:
                self._current_turn.result = result
            self._flush_turn()

        # 세션 요약 저장
        # onboarding_applied는 마지막 추천 턴의 값 사용
        ob_applied = {}
        if self._current_turn and self._current_turn.onboarding_applied:
            ob_applied = self._current_turn.onboarding_applied

        session_log = SessionLog(
            session_id     = self.session_id,
            user_id        = self.user_id,
            started_at     = self.started_at,
            ended_at       = _now(),
            total_turns    = self._turn_count,
            original_query = self.original_query,
            slot_summary   = _serialize_slots(slots),
            onboarding_applied = ob_applied,
            final_result   = result or [],
            completed      = completed,
        )

        _write_jsonl(_SESSION_LOG_PATH, asdict(session_log))
        logger.info(
            "세션 로그 저장: session_id=%s, turns=%d, completed=%s",
            self.session_id, self._turn_count, completed,
        )

    def _flush_turn(self) -> None:
        """현재 턴 로그를 turns.jsonl에 기록"""
        if self._current_turn:
            _write_jsonl(_TURN_LOG_PATH, asdict(self._current_turn))
            self._current_turn = None
