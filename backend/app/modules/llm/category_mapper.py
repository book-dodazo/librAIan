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


def _normalize(s: str) -> str:
    """공백 제거 정규화 — "현대 소설" → "현대소설"."""
    return "".join(s.split())


# 정규화된 fine → coarse 역방향 매핑 (공백 제거 기준)
_FINE_TO_COARSE_NORMALIZED: dict[str, str] = {
    _normalize(k): v for k, v in _FINE_TO_COARSE.items()
}


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
        get_coarse_category("한국소설")  → "소설"
        get_coarse_category("현대 소설") → "소설"  (공백 정규화)
        get_coarse_category("심리학")    → "인문"
        get_coarse_category("SF")        → None  (매핑 없음)
    """
    if not fine:
        return None

    # 1. 정확한 매핑 시도
    if fine in _FINE_TO_COARSE:
        coarse = _FINE_TO_COARSE[fine]
        logger.debug("카테고리 매핑 성공: %s → %s", fine, coarse)
        return coarse

    # 2. 공백 제거 후 재시도 ("현대 소설" → "현대소설")
    normalized = _normalize(fine)
    if normalized in _FINE_TO_COARSE_NORMALIZED:
        coarse = _FINE_TO_COARSE_NORMALIZED[normalized]
        logger.debug("카테고리 공백 정규화 매핑: %s → %s", fine, coarse)
        return coarse

    # 3. 부분 매칭 시도 (정규화된 키 기준)
    # 오매핑 방지: 1글자 제외 (한글 2글자 = 과학/소설/인문 등 허용)
    if len(normalized) >= 2:
        for norm_key, coarse_val in _FINE_TO_COARSE_NORMALIZED.items():
            if norm_key.startswith(normalized):
                logger.debug("카테고리 부분 매핑: %s → %s", fine, coarse_val)
                return coarse_val

    # 4. 매핑 실패 → None 반환 (LLM 폴백은 호출부에서 처리)
    logger.debug("카테고리 매핑 실패: %s → None (LLM 폴백 필요)", fine)
    return None


def get_canonical_fine(free_form: str) -> Optional[str]:
    """
    자유형 주제어 → 카테고리 트리의 정규 중분류(cate_depth2) 값으로 변환

    1. 정확 매칭: "한국소설" → "한국소설"
    2. 부분 매칭: 트리 키가 입력값으로 시작하거나, 입력값이 트리 키로 시작하는 경우
    3. 실패 → None (자유형 그대로 유지)

    예)
        get_canonical_fine("한국소설") → "한국소설"
        get_canonical_fine("한국사")   → "한국사" (정확 매칭)
        get_canonical_fine("SF")       → None (매핑 없음)
        get_canonical_fine("파이썬")   → None (트리에 없음)
    """
    if not free_form:
        return None

    # 1. 정확 매칭
    if free_form in _FINE_TO_COARSE:
        return free_form

    # 2. 공백 제거 후 정규화 매칭 ("현대 소설" → "현대소설")
    normalized = _normalize(free_form)
    if normalized in _FINE_TO_COARSE_NORMALIZED:
        canonical = next(k for k in _FINE_TO_COARSE if _normalize(k) == normalized)
        logger.debug("중분류 공백 정규화 매칭: %s → %s", free_form, canonical)
        return canonical

    # 3. 부분 매칭 (2글자 이상, 정규화 기준)
    if len(normalized) >= 2:
        for fine_key in _FINE_TO_COARSE:
            norm_key = _normalize(fine_key)
            if norm_key.startswith(normalized) or normalized.startswith(norm_key):
                logger.debug("중분류 부분 매칭: %s → %s", free_form, fine_key)
                return fine_key

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
