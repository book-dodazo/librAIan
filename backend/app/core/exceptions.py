# -*- coding: utf-8 -*-
# ============================================================
# app/core/exceptions.py
#
# 변경 이력:
#   v0.1 - 최초 작성
# ============================================================
"""
커스텀 예외 클래스 정의

HTTPException 대신 도메인 의미가 명확한 예외를 사용하고,
라우터 레벨 핸들러에서 HTTP 상태 코드로 변환합니다.

흐름:
    모듈(LLM 호출 실패) → LLMCallError 발생
    → 서비스 레이어에서 catch
    → 라우터에서 HTTPException 503 으로 변환
"""


class LLMCallError(Exception):
    """CLOVA Studio API 호출 자체가 실패했을 때"""
    pass


class IntentParseError(Exception):
    """LLM 응답을 JSON으로 파싱할 수 없을 때 (폴백 처리됨)"""
    pass
