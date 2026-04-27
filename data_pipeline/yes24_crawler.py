"""
YES24 구매 리뷰 크롤러

사용법:
  python yes24_crawler.py --test       # ISBN 5개로 셀렉터/엔드포인트 확인
  python yes24_crawler.py              # 전체 실행 (progress.json으로 재시작 가능)
  python yes24_crawler.py --limit 100  # 최대 100개만 실행
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
import re
import time
from datetime import datetime
from functools import wraps

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# 엔드포인트나 셀렉터가 바뀌면 여기만 수정
BASE_URL         = "https://www.yes24.com"
SEARCH_URL       = "https://www.yes24.com/Product/Search"
REVIEW_LIST_URL  = "https://www.yes24.com/Product/communityModules/GoodsReviewList/{goods_id}"
REVIEW_PAGE_SIZE = 5
MAX_REVIEWS      = 50

# 인메모리 캐시로 동일 상품에 대한 반복 요청을 줄임
GOODS_ID_CACHE = {}
PRODUCT_META_CACHE = {}

ISBN_FILE     = "books_sample_100000.json"
OUTPUT_JSON   = "yes24_reviews.jsonl"
PROGRESS_FILE = "progress.json"
LOG_FILE      = "crawler.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


def with_retry(max_attempts=3, backoff=2.0):
    """네트워크 오류 시 최대 max_attempts번 재시도하는 데코레이터."""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            for attempt in range(max_attempts):
                try:
                    return fn(*args, **kwargs)
                except (requests.exceptions.ConnectionError,
                        requests.exceptions.Timeout) as e:
                    if attempt == max_attempts - 1:
                        raise
                    wait = backoff * (attempt + 1)
                    logger.warning(f"재시도 {attempt + 1}/{max_attempts} ({wait:.0f}s): {e}")
                    time.sleep(wait)
        return wrapper
    return decorator


def load_isbn_list(filepath: str) -> list:
    """JSON 배열에서 isbn 필드를 추출해 리스트로 반환."""
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [str(item["isbn"]) for item in data if item.get("isbn")]


def build_session() -> requests.Session:
    """봇 차단 방지를 위해 브라우저 헤더가 설정된 세션을 반환."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Referer": "https://www.yes24.com",
    })
    retry = Retry(
        total=1,
        backoff_factor=0.5,
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=frozenset(["GET"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(pool_connections=20, pool_maxsize=20, max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session

def polite_sleep(success: bool, index: int):
    """
    성공/실패 상황에 따라 대기 시간을 다르게 적용.
    - 정상 처리: 최소 대기
    - 실패 발생: 조금 길게 대기
    - 일정 주기마다 긴 휴식
    """
    if not success:
        time.sleep(random.uniform(1.0, 2.5))
    elif index % 500 == 0:
        time.sleep(random.uniform(2.0, 4.0))
    else:
        time.sleep(random.uniform(0.1, 0.25))

@with_retry()
def get_goods_id(session: requests.Session, isbn: str, debug: bool = False) -> str | None:
    """ISBN으로 YES24를 검색해 내부 상품 ID(goods_id)를 반환. 없으면 None."""
    if isbn in GOODS_ID_CACHE:
        return GOODS_ID_CACHE[isbn]

    resp = session.get(SEARCH_URL, params={"domain": "BOOK", "query": isbn}, timeout=15)
    resp.raise_for_status()

    if debug:
        logger.info(f"[DEBUG] 최종 URL: {resp.url}")

    # 케이스 1: ISBN 검색 시 상품 페이지로 바로 리다이렉트
    m = re.search(r"/Product/Goods/(\d+)", resp.url)
    if m:
        goods_id = m.group(1)
        logger.info(f"ISBN {isbn} → goods_id {goods_id} (리다이렉트)")
        GOODS_ID_CACHE[isbn] = goods_id
        return goods_id

    html = resp.text
    m = re.search(
        r'<a[^>]+class=["\"][^"\"]*\bgd_name\b[^"\"]*["\"][^>]*href=["\"]/Product/Goods/(\d+)["\"]',
        html,
        re.IGNORECASE,
    )
    if m:
        goods_id = m.group(1)
        GOODS_ID_CACHE[isbn] = goods_id
        return goods_id

    soup = BeautifulSoup(html, "lxml")
    link = soup.select_one("a.gd_name[href]")
    if not link:
        return None

    goods_id = link["href"].strip("/").split("/")[-1]
    GOODS_ID_CACHE[isbn] = goods_id
    return goods_id


@with_retry()
def get_product_meta(session: requests.Session, goods_id: str, debug: bool = False) -> dict:
    """상품 페이지에서 ISBN13, 전체 평점, 리뷰 수를 파싱해 반환."""
    if goods_id in PRODUCT_META_CACHE:
        return PRODUCT_META_CACHE[goods_id]

    resp = session.get(f"{BASE_URL}/Product/Goods/{goods_id}", timeout=15)
    resp.raise_for_status()

    html = resp.text
    page_isbn = _parse_isbn13_from_text(html)
    total_score = _parse_total_score_from_text(html)
    review_count = _parse_review_count_from_text(html)

    if page_isbn is None or total_score is None or review_count is None:
        soup = BeautifulSoup(html, "lxml")
        page_isbn = page_isbn or _parse_isbn13(soup)
        total_score = total_score or _parse_total_score(soup)
        review_count = review_count or _parse_review_count(soup)

    result = {
        "page_isbn": page_isbn,
        "total_score": total_score,
        "review_count": review_count,
    }
    PRODUCT_META_CACHE[goods_id] = result
    return result


def _parse_isbn13_from_text(text: str) -> str | None:
    m = re.search(r"ISBN13[^\d]*(\d[\d\-]{11,17}\d)", text, re.IGNORECASE)
    if m:
        return re.sub(r"[^\d]", "", m.group(1))
    return None


def _parse_total_score_from_text(text: str) -> float | None:
    patterns = [
        r'class=["\"][^"\"]*\byes_b\b[^"\"]*["\"][^>]*>(\d+(?:\.\d+)?)<',
        r'class=["\"][^"\"]*\brating_score\b[^"\"]*["\"][^>]*>(\d+(?:\.\d+)?)<',
        r'id=["\"]spanBuyReviewScore["\"][^>]*>(\d+(?:\.\d+)?)<',
    ]
    for pattern in patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                pass

    m = re.search(r"width:\s*(\d+(?:\.\d+)?)\s*%", text)
    if m:
        return round(float(m.group(1)) / 20, 1)
    return None


def _parse_review_count_from_text(text: str) -> int | None:
    m = re.search(r'data-review-count=["\'](\d+)["\']', text, re.IGNORECASE)
    if m:
        return int(m.group(1))

    patterns = [
        r'id=["\'][^"\']*(?:emPurchaseReviewCountText|buyReviewCount|spanReviewCount)[^"\']*["\'][^>]*>([\d,]+)<',
        r'class=["\'][^"\']*(?:buyReviewCount|cnt_item)[^"\']*["\'][^>]*>([\d,]+)<',
    ]
    for pattern in patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            digits = re.sub(r"[^\d]", "", m.group(1))
            if digits:
                return int(digits)
    return None


def _parse_isbn13(soup: BeautifulSoup) -> str | None:
    """품목정보 테이블의 ISBN13 값을 추출."""
    for label in soup.find_all(["th", "dt"]):
        if "ISBN13" in label.get_text():
            sibling = label.find_next_sibling(["td", "dd"])
            if sibling:
                return re.sub(r"[^\d]", "", sibling.get_text())
    return None


def _parse_total_score(soup: BeautifulSoup) -> float | None:
    """구매자 리뷰 전체 평점을 추출. div.gd_rating > em.yes_b 우선 시도."""
    for sel in ["#infoset_reviewTop > div.review_starWrap > div.gd_rating > em.yes_b",
                "div.gd_rating > em.yes_b", "em.yes_b", "span.rating_score",
                "em.rating_num", ".ratingBuyer .rating_score", "#spanBuyReviewScore"]:
        el = soup.select_one(sel)
        if el:
            try:
                return float(el.get_text(strip=True))
            except ValueError:
                pass

    fill = soup.select_one(".ratingStarBuyer .ratingStarFill, .star_rating .fill")
    if fill:
        m = re.search(r"width:\s*(\d+(?:\.\d+)?)\s*%", fill.get("style", ""))
        if m:
            return round(float(m.group(1)) / 20, 1)
    return None


def _parse_review_count(soup: BeautifulSoup) -> int | None:
    """구매자 리뷰 총 개수를 추출."""
    el = soup.select_one("#purchase")
    if el:
        val = el.get("data-review-count", "")
        if val.strip().lstrip("-").isdigit():
            return int(val.strip())

    for sel in ["#emPurchaseReviewCountText", "#buyReviewCount", "span.buyReviewCount",
                ".ratingBuyer .cnt_item", "#spanReviewCount"]:
        el = soup.select_one(sel)
        if el:
            digits = re.sub(r"[^\d]", "", el.get_text())
            if digits:
                return int(digits)
    return None


@with_retry()
def get_reviews_page(
    session: requests.Session, goods_id: str, page: int, debug: bool = False
) -> list:
    """리뷰 목록 GET → 평점/텍스트 직접 파싱."""
    url = REVIEW_LIST_URL.format(goods_id=goods_id)
    resp = session.get(
        url,
        params={"Type": "Purchase", "Sort": 2, "PageNumber": page, "DojungAfterBuy": 1},
        headers={"Referer": f"{BASE_URL}/Product/Goods/{goods_id}"},
        timeout=15,
    )
    resp.raise_for_status()

    if debug:
        logger.info(f"[DEBUG] 리뷰 목록 URL: {resp.url}")
        # logger.info(f"[DEBUG] 리뷰 목록 HTML (page={page}):\n{resp.text[:3000]}")

    # soup = BeautifulSoup(resp.text, "html.parser")
    soup = BeautifulSoup(resp.text, "lxml")
    items = soup.select("#infoset_reviewContentList div.reviewInfoGrp.lnkExtend")

    if not items:
        return []

    reviews = []
    for item in items:
        score_el = item.select_one("div.reviewInfoTop > div > span > span")
        score = None
        if score_el:
            m = re.search(r"(\d+(?:\.\d+)?)", score_el.get_text())
            if m:
                score = float(m.group(1))

        text_el = item.select_one("div.reviewInfoBot.origin > div.review_cont")
        text = text_el.get_text(strip=True) if text_el else ""

        if text:
            reviews.append({"review_text": text, "review_score": score})

    return reviews


def get_all_reviews(
    session: requests.Session, goods_id: str, review_count: int | None = None,
    max_reviews: int = MAX_REVIEWS, debug: bool = False,
) -> list:
    """
    페이지 단위로 리뷰를 수집하되,
    실제 review_count를 활용해 불필요한 페이지 요청을 줄인다.
    """
    if review_count is not None:
        target_reviews = min(review_count, max_reviews)
    else:
        target_reviews = max_reviews

    if target_reviews <= 0:
        return []

    max_pages = -(-target_reviews // REVIEW_PAGE_SIZE)

    all_reviews = []
    for page in range(1,max_pages + 1):
        page_reviews = get_reviews_page(session, goods_id, page, debug=debug)

        if not page_reviews:
            break

        all_reviews.extend(page_reviews)
        if len(all_reviews) >= target_reviews:
            break

        time.sleep(random.uniform(0.2, 0.5))

    return all_reviews[:target_reviews]


def process_isbn(
    session: requests.Session, isbn: str, state: CrawlerState, debug: bool = False
) -> list | None:
    """ISBN 한 건을 처리해 리뷰 행 리스트를 반환. 실패 시 state에 기록 후 None 반환."""
    try:
        goods_id = get_goods_id(session, isbn, debug=debug)
        if not goods_id:
            state.mark_failed(isbn, "not_found")
            return None

        meta = get_product_meta(session, goods_id, debug=debug)

        page_isbn = meta.get("page_isbn")
        if page_isbn and page_isbn != str(isbn):
            logger.warning(f"ISBN 불일치: 요청={isbn}, 페이지={page_isbn} → 건너뜀")
            state.mark_failed(isbn, f"isbn_mismatch:{page_isbn}")
            return None
        
        review_count = meta.get("review_count")
        if review_count == 0:
            # logger.info(f"ISBN {isbn}: 구매 리뷰 0개 → 건너뜀")
            state.mark_failed(isbn, "no_reviews")
            return None

        reviews = get_all_reviews(session, goods_id, review_count, debug=debug)
        if not reviews:
            # logger.warning(f"ISBN {isbn}: 리뷰 없음")
            state.mark_failed(isbn, "no_reviews")
            return None

        texts = [r["review_text"] for r in reviews if r.get("review_text")]
        scores = [r["review_score"] for r in reviews if r.get("review_score") is not None]
        record = {
            "isbn": isbn,
            "reviews": texts,
            "review_score": round(sum(scores) / len(scores), 2) if scores else None,
            "total_score":  meta["total_score"],
            "review_count": meta["review_count"],
        }
        state.mark_done(isbn)
        logger.info(f"ISBN {isbn}: {len(texts)}개 리뷰 완료")
        return record

    except requests.exceptions.HTTPError as e:
        code = e.response.status_code if e.response else "?"
        if code == 429:
            logger.error("Rate limit(429). 60초 대기.")
            time.sleep(60)
        state.mark_failed(isbn, f"http_{code}")
        return None
    except Exception as e:
        logger.error(f"ISBN {isbn} 오류: {e}")
        state.mark_failed(isbn, str(e)[:200])
        return None


def save_batch(records: list, json_path: str):
    """records를 JSONL에 추가 저장(append). 한 줄 = JSON 1개."""
    if not records:
        return
    with open(json_path, "a", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    logger.info(f"{len(records)}개 레코드 저장 → {json_path}")


class CrawlerState:
    """완료/실패 ISBN을 추적하고 progress.json에 저장해 재시작을 지원."""

    def __init__(self, path: str = PROGRESS_FILE):
        self.path = path
        self.completed: set = set()
        self.failed: dict = {}
        if os.path.exists(path):
            try:
                data = json.load(open(path, encoding="utf-8"))
                self.completed = set(data.get("completed", []))
                self.failed = data.get("failed", {})
                logger.info(f"진행 상태 로드: 완료 {len(self.completed)}, 실패 {len(self.failed)}")
            except (json.JSONDecodeError, ValueError):
                logger.warning(f"{path} 파싱 실패 — 처음부터 시작합니다.")

    def mark_done(self, isbn: str):
        self.completed.add(isbn)

    def mark_failed(self, isbn: str, reason: str):
        self.failed[isbn] = reason

    def save(self):
        """현재 상태를 progress.json에 저장."""
        json.dump(
            {"completed": list(self.completed), "failed": self.failed,
             "last_saved": datetime.now().isoformat()},
            open(self.path, "w", encoding="utf-8"),
            ensure_ascii=False, indent=2,
        )


def main():
    """ISBN 목록을 순회하며 YES24 구매 리뷰를 수집해 CSV로 저장."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true", help="ISBN 5개만 테스트")
    parser.add_argument("--limit", type=int, default=None, help="처리할 ISBN 최대 개수")
    args = parser.parse_args()

    isbn_list = load_isbn_list(ISBN_FILE)
    logger.info(f"ISBN 목록 로드: {len(isbn_list)}개")

    state   = CrawlerState()
    session = build_session()

    pending = [isbn for isbn in isbn_list
               if isbn not in state.completed and isbn not in state.failed]

    if args.test:
        pending = pending[:5]
        logger.info(f"[TEST] {len(pending)}개 ISBN 테스트 시작")
    elif args.limit:
        pending = pending[:args.limit]

    logger.info(f"처리 대상: {len(pending)}개 (완료 {len(state.completed)}, 실패 {len(state.failed)})")

    batch = []
    elapsed_times = []
    for i, isbn in enumerate(pending, 1):
        start_time = time.perf_counter()
        record = process_isbn(session, isbn, state, debug=args.test)
        elapsed = time.perf_counter() - start_time
        elapsed_times.append(elapsed)

        success = record is not None

        if record:
            batch.append(record)

        if len(batch) >= 500:
            save_batch(batch, OUTPUT_JSON)
            batch = []

        if i % 500 == 0:
            state.save()
            logger.info("진행: %d/%d", i, len(pending))

        if i % 500 == 0:
            avg_time = sum(elapsed_times[-500:]) / len(elapsed_times[-500:])
            logger.info(f"평균 처리 속도 (최근 500개): {avg_time:.2f}s / ISBN")

        polite_sleep(success=success, index=i)

    if batch:
        save_batch(batch, OUTPUT_JSON)
    state.save()
    logger.info(f"완료. 처리: {len(state.completed)}, 실패: {len(state.failed)}")


if __name__ == "__main__":
    main()
