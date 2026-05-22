from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.db.database import get_db
from app.models.user import User, UserProfile
from app.core.auth import get_current_user_id

router = APIRouter(prefix="/api/profile", tags=["profile"])


class ProfileUpdateRequest(BaseModel):
    onboarding_data: dict


class FeedbackRequest(BaseModel):
    feedback: dict


@router.get("")
def get_profile(user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="사용자를 찾을 수 없습니다.")

    profile = user.profile
    return {
        "user": {"id": user.id, "name": user.name, "email": user.email},
        "onboarding_data": profile.onboarding_data if profile else {},
        "feedback_history": profile.feedback_history if profile else [],
    }


@router.put("")
def update_profile(body: ProfileUpdateRequest, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="사용자를 찾을 수 없습니다.")

    if not user.profile:
        user.profile = UserProfile(user_id=user_id, onboarding_data=body.onboarding_data, feedback_history=[])
        db.add(user.profile)
    else:
        user.profile.onboarding_data = body.onboarding_data

    db.commit()
    return {"ok": True}


@router.post("/feedback")
def add_feedback(body: FeedbackRequest, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="사용자를 찾을 수 없습니다.")

    history = list(user.profile.feedback_history or [])
    history.append(body.feedback)
    user.profile.feedback_history = history
    db.commit()
    return {"ok": True}
