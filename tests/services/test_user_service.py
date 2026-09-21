from collections.abc import Awaitable, Callable

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import verify_password
from src.models import Role, User
from src.schemas.user import UserCreate, UserUpdate
from src.services.user_service import DuplicateUsernameError, create_user, update_user


async def test_create_user_hashes_the_password_and_returns_the_user(db_session: AsyncSession) -> None:
    user = await create_user(db_session, UserCreate(username="agent1", password="a-real-password", role=Role.AGENT))

    assert user.id is not None
    assert user.password_hash != "a-real-password"
    assert verify_password("a-real-password", user.password_hash)


async def test_create_user_rejects_a_duplicate_username(
    db_session: AsyncSession, make_user: Callable[..., Awaitable[User]]
) -> None:
    await make_user(username="agent1")

    with pytest.raises(DuplicateUsernameError):
        await create_user(db_session, UserCreate(username="agent1", password="a-real-password", role=Role.AGENT))


async def test_update_user_can_change_role_and_deactivate(
    db_session: AsyncSession, make_user: Callable[..., Awaitable[User]]
) -> None:
    user = await make_user(role=Role.AGENT, is_active=True)

    updated = await update_user(db_session, user, UserUpdate(role=Role.ADMIN, is_active=False))

    assert updated.role is Role.ADMIN
    assert updated.is_active is False


async def test_update_user_can_reset_the_password(
    db_session: AsyncSession, make_user: Callable[..., Awaitable[User]]
) -> None:
    user = await make_user(password="old-password")

    updated = await update_user(db_session, user, UserUpdate(password="new-password"))

    assert verify_password("new-password", updated.password_hash)
    assert not verify_password("old-password", updated.password_hash)


async def test_update_user_leaves_fields_untouched_when_not_given(
    db_session: AsyncSession, make_user: Callable[..., Awaitable[User]]
) -> None:
    user = await make_user(role=Role.AGENT, is_active=True)

    updated = await update_user(db_session, user, UserUpdate())

    assert updated.role is Role.AGENT
    assert updated.is_active is True
