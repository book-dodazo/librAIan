"""
- ISBN 범위 분할 수집 (--start, --end, --delay 인자)
- 중단 시 이어서 실행 가능한 resume 기능
- 결과를 jsonl로 저장, data/ 폴더 gitignore 처리
"""
import json
import time
import argparse
import requests
from pathlib import Path

AUTH_KEY = "" # 본인 API 인증키 
BASE_URL = "http://data4library.kr/api/usageAnalysisList"
JSON_PATH = "data/books_sample_100000_page_date_updated.json"
OUTPUT_DIR = Path("data/api_results")

def parse_args():  
    # CLI 인자(start, end, delay) 파싱
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, required=True, help="시작 인덱스 (포함)")
    parser.add_argument("--end",   type=int, required=True, help="끝 인덱스 (미포함)")
    parser.add_argument("--delay", type=float, default=0.5, help="요청 간 대기 시간(초)")
    return parser.parse_args()

def fetch(isbn: str) -> dict | None:  
    # ISBN으로 정보나루 API 호출 후 response 반환, 오류·없음은 None
    params = {"authKey": AUTH_KEY, "isbn13": isbn, "format": "json"}
    try:
        resp = requests.get(BASE_URL, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json().get("response", {})
        if "error" in data:
            return None
        return data
    except Exception as e:
        print(f"  [오류] {isbn}: {e}")
        return None

def extract(data: dict) -> dict:  
    # API 응답에서 필요한 필드만 추출해 딕셔너리로 반환
    book = data.get("book", {})
    return {
        "isbn13":       book.get("isbn13"),
        "class_no":     book.get("class_no"),
        "class_nm":     book.get("class_nm"),
        "description":  book.get("description"),
        "loanCnt":      book.get("loanCnt"),
        "keywords":     [
            {"word": k["keyword"]["word"], "weight": k["keyword"]["weight"]}
            for k in data.get("keywords", [])
        ],
        "loanHistory":  [
            {"month": h["loan"]["month"], "loanCnt": h["loan"]["loanCnt"], "ranking": h["loan"]["ranking"]}
            for h in data.get("loanHistory", [])
        ],
        "loanGrps":     [
            {"age": g["loanGrp"]["age"], "gender": g["loanGrp"]["gender"], "loanCnt": g["loanGrp"]["loanCnt"]}
            for g in data.get("loanGrps", [])
        ],
        "coLoanBooks":      [b["book"]["isbn13"] for b in data.get("coLoanBooks", [])],
        "maniaRecBooks":    [b["book"]["isbn13"] for b in data.get("maniaRecBooks", [])],
        "readerRecBooks":   [b["book"]["isbn13"] for b in data.get("readerRecBooks", [])],
    }

def main():  
    # 범위 내 ISBN을 순회하며 API 호출, 결과를 jsonl로 저장 (재시작 지원)
    args = parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"result_{args.start}_{args.end}.jsonl"

    # 이미 처리된 ISBN 로드 (재시작 대비)
    done_isbns: set[str] = set()
    if out_path.exists():
        with open(out_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    done_isbns.add(json.loads(line)["isbn13"])
                except Exception:
                    pass
        print(f"이어서 시작 — 이미 처리된 도서: {len(done_isbns)}건")

    with open(JSON_PATH, "r", encoding="utf-8") as f:
        isbns = [str(b.get("isbn", "")).strip() for b in json.load(f)]

    targets = isbns[args.start:args.end]
    total = len(targets)

    success = len(done_isbns)
    skipped = 0

    with open(out_path, "a", encoding="utf-8") as out_f:
        for i, isbn in enumerate(targets, 1):
            if not isbn:
                skipped += 1
                continue
            if isbn in done_isbns:
                continue

            data = fetch(isbn)
            if data is None:
                skipped += 1
                print(f"[{i}/{total}] SKIP {isbn}")
            else:
                result = extract(data)
                out_f.write(json.dumps(result, ensure_ascii=False) + "\n")
                out_f.flush()
                success += 1
                print(f"[{i}/{total}] OK   {isbn}  누적대출={result['loanCnt']}")

            time.sleep(args.delay)

    print(f"\n완료 — 성공: {success}, 스킵: {skipped}, 저장: {out_path}")

if __name__ == "__main__":
    main()
