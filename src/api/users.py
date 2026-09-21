from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import Role, User
from ..repositories import user_repository
from ..schemas.user import UserCreate, UserResponse, UserUpdate
from ..services.user_service import DuplicateUsernameError, create_user, update_user
from .deps import require_role

router = APIRouter(prefix="/users", tags=["users"], dependencies=[Depends(require_role(Role.ADMIN))])


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create(body: UserCreate, session: AsyncSession = Depends(get_session)) -> User:
    try:
        return await create_user(session, body)
    except DuplicateUsernameError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists")


@router.patch("/{user_id}", response_model=UserResponse)
async def update(user_id: int, body: UserUpdate, session: AsyncSession = Depends(get_session)) -> User:
    user = await user_repository.get_by_id(session, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    return await update_user(session, user, body)
