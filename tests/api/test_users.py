from collections.abc import Awaitable, Callable

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Role, User


async def test_admin_can_create_a_user(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    admin = await make_user(username="admin1", role=Role.ADMIN)

    response = await client.post(
        "/users",
        json={"username": "new_agent", "password": "a-real-password", "role": "agent"},
        headers=auth_headers(admin),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["username"] == "new_agent"
    assert body["role"] == "agent"
    assert body["is_active"] is True
    assert "password" not in body
    assert "password_hash" not in body


async def test_create_user_fails_on_duplicate_username(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    admin = await make_user(username="admin1", role=Role.ADMIN)
    await make_user(username="taken")

    response = await client.post(
        "/users",
        json={"username": "taken", "password": "a-real-password", "role": "agent"},
        headers=auth_headers(admin),
    )

    assert response.status_code == 409


async def test_agent_cannot_create_a_user(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    agent = await make_user(username="agent1", role=Role.AGENT)

    response = await client.post(
        "/users",
        json={"username": "new_agent", "password": "a-real-password", "role": "agent"},
        headers=auth_headers(agent),
    )

    assert response.status_code == 403


async def test_unauthenticated_request_cannot_create_a_user(client: AsyncClient) -> None:
    response = await client.post(
        "/users", json={"username": "new_agent", "password": "a-real-password", "role": "agent"}
    )

    assert response.status_code == 401


async def test_admin_can_deactivate_a_user(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    admin = await make_user(username="admin1", role=Role.ADMIN)
    agent = await make_user(username="agent1", role=Role.AGENT, is_active=True)

    response = await client.patch(f"/users/{agent.id}", json={"is_active": False}, headers=auth_headers(admin))

    assert response.status_code == 200
    assert response.json()["is_active"] is False


async def test_update_a_nonexistent_user_returns_404(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    admin = await make_user(username="admin1", role=Role.ADMIN)

    response = await client.patch("/users/999999", json={"is_active": False}, headers=auth_headers(admin))

    assert response.status_code == 404


async def test_agent_cannot_update_a_user(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    agent = await make_user(username="agent1", role=Role.AGENT)
    other = await make_user(username="agent2", role=Role.AGENT)

    response = await client.patch(f"/users/{other.id}", json={"is_active": False}, headers=auth_headers(agent))

    assert response.status_code == 403


async def test_there_is_no_delete_users_endpoint(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    admin = await make_user(username="admin1", role=Role.ADMIN)
    agent = await make_user(username="agent1", role=Role.AGENT)

    response = await client.delete(f"/users/{agent.id}", headers=auth_headers(admin))

    assert response.status_code == 405
