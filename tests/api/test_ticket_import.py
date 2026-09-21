from collections.abc import Awaitable, Callable

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Role, User

HEADER = "ticket_id,customer,priority,status,hours\n"


def _csv_file(*rows: str) -> dict[str, tuple[str, bytes, str]]:
    content = (HEADER + "\n".join(rows)).encode("utf-8")
    return {"file": ("tickets.csv", content, "text/csv")}


async def test_admin_can_import_a_valid_csv(
    client: AsyncClient, make_user: Callable[..., Awaitable[User]], auth_headers: Callable[[User], dict[str, str]]
) -> None:
    admin = await make_user(username="admin1", role=Role.ADMIN)

    response = await client.post(
        "/tickets/import",
        files=_csv_file("111111111,Acme,low,open,1.5", "222222222,Globex,high,closed,4.0"),
        headers=auth_headers(admin),
    )

    assert response.status_code == 200
    body = response.json()
    assert body == {"total": 2, "inserted": 2, "skipped": 0, "errors": []}


async def test_agent_cannot_import(
    client: AsyncClient, make_user: Callable[..., Awaitable[User]], auth_headers: Callable[[User], dict[str, str]]
) -> None:
    agent = await make_user(username="agent1", role=Role.AGENT)

    response = await client.post(
        "/tickets/import", files=_csv_file("111111111,Acme,low,open,1.5"), headers=auth_headers(agent)
    )

    assert response.status_code == 403


async def test_unauthenticated_cannot_import(client: AsyncClient) -> None:
    response = await client.post("/tickets/import", files=_csv_file("111111111,Acme,low,open,1.5"))

    assert response.status_code == 401


async def test_malformed_csv_header_fails_422(
    client: AsyncClient, make_user: Callable[..., Awaitable[User]], auth_headers: Callable[[User], dict[str, str]]
) -> None:
    admin = await make_user(username="admin1", role=Role.ADMIN)

    response = await client.post(
        "/tickets/import",
        files={"file": ("bad.csv", b"wrong,columns\nfoo,bar\n", "text/csv")},
        headers=auth_headers(admin),
    )

    assert response.status_code == 422


async def test_oversized_file_fails_413(
    client: AsyncClient, make_user: Callable[..., Awaitable[User]], auth_headers: Callable[[User], dict[str, str]]
) -> None:
    admin = await make_user(username="admin1", role=Role.ADMIN)
    oversized = HEADER.encode("utf-8") + b"1" * (5 * 1024 * 1024 + 1)

    response = await client.post(
        "/tickets/import",
        files={"file": ("huge.csv", oversized, "text/csv")},
        headers=auth_headers(admin),
    )

    assert response.status_code == 413


async def test_partial_success_reports_errors_and_only_inserts_valid_rows(
    client: AsyncClient,
    db_session: AsyncSession,
    make_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    admin = await make_user(username="admin1", role=Role.ADMIN)
    # Pre-existing ticket in the DB that the import file will conflict with.
    create_response = await client.post(
        "/tickets",
        json={"ticket_id": "999999999", "customer": "Existing", "priority": "low", "hours": 1.0},
        headers=auth_headers(admin),
    )
    assert create_response.status_code == 201

    response = await client.post(
        "/tickets/import",
        files=_csv_file(
            "111111111,Acme,low,open,1.5",
            "999999999,Acme,low,open,2.0",  # conflicts with the pre-existing ticket
            "bad-id,Acme,low,open,1.0",  # invalid ticket_id
        ),
        headers=auth_headers(admin),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert body["inserted"] == 1
    assert body["skipped"] == 2
    reasons_by_row = {e["row_number"]: e["reason"] for e in body["errors"]}
    assert "already exists" in reasons_by_row[2]
    assert 3 in reasons_by_row
