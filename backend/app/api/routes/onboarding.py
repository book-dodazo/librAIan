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

_CATEGORY_PATH = Path(__file__).parents[3] / "modules/llm/category_tree.json"

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
            text("SELECT DISTINCT title, author FROM books WHERE title ILIKE :q ORDER BY title LIMIT 10"),
            {"q": f"%{q.strip()}%"},
        ).fetchall()
        return [{"title": r.title, "author": r.author} for r in rows]
    except Exception as e:
        logger.warning("책 검색 실패: %s", e)
        return []


@router.get("/libraries")
def search_libraries(q: str = Query(..., min_length=1)):
    if not settings.NARU_API_KEY:
        logger.warning("NARU_API_KEY 미설정 — 도서관 검색 불가")
        return []
    try:
        resp = requests.get(
            f"{settings.NARU_API_URL}/libSrch",
            params={
                "authKey": settings.NARU_API_KEY,
                "libName": q.strip(),
                "format": "json",
                "pageSize": 20,
            },
            timeout=5,
        )
        resp.raise_for_status()
        data = resp.json()
        libs = data.get("response", {}).get("libs", {}).get("lib", [])
        if isinstance(libs, dict):
            libs = [libs]
        return [
            {"name": lib.get("libName", ""), "address": lib.get("address", "")}
            for lib in libs
            if lib.get("libName")
        ]
    except Exception as e:
        logger.warning("도서관 검색 실패: %s", e)
        return []
