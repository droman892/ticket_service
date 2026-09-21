from collections.abc import Awaitable, Callable
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Priority, Role, Status, User
from src.schemas.ticket import TicketCreate, TicketUpdate
from src.services.ticket_lifecycle import TicketNotEditableError
from src.services.ticket_service import (
    DuplicateTicketIdError,
    InvalidAssignedAgentError,
    create_ticket,
    update_ticket,
)

VALID_CREATE = TicketCreate(ticket_id="123456789", customer="Acme", priority=Priority.LOW, hours=Decimal("1.5"))


async def test_create_ticket_succeeds_and_defaults_to_open(db_session: AsyncSession) -> None:
    ticket = await create_ticket(db_session, VALID_CREATE)

    assert ticket.id is not None
    assert ticket.status is Status.OPEN
    assert ticket.assigned_agent_id is None


async def test_create_ticket_rejects_a_duplicate_ticket_id(db_session: AsyncSession) -> None:
    await create_ticket(db_session, VALID_CREATE)

    with pytest.raises(DuplicateTicketIdError):
        await create_ticket(db_session, VALID_CREATE)


async def test_create_ticket_can_assign_to_a_real_agent(
    db_session: AsyncSession, make_user: Callable[..., Awaitable[User]]
) -> None:
    agent = await make_user(username="agent1", role=Role.AGENT)

    ticket = await create_ticket(db_session, VALID_CREATE.model_copy(update={"assigned_agent_id": agent.id}))

    assert ticket.assigned_agent_id == agent.id


async def test_create_ticket_rejects_an_unknown_assigned_agent_id(db_session: AsyncSession) -> None:
    with pytest.raises(InvalidAssignedAgentError):
        await create_ticket(db_session, VALID_CREATE.model_copy(update={"assigned_agent_id": 999_999}))


async def test_create_ticket_rejects_assigning_to_an_admin(
    db_session: AsyncSession, make_user: Callable[..., Awaitable[User]]
) -> None:
    admin = await make_user(username="admin1", role=Role.ADMIN)

    with pytest.raises(InvalidAssignedAgentError):
        await create_ticket(db_session, VALID_CREATE.model_copy(update={"assigned_agent_id": admin.id}))


async def test_update_ticket_applies_given_fields(db_session: AsyncSession) -> None:
    ticket = await create_ticket(db_session, VALID_CREATE)

    updated = await update_ticket(db_session, ticket, TicketUpdate(status=Status.IN_PROGRESS, hours=Decimal("2.0")))

    assert updated.status is Status.IN_PROGRESS
    assert updated.hours == Decimal("2.0")
    assert updated.customer == "Acme"  # untouched


async def test_update_ticket_can_unassign_with_explicit_null(
    db_session: AsyncSession, make_user: Callable[..., Awaitable[User]]
) -> None:
    agent = await make_user(username="agent1", role=Role.AGENT)
    ticket = await create_ticket(db_session, VALID_CREATE.model_copy(update={"assigned_agent_id": agent.id}))

    updated = await update_ticket(db_session, ticket, TicketUpdate(assigned_agent_id=None))

    assert updated.assigned_agent_id is None


async def test_update_ticket_rejects_reassigning_to_an_unknown_agent(db_session: AsyncSession) -> None:
    ticket = await create_ticket(db_session, VALID_CREATE)

    with pytest.raises(InvalidAssignedAgentError):
        await update_ticket(db_session, ticket, TicketUpdate(assigned_agent_id=999_999))


async def test_update_ticket_on_a_closed_ticket_is_rejected(db_session: AsyncSession) -> None:
    ticket = await create_ticket(db_session, VALID_CREATE.model_copy(update={"status": Status.CLOSED}))

    with pytest.raises(TicketNotEditableError):
        await update_ticket(db_session, ticket, TicketUpdate(customer="New Name"))
