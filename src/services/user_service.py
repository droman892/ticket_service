from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.security import hash_password
from ..models import User
from ..schemas.user import UserCreate, UserUpdate


class DuplicateUsernameError(Exception):
    pass


async def create_user(session: AsyncSession, data: UserCreate) -> User:
    user = User(
        username=data.username,
        password_hash=hash_password(data.password),
        role=data.role,
    )
    session.add(user)
    try:
        # Flushing (not just adding) is what actually sends the INSERT and
        # lets the DB's unique constraint on username reject a duplicate —
        # the constraint, not a pre-check, is the real safeguard (a
        # pre-check has a race between two concurrent requests).
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise DuplicateUsernameError()

    await session.commit()
    await session.refresh(user)
    return user


async def update_user(session: AsyncSession, user: User, data: UserUpdate) -> User:
    if data.role is not None:
        user.role = data.role
    if data.is_active is not None:
        user.is_active = data.is_active
    if data.password is not None:
        user.password_hash = hash_password(data.password)

    await session.commit()
    await session.refresh(user)
    return user
