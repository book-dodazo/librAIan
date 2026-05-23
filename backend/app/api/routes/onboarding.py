import json
import logging
from pathlib import Path

import requests
from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import get_db

router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])
logger = logging.getLogger(__name__)

_CATEGORY_PATH = Path(__file__).parents[2] / "modules/llm/category_tree.json"

_EXCLUDED_CATS = {
    "어린이(초등)", "유아(0~7세)", "취업/수험서", "중/고등참고서",
    "초등참고서", "대학교재", "한국소개도서", "교보오리지널",
    "ELT/수험서", "잡지", "어린이ELT", "유아/아동/청소년",
}


@router.get("/categories")
def get_categories():
    with open(_CATEGORY_PATH, encoding="utf-8") as f:
        tree = json.load(f)
    return {k: v for k, v in tree.items() if k not in _EXCLUDED_CATS}


@router.get("/books")
def search_books(q: str = Query(..., min_length=1), db: Session = Depends(get_db)):
    try:
        rows = db.execute(
            text("SELECT DISTINCT title, author FROM books WHERE LOWER(title) LIKE LOWER(:q) ORDER BY title LIMIT 10"),
            {"q": f"%{q.strip()}%"},
        ).fetchall()
        return [{"title": r.title, "author": r.author} for r in rows]
    except Exception as e:
        logger.warning("책 검색 실패: %s", e)
        return []


@router.get("/libraries")
def search_libraries(q: str = Query(..., min_length=1)):
    """
    도서관 검색.
    Naru API는 libName 필터를 지원하지 않으므로,
    대량으로 가져온 뒤 서버에서 이름/주소로 필터링한다.
    """
    if not settings.NARU_API_KEY:
        logger.warning("NARU_API_KEY 미설정 — 도서관 검색 불가")
        return []

    keyword = q.strip().lower()

    try:
        # 전체 목록 가져와서 서버에서 키워드 필터링
        # (Naru API는 libName 필터 미지원 — 전체 ~1600개 일괄 수신)
        resp = requests.get(
            f"{settings.NARU_API_URL}/libSrch",
            params={
                "authKey": settings.NARU_API_KEY,
                "format": "json",
                "pageSize": 2000,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        libs_raw = data.get("response", {}).get("libs", [])
        if isinstance(libs_raw, dict):
            libs_raw = [libs_raw]

        libs = [item["lib"] for item in libs_raw if isinstance(item, dict) and "lib" in item]

        # 도서관 이름 또는 주소에 키워드 포함된 것만 반환
        matched = [
            {"name": lib.get("libName", ""), "address": lib.get("address", "")}
            for lib in libs
            if keyword in lib.get("libName", "").lower()
            or keyword in lib.get("address", "").lower()
        ]

        return matched[:20]  # 최대 20개

    except Exception as e:
        logger.warning("도서관 검색 실패: %s", e)
        return []
