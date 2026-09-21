import itertools
from collections.abc import Awaitable, Callable
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Priority, Role, Status, Ticket, User

# Module-level so every call across a test (or across tests) gets a
# distinct ticket_id — a per-call range starting back at 0 collides the
# moment a test creates tickets in more than one batch.
_ticket_id_seq = itertools.count(100000000)


async def _make_tickets(session: AsyncSession, count: int, **overrides: object) -> list[Ticket]:
    tickets = []
    for _ in range(count):
        n = next(_ticket_id_seq)
        ticket = Ticket(
            ticket_id=str(n),
            customer=f"Customer{n}",
            priority=Priority.LOW,
            status=Status.OPEN,
            hours=Decimal("1.5"),
        )
        for key, value in overrides.items():
            setattr(ticket, key, value)
        session.add(ticket)
        tickets.append(ticket)
    await session.flush()
    return tickets


async def test_default_page_size_is_30(
    client: AsyncClient,
    db_session: AsyncSession,
    make_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    agent = await make_user(username="agent1", role=Role.AGENT)
    await _make_tickets(db_session, 35)

    response = await client.get("/tickets", headers=auth_headers(agent))

    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 30
    assert body["total"] == 35
    assert body["page"] == 1
    assert body["page_size"] == 30


async def test_page_size_above_100_fails_422(
    client: AsyncClient, make_user: Callable[..., Awaitable[User]], auth_headers: Callable[[User], dict[str, str]]
) -> None:
    agent = await make_user(username="agent1", role=Role.AGENT)

    response = await client.get("/tickets?page_size=150", headers=auth_headers(agent))

    assert response.status_code == 422


async def test_page_size_of_exactly_100_is_allowed(
    client: AsyncClient, make_user: Callable[..., Awaitable[User]], auth_headers: Callable[[User], dict[str, str]]
) -> None:
    agent = await make_user(username="agent1", role=Role.AGENT)

    response = await client.get("/tickets?page_size=100", headers=auth_headers(agent))

    assert response.status_code == 200


async def test_second_page_returns_the_remainder(
    client: AsyncClient,
    db_session: AsyncSession,
    make_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    agent = await make_user(username="agent1", role=Role.AGENT)
    await _make_tickets(db_session, 35)

    response = await client.get("/tickets?page=2", headers=auth_headers(agent))

    assert response.status_code == 200
    assert len(response.json()["items"]) == 5


async def test_filter_by_status(
    client: AsyncClient,
    db_session: AsyncSession,
    make_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    agent = await make_user(username="agent1", role=Role.AGENT)
    await _make_tickets(db_session, 3, status=Status.OPEN)
    await _make_tickets(db_session, 2, status=Status.CLOSED, customer="ClosedCo")

    response = await client.get("/tickets?status=closed", headers=auth_headers(agent))

    body = response.json()
    assert body["total"] == 2
    assert all(item["status"] == "closed" for item in body["items"])


async def test_filter_by_assigned_agent_id(
    client: AsyncClient,
    db_session: AsyncSession,
    make_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    admin = await make_user(username="admin1", role=Role.ADMIN)
    agent1 = await make_user(username="agent1", role=Role.AGENT)
    agent2 = await make_user(username="agent2", role=Role.AGENT)
    await _make_tickets(db_session, 2, assigned_agent_id=agent1.id)
    await _make_tickets(db_session, 3, assigned_agent_id=agent2.id)

    response = await client.get(f"/tickets?assigned_agent_id={agent1.id}", headers=auth_headers(admin))

    assert response.json()["total"] == 2


async def test_sort_by_hours_descending(
    client: AsyncClient,
    db_session: AsyncSession,
    make_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    admin = await make_user(username="admin1", role=Role.ADMIN)
    db_session.add(Ticket(ticket_id="111111111", customer="A", priority=Priority.LOW, status=Status.OPEN, hours=Decimal("1.0")))
    db_session.add(Ticket(ticket_id="222222222", customer="B", priority=Priority.LOW, status=Status.OPEN, hours=Decimal("5.0")))
    db_session.add(Ticket(ticket_id="333333333", customer="C", priority=Priority.LOW, status=Status.OPEN, hours=Decimal("3.0")))
    await db_session.flush()

    response = await client.get("/tickets?sort=hours&order=desc", headers=auth_headers(admin))

    hours_in_order = [item["hours"] for item in response.json()["items"]]
    assert hours_in_order == ["5.0", "3.0", "1.0"]


async def test_invalid_sort_field_fails_422(
    client: AsyncClient, make_user: Callable[..., Awaitable[User]], auth_headers: Callable[[User], dict[str, str]]
) -> None:
    agent = await make_user(username="agent1", role=Role.AGENT)

    response = await client.get("/tickets?sort=id", headers=auth_headers(agent))

    assert response.status_code == 422


async def test_agent_and_admin_both_see_all_tickets(
    client: AsyncClient,
    db_session: AsyncSession,
    make_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    admin = await make_user(username="admin1", role=Role.ADMIN)
    agent1 = await make_user(username="agent1", role=Role.AGENT)
    agent2 = await make_user(username="agent2", role=Role.AGENT)
    await _make_tickets(db_session, 2, assigned_agent_id=agent2.id)

    admin_view = await client.get("/tickets", headers=auth_headers(admin))
    agent_view = await client.get("/tickets", headers=auth_headers(agent1))

    assert admin_view.json()["total"] == agent_view.json()["total"] == 2


async def test_summary_counts_by_status_priority_and_customer(
    client: AsyncClient,
    db_session: AsyncSession,
    make_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    agent = await make_user(username="agent1", role=Role.AGENT)
    db_session.add(
        Ticket(
            ticket_id="111111111", customer="Acme", priority=Priority.HIGH, status=Status.OPEN, hours=Decimal("1.0")
        )
    )
    db_session.add(
        Ticket(
            ticket_id="222222222",
            customer="Acme",
            priority=Priority.LOW,
            status=Status.CLOSED,
            hours=Decimal("2.0"),
        )
    )
    db_session.add(
        Ticket(
            ticket_id="333333333",
            customer="Globex",
            priority=Priority.HIGH,
            status=Status.OPEN,
            hours=Decimal("3.0"),
        )
    )
    await db_session.flush()

    response = await client.get("/tickets/summary", headers=auth_headers(agent))

    assert response.status_code == 200
    body = response.json()
    assert body["by_status"] == {"open": 2, "closed": 1}
    assert body["by_priority"] == {"high": 2, "low": 1}
    assert body["by_customer"] == {"Acme": 2, "Globex": 1}


async def test_summary_route_is_not_shadowed_by_the_get_by_id_route(
    client: AsyncClient, make_user: Callable[..., Awaitable[User]], auth_headers: Callable[[User], dict[str, str]]
) -> None:
    admin = await make_user(username="admin1", role=Role.ADMIN)

    response = await client.get("/tickets/summary", headers=auth_headers(admin))

    assert response.status_code == 200
    assert set(response.json().keys()) == {"by_status", "by_priority", "by_customer"}
