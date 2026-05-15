# -*- coding: utf-8 -*-
"""
RAG 쿼리 구조 예시 (팀원 공유용)

시나리오:
    "불편한 편의점처럼 따뜻하고 읽기 쉬운 소설 추천해줘.
     요즘 너무 지쳐 있어서 힐링이 필요하거든.
     너무 무거운 건 싫고, 300페이지 이하면 좋겠어.
     지금 당장 마포구립서강도서관에서 빌릴 수 있는 거로."

이 예시는 build_rag_query() 가 반환하는 딕셔너리의 전체 구조를 보여줍니다.
실제 값은 LLM + slot filler 가 채워주며, 여기서는 위 시나리오 기준의 고정값입니다.
"""

rag_query_example = {

    # ──────────────────────────────────────────────────────────────
    # BM25 검색기 전달 키워드 목록
    #
    # - LLM 이 slot 요약문 보고 생성 (LLM 실패 시 slot 값 직접 추출로 폴백)
    # - BM25.py 에서 역색인 키워드 매칭에 사용
    # - 최대 7개 (폴백 시 _fallback_keywords 참고)
    # - 일반적으로 중분류(fine), 세부주제(subject), 감정/목적 키워드 포함
    # ──────────────────────────────────────────────────────────────
    "keyword_query": [
        "소설",          # topic.fine (중분류)
        "힐링",          # purpose/mood 맥락에서 LLM 생성
        "가볍고 쉽게 읽히는",  # reading_level=easy 자연어 표현
        "따뜻한",        # comparison_basis (분위기 기준)
        "불편한 편의점",  # anchor (기준 책 제목)
    ],

    # ──────────────────────────────────────────────────────────────
    # Dense(벡터) 검색기 전달 자연어 쿼리
    #
    # - LLM 이 slot 요약문 보고 자연어 문장으로 생성
    # - Refinement 시: 기존 쿼리 + 수정 사항만 앞뒤에 붙여서 갱신
    #   예) "더 짧은 거로" → "짧은 [기존쿼리]"
    # ──────────────────────────────────────────────────────────────
    "semantic_query": (
        "지쳐있을 때 읽기 좋은 가볍고 따뜻한 소설, "
        "불편한 편의점처럼 힐링되는 국내 소설 추천"
    ),

    # ──────────────────────────────────────────────────────────────
    # 메타데이터 하드 필터 (BM25 + Dense 공통)
    #
    # cate_depth1   : 대분류 필터 — topic.coarse 에서 생성
    #                 BM25.py 가 이 값으로 먼저 후보를 좁힘
    #                 없으면 전체 카테고리 대상으로 검색
    #
    # target_reader : 대상 독자 필터 — constraints type="target_reader" 에서 생성
    #                 예) ["성인", "중학생"]
    #                 없으면 이 필드 자체가 딕셔너리에 포함되지 않음
    #
    # custom_constraints : 하드 필터 불가 자연어 제약 (후처리용 참고)
    #                      예) ["번역서 제외", "수상작만"]
    #                      Reranker 또는 후처리 단계에서 참고
    # ──────────────────────────────────────────────────────────────
    "filters": {
        "cate_depth1": ["소설"],          # topic.coarse 리스트
        # "target_reader": ["성인"],      # 대상 독자 필터 (없으면 키 자체 없음)
        # "custom_constraints": ["번역서 제외"],  # 자연어 제약 (없으면 키 자체 없음)
    },

    # ──────────────────────────────────────────────────────────────
    # 수치 기반 하드 제약 (BM25.py constraints 키 기준)
    #
    # page_range  : 페이지 수 제약 — constraints type="page_range" 에서 생성
    #               operator 종류: "lte"(이하), "gte"(이상), "lt"(미만), "gt"(초과), "eq"(같음)
    #               복수 조건 가능 예) 200 이상 400 이하
    #
    # pub_year    : 출판연도 제약 — constraints type="pub_year" 에서 생성
    #               operator 종류: "gte"(이후), "lte"(이전)
    #               예) 2020년 이후 출판된 책
    #
    # author      : 포함할 저자 — constraints type="author" 에서 생성
    #               BM25.py: constraints["author"]
    #
    # author_non  : 제외할 저자 — constraints type="nonauthor" 에서 생성
    #               BM25.py: constraints["author_non"]
    #
    # 값이 없는 항목은 딕셔너리에 포함되지 않음
    # ──────────────────────────────────────────────────────────────
    "constraints": {
        "page_range": [
            {"operator": "lte", "value": 300}  # "300페이지 이하"
            # 복수 조건 예시: {"operator": "gte", "value": 200}
        ],
        # "pub_year": [{"operator": "gte", "value": 2020}],  # "2020년 이후"
        # "author": ["김초엽"],                               # "김초엽 작가 책으로"
        # "author_non": ["기욤 뮈소"],                        # "기욤 뮈소 빼줘"
    },

    # ──────────────────────────────────────────────────────────────
    # Reranker 스코어 보정 (소프트 신호 — 필터 아님)
    #
    # cate_depth2 : 중분류 boost — topic.fine 에서 생성
    #               이 리스트에 해당하는 책에 가산점 부여
    #               예) ["한국 소설"] → 한국 소설 결과를 상위로
    #
    # subject     : 세부 주제 boost — topic.subject 에서 생성
    #               예) ["힐링", "일상"] → 해당 태그 책에 가산점
    #
    # 없으면 빈 딕셔너리 {} 반환
    # ──────────────────────────────────────────────────────────────
    "score_boost": {
        "cate_depth2": ["한국 소설"],   # topic.fine 리스트
        # "subject": ["힐링", "일상"],  # topic.subject 리스트 (있을 때만)
    },

    # ──────────────────────────────────────────────────────────────
    # 도서관 대출 가능 여부 조회 플래그
    #
    # True  : 정보나루 API 호출 → 실시간 대출 가능 도서만 필터
    # False : API 호출 안 함 (대출 가능 여부 무관)
    #
    # 트리거: 슬롯 constraints type="availability" 또는
    #         "지금 빌릴 수 있는", "대출 가능한" 등의 표현 감지 시
    # location 슬롯의 region/library 와 함께 사용
    # ──────────────────────────────────────────────────────────────
    "availability_required": True,

    # ──────────────────────────────────────────────────────────────
    # 기준점 앵커 목록 (슬롯 아님 — 질의에서 직접 파싱)
    #
    # value : 앵커 텍스트 (책 제목, 저자명, 시리즈명, 도서관명)
    # type  : 앵커 유형
    #         "book_title" — 책 제목 ("불편한 편의점")
    #         "author"     — 저자명 ("김호연")
    #         "series"     — 시리즈명 ("해리포터 시리즈")
    #         "library"    — 도서관명 ("마포구립서강도서관")
    #
    # 앵커가 없으면 None 반환
    # comparison_basis 슬롯과 함께 사용:
    #   anchor 있음 + comparison_basis 있음 → "~처럼 [기준] 비슷한 책" 검색
    #   anchor 있음 + comparison_basis 없음 → 세션 질문으로 비교 기준 확인
    # ──────────────────────────────────────────────────────────────
    "anchors": [
        {"value": "불편한 편의점", "type": "book_title"},
        # {"value": "마포구립서강도서관", "type": "library"},  # 도서관 앵커 예시
    ],

    # ──────────────────────────────────────────────────────────────
    # 세션 신호 (Reranker 에 높은 가중치로 전달)
    #
    # 현재 세션에서 사용자가 직접 말한/표현한 슬롯 값만 포함
    # 비어 있는 슬롯은 이 딕셔너리에 포함되지 않음
    #
    # purpose        : 독서 목적 (PurposeValue Enum 값)
    #                  "학습" / "교양" / "재미" / "실용"
    #
    # reading_level  : 읽기 부담 (ReadingLevelValue Enum 값)
    #                  "easy"(가볍고 쉽게) / "medium"(적당한 깊이) / "hard"(깊이 있는)
    #
    # mood           : 감정/상태 카테고리 리스트 (MoodCategory Enum 값)
    #                  복합 감정 지원 (예: 지치고 불안한 → 2개)
    #                  주요 값: "negative_exhausted"(소진), "negative_anxious"(불안),
    #                           "recovery_comfort"(위로), "recovery_relax"(이완),
    #                           "positive_excited"(설렘), "positive_energized"(활기)
    #
    # location       : 지역/도서관 정보
    #                  region  — 지역명 (예: "마포구")
    #                  library — 도서관명 (예: "마포구립서강도서관")
    #                  availability_required=True 일 때 API 조회에 사용
    #
    # avoid_mood     : 피하고 싶은 분위기 키워드 리스트
    #                  예: ["너무 무거운", "너무 잔인한"]
    #                  Reranker 가 해당 분위기 책에 감점 부여
    #
    # length         : 분량 수준 (LengthLevel Enum 값)
    #                  "short"(짧은) / "medium"(적당한) / "long"(긴)
    #                  page_range(수치 하드 필터)와 달리 소프트 신호
    #
    # comparison_basis: 비교 기준 축 (anchor 와 함께 활성화)
    #                  dimensions — ComparisonDimension Enum 값 리스트
    #                               "mood"(분위기), "topic"(주제), "style"(문체),
    #                               "difficulty"(난이도), "depth"(깊이), "custom"(직접입력)
    #                  raw        — 원문 표현 보존 (디버깅용)
    #
    # 중복 제외 항목:
    #   topic     → score_boost["cate_depth2"] 와 동일하므로 제외
    #   anchor    → 최상위 rag_query["anchors"] 와 동일하므로 제외
    #   nonauthor → constraints["author_non"] 와 동일하므로 제외
    # ──────────────────────────────────────────────────────────────
    "session_signals": {
        "purpose"      : "재미",                    # PurposeValue: "학습" / "교양" / "재미" / "실용"
        "reading_level": "easy",                    # ReadingLevelValue: "easy" / "medium" / "hard"
        "mood"         : ["negative_exhausted"],    # MoodCategory 값 리스트 (복합 감정 가능)
        "location"     : {
            "region" : None,                        # 지역명 (예: "마포구") — 없으면 None
            "library": "마포구립서강도서관",         # 도서관명 — 없으면 None
        },
        "avoid_mood"   : ["너무 무거운"],            # 회피 분위기 키워드 리스트
        "length"       : "short",                   # LengthLevel: "short" / "medium" / "long"
        "comparison_basis": {                       # anchor 감지 + 유사도 표현 있을 때만 포함
            "dimensions": ["mood"],                 # ComparisonDimension 값 리스트
            "raw"       : "불편한 편의점처럼 따뜻한", # 원문 표현 보존
        },
    },

    # ──────────────────────────────────────────────────────────────
    # 온보딩 신호 (Reranker 에 낮은 가중치로 전달)
    #
    # 사용 조건 (MINICORN uncertainty 기반):
    #   uncertainty HIGH 슬롯에 한해서만 온보딩 데이터를 보조 신호로 활용
    #   uncertainty LOW  슬롯은 세션 신호가 충분하므로 온보딩 무시
    #   세션 신호 > 온보딩 신호 (항상 세션 우선)
    #
    # topic            : 온보딩 preferred_categories 대분류 리스트
    #                    세션 topic 슬롯이 비어있고 uncertainty HIGH 일 때만 포함
    #                    예: ["소설", "인문"] → 이 카테고리 책에 약한 가산점
    #
    # page_range_soft  : 온보딩 preferred_length 를 수치로 변환한 소프트 신호
    #                    세션에 page_range 하드 제약이 없을 때만 포함
    #                    "300p 이하" → {"operator": "lte", "value": 300}
    #                    page_range(constraints 하드 필터)보다 약한 신호
    #
    # disliked_keywords: 온보딩 회피 태그 리스트
    #                    세션 avoid_mood/topic 과 충돌 없을 때만 포함
    #                    충돌 예: 세션 "전쟁 역사책" + 온보딩 "너무 잔인한" → 제외
    #                    예: ["dark", "tense", "너무 잔인한"]
    #
    # frequent_libraries: 온보딩 자주 방문 도서관 리스트
    #                     availability_required=True 일 때만 포함
    #                     예: ["마포구립서강도서관", "은평구립도서관"]
    #
    # 온보딩 없거나 모든 슬롯 uncertainty LOW 이면 빈 딕셔너리 {} 반환
    # ──────────────────────────────────────────────────────────────
    "onboarding_signals": {
        # 이 시나리오에서는 세션에서 topic/location 이 직접 채워졌으므로
        # uncertainty LOW → 온보딩 신호 최소화
        "frequent_libraries": ["마포구립서강도서관"],  # availability_required=True 이므로 포함
        # "topic"            : ["소설", "에세이"],     # topic uncertainty HIGH 일 때만 포함
        # "disliked_keywords": ["너무 잔인한"],        # 세션과 충돌 없을 때만 포함
        # "page_range_soft"  : {"operator": "lte", "value": 300},  # 세션에 page_range 없을 때만
    },
}


# ──────────────────────────────────────────────────────────────────
# 각 키가 RAG 파이프라인에서 어디에 쓰이는지 요약
# ──────────────────────────────────────────────────────────────────
#
# ┌─────────────────────┬──────────────────────────────────────────┐
# │ 키                  │ 사용처                                    │
# ├─────────────────────┼──────────────────────────────────────────┤
# │ keyword_query       │ BM25 검색기 — 역색인 키워드 매칭          │
# │ semantic_query      │ Dense 검색기 — 벡터 유사도 검색           │
# │ filters.cate_depth1 │ BM25 + Dense 공통 — 대분류 사전 필터      │
# │ filters.target_reader│ BM25 + Dense 공통 — 대상 독자 필터      │
# │ constraints.*       │ BM25.py — 페이지/연도/저자 하드 필터      │
# │ score_boost.*       │ Reranker — 중분류/세부주제 가산점          │
# │ availability_required│ 도서관 API — 대출 가능 도서 필터         │
# │ anchors             │ Dense 검색기 + Reranker — 기준 책 유사도  │
# │ session_signals     │ Reranker — 높은 가중치 개인화 신호        │
# │ onboarding_signals  │ Reranker — 낮은 가중치 온보딩 보정 신호   │
# └─────────────────────┴──────────────────────────────────────────┘
