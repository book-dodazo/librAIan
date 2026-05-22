# -*- coding: utf-8 -*-
# ============================================================
# app/modules/slot/anchor_extractor.py
#
# 변경 이력:
#   v0.1 - 최초 작성
#          비교 표현 패턴 정규식 pre-extraction
#          LLM 호출 전에 anchor 후보를 추출해 힌트로 주입
# ============================================================
"""
Anchor 후보 정규식 pre-extraction.

역할:
    LLM 호출 전에 비교 표현 패턴(처럼, 같은, 스타일의 등)으로
    anchor 후보를 추출하여 LLM 추출 프롬프트에 힌트로 주입합니다.

    LLM 단독 처리의 한계(~75-80% 천장):
    - "채식주의자", "아몬드" 같은 일반 명사형 한국 책 제목을
      LLM이 anchor로 인식하지 못하는 경우가 많음
    - 비교 표현이 있어도 anchor 위치를 놓치는 경우

    코드 보완으로 얻는 것:
    - 비교 패턴 감지 → anchor가 존재함을 LLM에 명시적으로 알림
    - 후보 텍스트 제공 → LLM이 "확인"만 하면 되는 구조로 전환
    - 저자명 vs 책 제목 휴리스틱 분류

처리 흐름:
    쿼리 문자열
    → 비교 접미사 탐색 (처럼, 같은, 스타일의, 만큼, 수준으로 등)
    → 접미사 직전 명사 구 추출 (_extract_anchor_phrase)
    → 저자명 가능성 판별 (_is_likely_author)
    → AnchorCandidate 반환

알려진 한계:
    - 외래어 복합 표제어 (드래곤 라자, 엔드 오브 타임 등)는
      마지막 단어만 추출될 수 있음
    - 이 경우에도 LLM에 힌트가 제공되어 성능 향상 기대

사용법:
    from app.modules.slot.anchor_extractor import extract_anchor_candidate

    hint = extract_anchor_candidate("채식주의자처럼 감성적인 소설")
    # → AnchorCandidate(text="채식주의자", anchor_type="book_title", ...)

    hint = extract_anchor_candidate("장하준 스타일의 경제책")
    # → AnchorCandidate(text="장하준", anchor_type="author", ...)
"""

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


# ── 결과 타입 ─────────────────────────────────────────────────

@dataclass
class AnchorCandidate:
    """비교 표현 패턴으로 추출된 anchor 후보"""
    text       : str    # 추출된 anchor 후보 텍스트
    anchor_type: str    # "book_title" | "author" | "ambiguous"
    confidence : float  # 0.0 ~ 1.0 (0.55 미만이면 힌트 생략)
    pattern    : str    # 트리거된 비교 표현


# ── 비교 패턴 정의 ─────────────────────────────────────────────
# 각 항목: (접미사 문자열, 패턴 레이블, 기본 anchor_type)
# 우선순위 순서 — 더 구체적인 패턴 먼저
_COMPARISON_SUFFIXES: list[tuple[str, str, str]] = [
    # "스타일의" / "스타일로" → 저자명 연관성 높음
    ("스타일의", "스타일의", "ambiguous"),
    ("스타일로", "스타일의", "ambiguous"),
    # "처럼" → 책 제목 연관성 높음 (직접 접착)
    ("처럼",     "처럼",     "book_title"),
    # "만큼" → 짧으면 저자, 길면 책 제목 (휴리스틱 판별)
    ("만큼",     "만큼",     "ambiguous"),
    # "수준으로" / "수준의" → 품질/깊이 비교 → 주로 책 제목
    ("수준으로", "수준으로", "book_title"),
    ("수준의",   "수준으로", "book_title"),
    # "느낌으로" / "느낌의"
    ("느낌으로", "느낌으로", "book_title"),
    ("느낌의",   "느낌으로", "book_title"),
    # "같은" / "비슷한" / "유사한"
    ("같은",     "같은",     "book_title"),
    ("비슷한",   "비슷한",   "book_title"),
    ("유사한",   "비슷한",   "book_title"),
    # "정도로" / "정도의"
    ("정도로",   "정도로",   "book_title"),
    ("정도의",   "정도로",   "book_title"),
]

# ── 한국어 성씨 집합 ──────────────────────────────────────────
# 성이 1자인 한국 성씨 (저자명 판별 휴리스틱)
_KOREAN_SURNAMES: frozenset = frozenset({
    "김", "이", "박", "최", "정", "강", "조", "윤", "장", "임",
    "한", "오", "서", "신", "권", "황", "안", "송", "류", "홍",
    "전", "고", "문", "양", "손", "배", "백", "허", "유",
    "남", "심", "노", "하", "곽", "성", "차", "주", "우", "구",
    "민", "나", "진", "지", "엄", "채", "원", "천", "방",
    "공", "현", "함", "변", "염", "여", "추", "도", "소",
    "석", "선", "설", "마", "길", "연", "위", "표", "명", "기",
})

# ── 관형사형 어미 / 수식어 판별 집합 ─────────────────────────
# "불편한" → "한", "82년생" → "생" 등
# 직전 eojeol이 수식어임을 나타내는 어미/접미사
_ADNOMINAL_ENDINGS: frozenset = frozenset({
    "한", "은", "는", "인", "된", "할", "올",   # 관형사형 어미
    "생", "대",                                    # 숫자 접미어 (82년생, 20대)
})

# ── anchor 후보 제외 단어 집합 ───────────────────────────────
# 비교 표현 앞에 위치하지만 실제 책 제목/저자명이 아닌 대명사/한정사
# (false positive 방지)
_ANCHOR_STOPWORDS: frozenset = frozenset({
    # 부정 대명사
    "아무것", "아무거나", "아무것도", "무엇", "무언가", "뭔가", "뭐",
    # 지시 대명사
    "이것", "그것", "저것", "이런것", "그런것", "저런것",
    "이게", "그게", "저게", "이거", "그거", "저거",
    # 관형 대명사
    "어떤것", "모든것", "다른것", "같은것",
    # 인칭 관련
    "나", "저", "그", "이",
    # 책 장르/형식 일반 명사 — anchor로 오인될 수 있는 단어
    # 예: "소설처럼 읽히는 인문서" → "소설"이 anchor가 되면 안 됨
    "책", "소설", "에세이", "시집", "작품", "글", "이야기",
    "만화", "영화", "드라마", "음악",
    # 의존명사 단독 (조합 책 제목은 _DEPENDENT_NOUNS 케이스에서 처리)
    "것", "수", "때", "줄",
})

# ── 흔한 조사 (anchor 후보 후처리 시 제거) ───────────────────
# 길이 내림차순 정렬 (더 긴 조사 먼저 매칭)
_JOSA_SUFFIXES: list[str] = sorted([
    "에서", "으로", "이랑", "에게", "까지", "부터",
    "로", "을", "를", "의", "에", "와", "과", "랑",
    "은", "는", "이", "가", "도", "만",
], key=len, reverse=True)


# ── 핵심 함수 ──────────────────────────────────────────────────

def extract_anchor_candidate(query: str) -> Optional[AnchorCandidate]:
    """
    비교 표현 패턴으로 anchor 후보를 pre-extraction합니다.

    LLM 호출 전에 실행되어 추출 결과를 힌트로 주입.

    Args:
        query: 사용자 발화 원문

    Returns:
        AnchorCandidate — 매칭된 후보 정보
        None — 비교 표현 패턴 없음 또는 신뢰 가능한 후보 없음

    예시:
        "채식주의자처럼 감성적인 소설"
            → AnchorCandidate(text="채식주의자", anchor_type="book_title", confidence=0.75)

        "장하준 스타일의 경제책"
            → AnchorCandidate(text="장하준", anchor_type="author", confidence=0.75)

        "드래곤 라자 같은 판타지"
            → AnchorCandidate(text="드래곤 라자", anchor_type="book_title", confidence=0.75)
            (2-word title은 best-effort)

        "82년생 김지영처럼 사회적 메시지 소설"
            → AnchorCandidate(text="82년생 김지영", anchor_type="book_title", confidence=0.75)
    """
    query_stripped = query.strip()

    for suffix, pattern_name, default_type in _COMPARISON_SUFFIXES:
        idx = query_stripped.find(suffix)

        # 접미사 없거나 문장 맨 앞에 있으면 건너뜀
        if idx <= 0:
            continue

        # 접미사 앞 텍스트
        before = query_stripped[:idx].rstrip()
        if not before:
            continue

        # 명사 구 추출 (마지막 1-3 eojeol)
        candidate = _extract_anchor_phrase(before)
        if not candidate:
            continue

        # 최소/최대 길이 필터
        if len(candidate) < 2 or len(candidate) > 15:
            continue

        # 조사 후처리 (예: "아몬드가" → "아몬드")
        candidate = _strip_josa(candidate)
        if len(candidate) < 2:
            continue

        # 대명사/한정사 필터 (false positive 방지)
        # 예: "아무것도 같은" → "아무것" → stopword → skip
        if candidate in _ANCHOR_STOPWORDS:
            logger.debug("앵커 후보 stopword 필터: '%s' — 건너뜀", candidate)
            continue

        # 저자명 여부 판별
        is_author, author_conf = _is_likely_author(candidate)

        # 패턴별 타입 결정
        if pattern_name == "스타일의":
            # "스타일의/로" — 저자 스타일 표현에 훨씬 많이 쓰임
            if is_author and author_conf >= 0.6:
                anchor_type = "author"
                confidence  = author_conf
            else:
                anchor_type = "book_title"
                confidence  = 0.60
        elif default_type == "book_title":
            if is_author and author_conf >= 0.75:
                # 명확한 저자명이면 author로 분류
                anchor_type = "author"
                confidence  = author_conf
            else:
                anchor_type = "book_title"
                confidence  = 0.75
        else:  # ambiguous (만큼 등)
            anchor_type = "author" if is_author else "book_title"
            confidence  = author_conf if is_author else 0.60

        logger.debug(
            "앵커 후보 pre-extraction: '%s' (%s, conf=%.2f) — 패턴='%s'",
            candidate, anchor_type, confidence, pattern_name,
        )

        return AnchorCandidate(
            text       = candidate,
            anchor_type= anchor_type,
            confidence = confidence,
            pattern    = pattern_name,
        )

    return None


# ── 내부 헬퍼 ─────────────────────────────────────────────────

def _extract_anchor_phrase(text: str) -> Optional[str]:
    """
    비교 접미사 앞 텍스트에서 anchor 명사 구(최대 5 eojeol)를 추출합니다.

    전략:
        0. [Special] 의존명사(것/수/때/줄) + 관형형 어미(는/은/ㄹ) 패턴
           → 전체 명사구가 책 제목일 가능성 높음 (예: "지혜롭게 나이 든다는 것")
           → 길이 범위(2~15자) 안에서 최대한 많은 단어 포함
        1. 마지막 eojeol을 기본 후보로 설정
        2. 직전 eojeol이 관형사형 수식어처럼 보이면 함께 포함
           (예: "불편한 편의점" — "불편한" ends with "한")
        3. 외래어 복합 표제어는 best-effort (마지막 2-3 eojeol)

    알려진 한계:
        - "드래곤 라자" 같은 외래어 복합어는 마지막 단어("라자")만 추출될 수 있음
        - 이 경우에도 LLM 힌트로서 partial 정보 제공 효과 있음
    """
    # 의존명사: 동사 관형형 + 의존명사 → 전체가 명사구(책 제목)
    _DEPENDENT_NOUNS = frozenset({"것", "수", "때", "줄", "데", "바"})
    # 관형형 어미 (의존명사 앞에 붙는 어미) — 수식형과 구분
    _NOMI_VERB_ENDINGS = frozenset({"는", "은", "ㄴ", "을", "ㄹ"})

    parts = text.strip().split()
    if not parts:
        return None

    last = parts[-1]

    # 단어가 1개면 그대로 반환 (단, 의존명사 단독은 의미 없음)
    if len(parts) == 1:
        if last in _DEPENDENT_NOUNS:
            return None
        return last if len(last) >= 2 else None

    second_last = parts[-2]

    # ── [Step 0] 의존명사 패턴 특수 처리 ─────────────────────────
    # "든다는 것", "않을 것", "살아온 것" 등
    # → 직전 단어가 동사 관형형이면 전체 앞 구를 포함
    if last in _DEPENDENT_NOUNS and any(second_last.endswith(e) for e in _NOMI_VERB_ENDINGS):
        for n in range(min(5, len(parts)), 1, -1):
            phrase = " ".join(parts[-n:])
            if 2 <= len(phrase) <= 15:
                return phrase
        # 길이 범위 밖이면 일반 로직으로 fall-through

    # ── [Step 1] 직전 단어가 수식어인지 판별 ─────────────────────
    if _looks_like_adnominal(second_last):
        candidate2 = f"{second_last} {last}"

        # 세 번째 단어도 수식어인지 확인 (최대 3 eojeol까지)
        if len(parts) >= 3:
            third_last = parts[-3]
            if _looks_like_adnominal(third_last):
                candidate3 = f"{third_last} {second_last} {last}"
                if 2 <= len(candidate3) <= 15:
                    return candidate3

        if 2 <= len(candidate2) <= 15:
            return candidate2

    # ── [Step 2] 기본: 마지막 단어 반환 ─────────────────────────
    return last if len(last) >= 2 else None


# 인칭대명사 어근 — "나는", "저는", "그는" 같은 패턴을 관형어로 오인 방지
_PRONOUN_STEMS: frozenset = frozenset({"나", "저", "그", "이", "당"})


def _looks_like_adnominal(word: str) -> bool:
    """
    단어가 다음 명사를 수식하는 관형어처럼 보이는지 판별.

    기준 (우선순위 순서):
        1. 관형사형 어미로 끝남 → True
           (길이에 관계없이 먼저 확인 — "편한" 2글자도 포함)
           예외: 2글자 인칭대명사+조사 ("나는", "저는", "그는") → False
        2. 1글자 이하 → False
        3. 2글자: 숫자 포함이면 True (20, 80 같은 숫자 접두어)
        4. 3글자 이상: 조사 제거 후 2글자 이상 → 명사+격조사 패턴
           예: "소년이" → strip "이" → "소년" (2글자) → True
               "나를"  → strip "를" → "나"   (1글자) → False

    수정 이력:
        - "편한" (2글자 관형사형) 처리를 위해 길이 체크 전에 어미 체크 선행
        - "나는", "저는" 오인 방지를 위해 2글자 인칭대명사+는/은 예외 추가
    """
    if not word:
        return False

    # [1] 관형사형 어미 체크 — 길이보다 먼저 확인 ("편한" 2글자 포함)
    if any(word.endswith(e) for e in _ADNOMINAL_ENDINGS):
        # 예외: 2글자 인칭대명사+는/은 ("나는", "저는", "그는") → 조사이므로 제외
        if len(word) == 2 and word[-1] in ("는", "은") and word[0] in _PRONOUN_STEMS:
            return False
        return True

    length = len(word)

    # [2] 1글자 이하 → 기능어 가능성 높음
    if length <= 1:
        return False

    # [3] 2글자: 숫자 포함 (20대, 80년대 접두어)
    if length == 2:
        return any(c.isdigit() for c in word)

    # [4] 3글자 이상: 조사 제거 후 2글자 이상 → 명사+격조사 패턴
    # "소년이" → strip "이" → "소년" (2글자) → True
    # "나를"   → strip "를" → "나"   (1글자) → False
    stripped = _strip_josa(word)
    if stripped != word and len(stripped) >= 2:
        return True

    return False


def is_likely_author(candidate: str) -> tuple[bool, float]:
    """
    후보 문자열이 저자명일 가능성을 (is_author, confidence)로 반환합니다.
    (filler.py 등 외부 모듈에서 사용하는 public alias)
    """
    return _is_likely_author(candidate)


def _is_likely_author(candidate: str) -> tuple[bool, float]:
    """
    후보 문자열이 저자명일 가능성을 (is_author, confidence)로 반환합니다.

    휴리스틱 기준:
        - 한국 성씨(1자) + 이름(1-3자) = 2-4글자 한국 이름 → 높은 확신
        - 공백 포함 + 2-3 파트 + 각 파트 2-4글자 → 외국 저자명 스타일
        - 숫자 포함 → 책 제목 (82년생 김지영 등)
        - 5글자 초과 단일 단어 → 책 제목 가능성 높음

    Returns:
        (is_author: bool, confidence: float 0.0~1.0)
    """
    stripped = candidate.strip()
    length   = len(stripped)

    # 최소 길이
    if length < 2:
        return False, 0.1

    # 숫자 포함 → 책 제목 (82년생 김지영, 1984 등)
    if any(c.isdigit() for c in stripped):
        return False, 0.85

    # 공백 있는 경우 — 외국 저자명 vs 다중단어 책 제목 판별
    if " " in stripped:
        parts = stripped.split()
        n = len(parts)
        # 2-3 파트, 각 파트 2-4글자 → 외국 저자명 스타일 (무라카미 하루키 등)
        if n in (2, 3) and all(2 <= len(p) <= 4 for p in parts):
            return True, 0.65
        # 파트 중 하나가 긴 경우 → 책 제목 가능성
        if any(len(p) > 5 for p in parts):
            return False, 0.70
        return False, 0.50

    # 단일 단어 — 한국 저자명 판별
    if length in (2, 3, 4):
        if stripped[0] in _KOREAN_SURNAMES:
            # 2글자: 성+1자 이름 (한강, 김훈) → 높은 확신
            # 3글자: 성+2자 이름 (박경리, 황석영) → 중간
            # 4글자: 성+3자 이름 또는 저자명 — 가능
            conf_map = {2: 0.82, 3: 0.75, 4: 0.65}
            return True, conf_map.get(length, 0.60)

    # 5글자 초과 단일 단어 → 대체로 책 제목
    if length > 5:
        return False, 0.30

    return False, 0.40


def _strip_josa(text: str) -> str:
    """
    한국어 조사를 제거합니다.

    예) "아몬드가" → "아몬드", "채식주의자를" → "채식주의자"

    주의:
        2글자 이상 남을 때만 제거 (너무 짧아지면 원본 유지).
    """
    for josa in _JOSA_SUFFIXES:
        if text.endswith(josa):
            stripped = text[:-len(josa)]
            if len(stripped) >= 2:
                return stripped
    return text
