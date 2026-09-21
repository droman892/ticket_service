import jwt
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_user, require_role
from src.config import get_settings
from src.core.security import create_access_token, hash_password
from src.models import Role, User


async def _make_user(session: AsyncSession, *, role: Role = Role.AGENT, is_active: bool = True) -> User:
    user = User(username="u", password_hash=hash_password("pw"), role=role, is_active=is_active)
    session.add(user)
    await session.flush()
    return user


def _bearer(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


async def test_get_current_user_returns_the_user_for_a_valid_token(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    settings = get_settings()
    token = create_access_token(user_id=user.id, role=user.role.value, settings=settings)

    result = await get_current_user(credentials=_bearer(token), session=db_session, settings=settings)

    assert result.id == user.id


async def test_get_current_user_rejects_missing_credentials(db_session: AsyncSession) -> None:
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(credentials=None, session=db_session, settings=get_settings())

    assert exc_info.value.status_code == 401


async def test_get_current_user_rejects_a_token_with_a_bad_signature(db_session: AsyncSession) -> None:
    forged = jwt.encode({"sub": "1", "role": "agent"}, "a-completely-different-32-byte-secret", algorithm="HS256")

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(credentials=_bearer(forged), session=db_session, settings=get_settings())

    assert exc_info.value.status_code == 401


async def test_get_current_user_rejects_a_deactivated_user_even_with_a_valid_token(
    db_session: AsyncSession,
) -> None:
    user = await _make_user(db_session, is_active=False)
    settings = get_settings()
    token = create_access_token(user_id=user.id, role=user.role.value, settings=settings)

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(credentials=_bearer(token), session=db_session, settings=settings)

    assert exc_info.value.status_code == 401


async def test_require_role_allows_a_matching_role(db_session: AsyncSession) -> None:
    user = await _make_user(db_session, role=Role.ADMIN)
    check = require_role(Role.ADMIN)

    assert await check(user=user) is user


async def test_require_role_rejects_a_non_matching_role(db_session: AsyncSession) -> None:
    user = await _make_user(db_session, role=Role.AGENT)
    check = require_role(Role.ADMIN)

    with pytest.raises(HTTPException) as exc_info:
        await check(user=user)

    assert exc_info.value.status_code == 403
