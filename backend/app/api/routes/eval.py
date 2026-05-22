# -*- coding: utf-8 -*-
"""
/api/eval 라우터
평가 데이터셋을 프론트엔드에 제공합니다.

엔드포인트:
    GET /api/eval/scenarios   : scenario_data.json 반환
    GET /api/eval/onboarding  : onboarding_data.json 반환
"""
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/eval", tags=["eval"])

# backend/app/api/routes/ 기준으로 4단계 위 → 프로젝트 루트
_DATASET_PATH = Path(__file__).parents[4] / "evaluation" / "dataset"


@router.get("/scenarios")
def get_scenarios():
    path = _DATASET_PATH / "scenario_data.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"파일 없음: {path}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@router.get("/onboarding")
def get_onboarding():
    path = _DATASET_PATH / "onboarding_data.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"파일 없음: {path}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)
