from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import hash_password
from src.models import Role, User


async def _make_user(session: AsyncSession, *, username: str, password: str, is_active: bool = True) -> User:
    user = User(username=username, password_hash=hash_password(password), role=Role.AGENT, is_active=is_active)
    session.add(user)
    await session.flush()
    return user


async def test_login_succeeds_and_returns_a_bearer_token(client: AsyncClient, db_session: AsyncSession) -> None:
    await _make_user(db_session, username="agent1", password="correct-password")

    response = await client.post("/auth/login", json={"username": "agent1", "password": "correct-password"})

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert len(body["access_token"]) > 0


async def test_login_fails_the_same_way_for_unknown_user_and_wrong_password(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _make_user(db_session, username="agent1", password="correct-password")

    wrong_password = await client.post("/auth/login", json={"username": "agent1", "password": "nope"})
    unknown_user = await client.post("/auth/login", json={"username": "ghost", "password": "nope"})

    assert wrong_password.status_code == 401
    assert unknown_user.status_code == 401
    assert wrong_password.json() == unknown_user.json()


async def test_login_fails_for_a_deactivated_user(client: AsyncClient, db_session: AsyncSession) -> None:
    await _make_user(db_session, username="agent1", password="correct-password", is_active=False)

    response = await client.post("/auth/login", json={"username": "agent1", "password": "correct-password"})

    assert response.status_code == 401
