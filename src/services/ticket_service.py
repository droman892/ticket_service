from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Role, Ticket
from ..repositories import user_repository
from ..schemas.ticket import TicketCreate, TicketUpdate
from .ticket_lifecycle import ensure_editable


class DuplicateTicketIdError(Exception):
    pass


class InvalidAssignedAgentError(Exception):
    pass


async def _validate_assigned_agent(session: AsyncSession, agent_id: int) -> None:
    user = await user_repository.get_by_id(session, agent_id)
    if user is None or user.role is not Role.AGENT:
        raise InvalidAssignedAgentError(f"assigned_agent_id {agent_id} does not reference an existing agent")


async def create_ticket(session: AsyncSession, data: TicketCreate) -> Ticket:
    if data.assigned_agent_id is not None:
        await _validate_assigned_agent(session, data.assigned_agent_id)

    ticket = Ticket(
        ticket_id=data.ticket_id,
        customer=data.customer,
        priority=data.priority,
        status=data.status,
        hours=data.hours,
        assigned_agent_id=data.assigned_agent_id,
    )
    session.add(ticket)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise DuplicateTicketIdError()

    await session.commit()
    await session.refresh(ticket)
    return ticket


async def update_ticket(session: AsyncSession, ticket: Ticket, data: TicketUpdate) -> Ticket:
    ensure_editable(ticket)

    fields_set = data.model_fields_set

    # Checked before any field is applied: a bad reassignment should leave
    # every other field in the same PATCH untouched, not partially applied.
    if "assigned_agent_id" in fields_set and data.assigned_agent_id is not None:
        await _validate_assigned_agent(session, data.assigned_agent_id)

    if "customer" in fields_set:
        ticket.customer = data.customer  # type: ignore[assignment]
    if "priority" in fields_set:
        ticket.priority = data.priority  # type: ignore[assignment]
    if "status" in fields_set:
        ticket.status = data.status  # type: ignore[assignment]
    if "hours" in fields_set:
        ticket.hours = data.hours  # type: ignore[assignment]
    if "assigned_agent_id" in fields_set:
        # Explicit null here means "unassign" and must be applied — unlike
        # the fields above, None is a meaningful value for this one, not
        # just "field omitted" (that distinction is exactly what
        # model_fields_set is for).
        ticket.assigned_agent_id = data.assigned_agent_id

    await session.commit()
    await session.refresh(ticket)
    return ticket
