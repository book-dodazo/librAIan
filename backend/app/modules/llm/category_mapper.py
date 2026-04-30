# -*- coding: utf-8 -*-
# ============================================================
# app/modules/llm/category_mapper.py
#
# 변경 이력:
#   v0.1 - 최초 작성
#          category_tree.json 로드 후 중분류 → 대분류 역방향 매핑 자동 생성
#          카테고리에 없는 값은 LLM 폴백 또는 null 처리
# ============================================================
"""
카테고리 매핑 모듈

역할:
    LLM이 질의에서 추출한 topic (fine/subject) 을
    category_tree.json 기준 대분류(coarse) 로 변환합니다.

처리 순서:
    1. 중분류가 매핑 테이블에 있으면 → 대분류 즉시 반환
    2. 없으면 → LLM이 대분류 목록 보고 판단
    3. LLM도 모호하면 → None 반환 (전체 범위 검색)

사용법:
    from app.modules.llm.category_mapper import get_coarse_category
    coarse = get_coarse_category("한국소설")  # → "소설"
    coarse = get_coarse_category("SF")        # → None (매핑 없음, LLM 폴백)
"""
import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── 카테고리 트리 로드 ─────────────────────────────────────────
# 이 파일 기준 상대 경로로 category_tree.json 을 읽어요.
# 실제 프로젝트에서는 경로를 config 로 관리하는 게 좋습니다.
_CATEGORY_TREE_PATH = Path(__file__).parent / "category_tree.json"


def _load_category_tree() -> dict:
    """category_tree.json 로드"""
    try:
        with open(_CATEGORY_TREE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error(
            "category_tree.json 을 찾을 수 없습니다: %s", _CATEGORY_TREE_PATH
        )
        return {}


def _build_fine_to_coarse(tree: dict) -> dict[str, str]:
    """
    대분류 → [중분류] 구조를 중분류 → 대분류 역방향으로 변환합니다.

    예)
        입력: {"소설": ["한국소설", "영미소설", ...], ...}
        출력: {"한국소설": "소설", "영미소설": "소설", ...}
    """
    mapping = {}
    for coarse, fines in tree.items():
        for fine in fines:
            mapping[fine] = coarse
    return mapping


# 모듈 로드 시 한 번만 생성
_TREE: dict = _load_category_tree()
_FINE_TO_COARSE: dict[str, str] = _build_fine_to_coarse(_TREE)
COARSE_CATEGORIES: list[str] = list(_TREE.keys())  # 대분류 목록 (LLM 폴백용)


def get_coarse_category(fine: str) -> Optional[str]:
    """
    중분류 → 대분류 변환 (매핑 테이블 기반)

    Args:
        fine: LLM이 질의에서 추출한 중분류 또는 주제어
              예) "한국소설", "심리학", "SF"

    Returns:
        대분류 문자열 또는 None
        - 매핑 성공: "소설", "인문" 등
        - 매핑 실패: None → LLM 폴백 또는 전체 범위 검색

    예시:
        get_coarse_category("한국소설") → "소설"
        get_coarse_category("심리학")   → "인문"
        get_coarse_category("SF")       → None  (매핑 없음)
    """
    if not fine:
        return None

    # 1. 정확한 매핑 시도
    if fine in _FINE_TO_COARSE:
        coarse = _FINE_TO_COARSE[fine]
        logger.debug("카테고리 매핑 성공: %s → %s", fine, coarse)
        return coarse

    # 2. 부분 매칭 시도
    # 주의: 오매핑 방지를 위해 입력값이 키의 앞부분과 일치하는 경우만 허용
    # 예) "한국 근현대사" → "한국사" 포함 X, "역사/문화" 키워드 포함 O
    for fine_key, coarse_val in _FINE_TO_COARSE.items():
        # fine_key 가 입력값으로 시작하는 경우만 매칭
        # 예) fine="한국사", fine_key="한국사" → 정확 매칭 (위에서 처리됨)
        # 너무 짧은 단어(2글자 이하)는 부분 매칭 제외 (오매핑 방지)
        if len(fine) > 2 and fine_key.startswith(fine):
            logger.debug("카테고리 부분 매핑: %s → %s (via %s)", fine, coarse_val, fine_key)
            return coarse_val

    # 3. 매핑 실패 → None 반환 (LLM 폴백은 호출부에서 처리)
    logger.debug("카테고리 매핑 실패: %s → None (LLM 폴백 필요)", fine)
    return None


def get_all_coarse_categories() -> list[str]:
    """
    대분류 목록 반환 (LLM 폴백 시 프롬프트에 전달용)

    예시:
        ["종교", "어린이(초등)", "취업/수험서", "자기계발", ...]
    """
    return COARSE_CATEGORIES


def get_fines_by_coarse(coarse: str) -> list[str]:
    """
    대분류 → 중분류 목록 반환 (온보딩 UI 렌더링용)

    예시:
        get_fines_by_coarse("소설")
        → ["고전소설/문학선", "영미소설", "한국소설", ...]
    """
    return _TREE.get(coarse, [])


def is_valid_coarse(coarse: str) -> bool:
    """대분류가 유효한지 확인"""
    return coarse in _TREE


def is_valid_fine(fine: str) -> bool:
    """중분류가 유효한지 확인"""
    return fine in _FINE_TO_COARSE
