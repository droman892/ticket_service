from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Priority, Status, Ticket

VALID_TICKET = {
    "ticket_id": "123456789",
    "customer": "Acme",
    "priority": Priority.LOW,
    "status": Status.OPEN,
    "hours": Decimal("1.5"),
}


async def test_migrated_schema_has_expected_tables(db_session: AsyncSession) -> None:
    result = await db_session.execute(
        text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
    )
    tables = {row[0] for row in result}

    assert {"users", "tickets", "alembic_version"} <= tables


async def test_ticket_round_trips_through_the_orm(db_session: AsyncSession) -> None:
    ticket = Ticket(**VALID_TICKET)
    db_session.add(ticket)
    await db_session.flush()
    await db_session.refresh(ticket)

    assert ticket.id is not None
    assert ticket.priority is Priority.LOW
    assert ticket.status is Status.OPEN


@pytest.mark.parametrize("bad_ticket_id", ["12345", "1234567890", "12345678a", ""])
async def test_ticket_id_must_be_exactly_nine_digits(db_session: AsyncSession, bad_ticket_id: str) -> None:
    """Too-short/non-digit values fail the CHECK constraint (IntegrityError);
    the one 10-digit case instead overflows the VARCHAR(9) column itself
    (DataError). Both are DBAPIError, and both are the DB correctly
    rejecting the value — which mechanism catches it isn't the point."""
    ticket = Ticket(**{**VALID_TICKET, "ticket_id": bad_ticket_id})
    db_session.add(ticket)

    with pytest.raises(DBAPIError):
        await db_session.flush()


@pytest.mark.parametrize("bad_hours", [Decimal("0"), Decimal("40.5"), Decimal("1.3")])
async def test_hours_must_be_in_range_and_on_a_half_hour_step(db_session: AsyncSession, bad_hours: Decimal) -> None:
    ticket = Ticket(**{**VALID_TICKET, "hours": bad_hours})
    db_session.add(ticket)

    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_assigned_agent_must_reference_a_real_user(db_session: AsyncSession) -> None:
    ticket = Ticket(**{**VALID_TICKET, "assigned_agent_id": 999_999})
    db_session.add(ticket)

    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_priority_column_rejects_a_value_outside_the_enum_at_the_db_level(db_session: AsyncSession) -> None:
    """Bypasses the ORM (which would refuse an invalid enum client-side) to
    prove Postgres itself — not just app code — enforces the enum."""
    with pytest.raises(DBAPIError):
        await db_session.execute(
            text(
                "INSERT INTO tickets (ticket_id, customer, priority, status, hours) "
                "VALUES ('123456789', 'Acme', 'urgent', 'open', 1.5)"
            )
        )
