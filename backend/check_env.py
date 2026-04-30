"""
환경변수 설정 확인 스크립트

실행:
    python backend/check_env.py
"""

import os
import sys

REQUIRED = [
    ("NARU_API_KEY",  "정보나루 Open API 인증키"),
    ("NARU_LIB_CODE", "조회할 도서관 코드 (예: 111003 = 국립중앙도서관)"),
]

OPTIONAL = [
    ("CLOVA_STUDIO_API_KEY",  "CLOVA Studio Reranker API 키 (없으면 재정렬 건너뜀)"),
    ("HCX_API_KEY",           "HyperCLOVA X API 키"),
    ("POSTGRES_DB",           "PostgreSQL DB 이름",     "libraian"),
    ("POSTGRES_HOST",         "PostgreSQL 호스트",       "localhost"),
    ("POSTGRES_PORT",         "PostgreSQL 포트",         "5432"),
    ("POSTGRES_USER",         "PostgreSQL 사용자",       os.getenv("USER", "")),
    ("POSTGRES_PASSWORD",     "PostgreSQL 비밀번호",     "(없음)"),
]

OK   = "\033[32m✔\033[0m"
MISS = "\033[31m✘\033[0m"
SKIP = "\033[33m-\033[0m"


def check() -> bool:
    all_ok = True

    print("\n[필수 환경변수]")
    for key, desc in REQUIRED:
        val = os.getenv(key)
        if val:
            masked = val[:4] + "****" if len(val) > 4 else "****"
            print(f"  {OK}  {key:<30} {masked}  ({desc})")
        else:
            print(f"  {MISS}  {key:<30} 미설정  ({desc})")
            all_ok = False

    print("\n[선택 환경변수]")
    for item in OPTIONAL:
        key, desc, *default = item
        default_val = default[0] if default else None
        val = os.getenv(key)
        if val:
            masked = val[:4] + "****" if len(val) > 4 else "****"
            print(f"  {OK}  {key:<30} {masked}  ({desc})")
        else:
            fallback = f"기본값: {default_val}" if default_val else "미설정"
            print(f"  {SKIP}  {key:<30} {fallback}  ({desc})")

    print()
    return all_ok


if __name__ == "__main__":
    ok = check()
    if not ok:
        print("✘ 필수 환경변수가 누락되었습니다. 설정 후 다시 실행하세요.\n")
        sys.exit(1)
    print("✔ 모든 필수 환경변수가 설정되었습니다.\n")
