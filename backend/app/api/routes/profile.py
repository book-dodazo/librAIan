"""
프로필 라우트 모듈.

사용자 프로필 관리를 제공합니다.
나중에 사용자 맞춤화에 사용됩니다.
"""

from fastapi import APIRouter
from ..schemas import UserProfile


router = APIRouter()


@router.get("/profile/{user_id}", response_model=UserProfile)
async def get_user_profile(user_id: str):
    """사용자 프로필 조회.

    Args:
        user_id: 사용자 ID

    Returns:
        사용자 프로필
    """
    # TODO: 프로필 조회 구현
    return UserProfile(
        user_id=user_id,
        preferences={},
        reading_history=[]
    )


@router.put("/profile/{user_id}")
async def update_user_profile(user_id: str, profile: UserProfile):
    """사용자 프로필 업데이트.

    Args:
        user_id: 사용자 ID
        profile: 업데이트할 프로필

    Returns:
        업데이트 결과
    """
    # TODO: 프로필 업데이트 구현
    return {"message": "프로필이 업데이트되었습니다."}