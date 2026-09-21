from collections.abc import Awaitable, Callable

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Role, User

VALID_PAYLOAD = {"ticket_id": "123456789", "customer": "Acme", "priority": "low", "hours": 1.5}


async def test_agent_can_create_an_unassigned_ticket(
    client: AsyncClient, make_user: Callable[..., Awaitable[User]], auth_headers: Callable[[User], dict[str, str]]
) -> None:
    agent = await make_user(username="agent1", role=Role.AGENT)

    response = await client.post("/tickets", json=VALID_PAYLOAD, headers=auth_headers(agent))

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "open"
    assert body["assigned_agent_id"] is None


async def test_agent_can_create_a_ticket_assigned_to_self(
    client: AsyncClient, make_user: Callable[..., Awaitable[User]], auth_headers: Callable[[User], dict[str, str]]
) -> None:
    agent = await make_user(username="agent1", role=Role.AGENT)

    response = await client.post(
        "/tickets", json={**VALID_PAYLOAD, "assigned_agent_id": agent.id}, headers=auth_headers(agent)
    )

    assert response.status_code == 201
    assert response.json()["assigned_agent_id"] == agent.id


async def test_agent_cannot_create_a_ticket_assigned_to_another_agent(
    client: AsyncClient, make_user: Callable[..., Awaitable[User]], auth_headers: Callable[[User], dict[str, str]]
) -> None:
    agent = await make_user(username="agent1", role=Role.AGENT)
    other = await make_user(username="agent2", role=Role.AGENT)

    response = await client.post(
        "/tickets", json={**VALID_PAYLOAD, "assigned_agent_id": other.id}, headers=auth_headers(agent)
    )

    assert response.status_code == 403


async def test_admin_can_create_a_ticket_assigned_to_any_agent(
    client: AsyncClient, make_user: Callable[..., Awaitable[User]], auth_headers: Callable[[User], dict[str, str]]
) -> None:
    admin = await make_user(username="admin1", role=Role.ADMIN)
    agent = await make_user(username="agent1", role=Role.AGENT)

    response = await client.post(
        "/tickets", json={**VALID_PAYLOAD, "assigned_agent_id": agent.id}, headers=auth_headers(admin)
    )

    assert response.status_code == 201
    assert response.json()["assigned_agent_id"] == agent.id


async def test_duplicate_ticket_id_fails_409(
    client: AsyncClient, make_user: Callable[..., Awaitable[User]], auth_headers: Callable[[User], dict[str, str]]
) -> None:
    agent = await make_user(username="agent1", role=Role.AGENT)
    headers = auth_headers(agent)
    await client.post("/tickets", json=VALID_PAYLOAD, headers=headers)

    response = await client.post("/tickets", json=VALID_PAYLOAD, headers=headers)

    assert response.status_code == 409


async def test_invalid_ticket_id_format_fails_422(
    client: AsyncClient, make_user: Callable[..., Awaitable[User]], auth_headers: Callable[[User], dict[str, str]]
) -> None:
    agent = await make_user(username="agent1", role=Role.AGENT)

    response = await client.post(
        "/tickets", json={**VALID_PAYLOAD, "ticket_id": "12345"}, headers=auth_headers(agent)
    )

    assert response.status_code == 422


async def test_hours_out_of_step_fails_422(
    client: AsyncClient, make_user: Callable[..., Awaitable[User]], auth_headers: Callable[[User], dict[str, str]]
) -> None:
    agent = await make_user(username="agent1", role=Role.AGENT)

    response = await client.post("/tickets", json={**VALID_PAYLOAD, "hours": 1.3}, headers=auth_headers(agent))

    assert response.status_code == 422


async def test_get_ticket_by_id(
    client: AsyncClient, make_user: Callable[..., Awaitable[User]], auth_headers: Callable[[User], dict[str, str]]
) -> None:
    agent = await make_user(username="agent1", role=Role.AGENT)
    headers = auth_headers(agent)
    created = (await client.post("/tickets", json=VALID_PAYLOAD, headers=headers)).json()

    response = await client.get(f"/tickets/{created['id']}", headers=headers)

    assert response.status_code == 200
    assert response.json()["ticket_id"] == "123456789"


async def test_get_nonexistent_ticket_returns_404(
    client: AsyncClient, make_user: Callable[..., Awaitable[User]], auth_headers: Callable[[User], dict[str, str]]
) -> None:
    agent = await make_user(username="agent1", role=Role.AGENT)

    response = await client.get("/tickets/999999", headers=auth_headers(agent))

    assert response.status_code == 404


async def test_assigned_agent_can_update_their_own_ticket(
    client: AsyncClient, make_user: Callable[..., Awaitable[User]], auth_headers: Callable[[User], dict[str, str]]
) -> None:
    agent = await make_user(username="agent1", role=Role.AGENT)
    headers = auth_headers(agent)
    created = (
        await client.post("/tickets", json={**VALID_PAYLOAD, "assigned_agent_id": agent.id}, headers=headers)
    ).json()

    response = await client.patch(f"/tickets/{created['id']}", json={"status": "in_progress"}, headers=headers)

    assert response.status_code == 200
    assert response.json()["status"] == "in_progress"


async def test_agent_cannot_update_a_ticket_assigned_to_someone_else(
    client: AsyncClient, make_user: Callable[..., Awaitable[User]], auth_headers: Callable[[User], dict[str, str]]
) -> None:
    owner = await make_user(username="agent1", role=Role.AGENT)
    other = await make_user(username="agent2", role=Role.AGENT)
    created = (
        await client.post(
            "/tickets", json={**VALID_PAYLOAD, "assigned_agent_id": owner.id}, headers=auth_headers(owner)
        )
    ).json()

    response = await client.patch(
        f"/tickets/{created['id']}", json={"status": "in_progress"}, headers=auth_headers(other)
    )

    assert response.status_code == 403


async def test_agent_cannot_update_an_unassigned_ticket(
    client: AsyncClient, make_user: Callable[..., Awaitable[User]], auth_headers: Callable[[User], dict[str, str]]
) -> None:
    agent = await make_user(username="agent1", role=Role.AGENT)
    admin = await make_user(username="admin1", role=Role.ADMIN)
    created = (await client.post("/tickets", json=VALID_PAYLOAD, headers=auth_headers(admin))).json()

    response = await client.patch(
        f"/tickets/{created['id']}", json={"status": "in_progress"}, headers=auth_headers(agent)
    )

    assert response.status_code == 403


async def test_agent_cannot_reassign_even_their_own_ticket(
    client: AsyncClient, make_user: Callable[..., Awaitable[User]], auth_headers: Callable[[User], dict[str, str]]
) -> None:
    agent = await make_user(username="agent1", role=Role.AGENT)
    other = await make_user(username="agent2", role=Role.AGENT)
    headers = auth_headers(agent)
    created = (
        await client.post("/tickets", json={**VALID_PAYLOAD, "assigned_agent_id": agent.id}, headers=headers)
    ).json()

    response = await client.patch(
        f"/tickets/{created['id']}", json={"assigned_agent_id": other.id}, headers=headers
    )

    assert response.status_code == 403


async def test_admin_can_reassign_a_ticket(
    client: AsyncClient, make_user: Callable[..., Awaitable[User]], auth_headers: Callable[[User], dict[str, str]]
) -> None:
    admin = await make_user(username="admin1", role=Role.ADMIN)
    agent1 = await make_user(username="agent1", role=Role.AGENT)
    agent2 = await make_user(username="agent2", role=Role.AGENT)
    created = (
        await client.post(
            "/tickets", json={**VALID_PAYLOAD, "assigned_agent_id": agent1.id}, headers=auth_headers(admin)
        )
    ).json()

    response = await client.patch(
        f"/tickets/{created['id']}", json={"assigned_agent_id": agent2.id}, headers=auth_headers(admin)
    )

    assert response.status_code == 200
    assert response.json()["assigned_agent_id"] == agent2.id


async def test_closed_ticket_cannot_be_patched_even_by_an_admin(
    client: AsyncClient, make_user: Callable[..., Awaitable[User]], auth_headers: Callable[[User], dict[str, str]]
) -> None:
    admin = await make_user(username="admin1", role=Role.ADMIN)
    created = (
        await client.post("/tickets", json={**VALID_PAYLOAD, "status": "closed"}, headers=auth_headers(admin))
    ).json()

    response = await client.patch(
        f"/tickets/{created['id']}", json={"customer": "New Name"}, headers=auth_headers(admin)
    )

    assert response.status_code == 409


async def test_update_nonexistent_ticket_returns_404(
    client: AsyncClient, make_user: Callable[..., Awaitable[User]], auth_headers: Callable[[User], dict[str, str]]
) -> None:
    admin = await make_user(username="admin1", role=Role.ADMIN)

    response = await client.patch("/tickets/999999", json={"customer": "New Name"}, headers=auth_headers(admin))

    assert response.status_code == 404
