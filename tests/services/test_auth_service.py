import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import hash_password
from src.models import Role, User
from src.services.auth_service import AuthenticationError, authenticate


async def _make_user(session: AsyncSession, *, username: str, password: str, is_active: bool = True) -> User:
    user = User(
        username=username,
        password_hash=hash_password(password),
        role=Role.AGENT,
        is_active=is_active,
    )
    session.add(user)
    await session.flush()
    return user


async def test_authenticate_succeeds_with_correct_credentials(db_session: AsyncSession) -> None:
    await _make_user(db_session, username="agent1", password="correct-password")

    user = await authenticate(db_session, "agent1", "correct-password")

    assert user.username == "agent1"


async def test_authenticate_fails_with_wrong_password(db_session: AsyncSession) -> None:
    await _make_user(db_session, username="agent1", password="correct-password")

    with pytest.raises(AuthenticationError):
        await authenticate(db_session, "agent1", "wrong-password")


async def test_authenticate_fails_with_unknown_username(db_session: AsyncSession) -> None:
    with pytest.raises(AuthenticationError):
        await authenticate(db_session, "ghost", "anything")


async def test_authenticate_fails_for_a_deactivated_user_even_with_correct_password(
    db_session: AsyncSession,
) -> None:
    await _make_user(db_session, username="agent1", password="correct-password", is_active=False)

    with pytest.raises(AuthenticationError):
        await authenticate(db_session, "agent1", "correct-password")
