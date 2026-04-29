from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import requests

AUTH_KEY = os.getenv("DATA4LIBRARY_AUTH_KEY", "")
BASE_URL = "http://data4library.kr/api/usageAnalysisList"
JSON_PATH = Path("data/books_sample_100000_page_date_updated.json")
OUTPUT_DIR = Path("data/api_results")


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, required=True, help="시작 인덱스 (포함)")
    parser.add_argument("--end", type=int, required=True, help="끝 인덱스 (미포함)")
    parser.add_argument("--delay", type=float, default=0.5, help="요청 간 대기 시간(초)")
    parser.add_argument("--auth-key", default=AUTH_KEY, help="정보나루 API 인증키")
    return parser.parse_args()


def fetch(session, isbn: str, auth_key: str):
    params = {"authKey": auth_key, "isbn13": isbn, "format": "json"}
    try:
        resp = session.get(BASE_URL, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json().get("response") or {}
        if "error" in data:
            return None, str(data["error"])
        return data, ""
    except Exception as e:
        return None, str(e)


def child(item, key):
    value = item.get(key)
    return value if isinstance(value, dict) else {}


def rows(data, key, outer, fields):
    result = []
    for item in data.get(key, []):
        if isinstance(item, dict):
            obj = child(item, outer)
            result.append({field: obj.get(field) for field in fields})
    return result


def rec_isbns(data, key):
    return [
        child(item, "book")["isbn13"]
        for item in data.get(key, [])
        if isinstance(item, dict) and child(item, "book").get("isbn13")
    ]


def extract(data: dict):
    book = data.get("book") or {}
    return {
        "isbn13": book.get("isbn13"),
        "class_no": book.get("class_no"),
        "class_nm": book.get("class_nm"),
        "description": book.get("description"),
        "loanCnt": book.get("loanCnt"),
        "keywords": rows(data, "keywords", "keyword", ["word", "weight"]),
        "loanHistory": rows(data, "loanHistory", "loan", ["month", "loanCnt", "ranking"]),
        "loanGrps": rows(data, "loanGrps", "loanGrp", ["age", "gender", "loanCnt"]),
        "coLoanBooks": rec_isbns(data, "coLoanBooks"),
        "maniaRecBooks": rec_isbns(data, "maniaRecBooks"),
        "readerRecBooks": rec_isbns(data, "readerRecBooks"),
    }


def main():
    args = parse_args()
    if not args.auth_key:
        raise SystemExit("--auth-key 또는 DATA4LIBRARY_AUTH_KEY 환경변수가 필요합니다.")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"result_{args.start}_{args.end}.jsonl"

    done = set()
    if out_path.exists():
        for line in out_path.read_text(encoding="utf-8").splitlines():
            try:
                done.add(json.loads(line)["isbn13"])
            except Exception:
                pass
        print(f"이어서 시작 - 이미 처리된 도서: {len(done)}건")

    with JSON_PATH.open(encoding="utf-8") as f:
        targets = [str(x.get("isbn", "")).strip() for x in json.load(f)][args.start:args.end]

    success, skipped = len(done), 0
    with requests.Session() as session, out_path.open("a", encoding="utf-8") as out:
        for i, isbn in enumerate(targets, 1):
            if not isbn:
                skipped += 1
                print(f"[{i}/{len(targets)}] SKIP  ISBN 없음")
                continue
            if isbn in done:
                continue

            data, reason = fetch(session, isbn, args.auth_key)
            if data is None:
                skipped += 1
                print(f"[{i}/{len(targets)}] SKIP  {isbn}  사유: {reason}")
            else:
                row = extract(data)
                out.write(json.dumps(row, ensure_ascii=False) + "\n")
                out.flush()
                success += 1
                print(f"[{i}/{len(targets)}] OK    {isbn}  누적대출={row['loanCnt']}")

            time.sleep(args.delay)

    print(f"\n완료 - 성공: {success}, 스킵: {skipped}, 저장: {out_path}")


if __name__ == "__main__":
    main()
