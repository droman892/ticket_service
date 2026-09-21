from decimal import Decimal
from typing import Any

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from ..models import Priority, Status, Ticket
from ..schemas.ticket import SortField, SortOrder

_SORTABLE_COLUMNS: dict[SortField, InstrumentedAttribute[Any]] = {
    "ticket_id": Ticket.ticket_id,
    "customer": Ticket.customer,
    "priority": Ticket.priority,
    "status": Ticket.status,
    "hours": Ticket.hours,
    "assigned_agent_id": Ticket.assigned_agent_id,
    "created_at": Ticket.created_at,
    "updated_at": Ticket.updated_at,
}


async def get_by_id(session: AsyncSession, ticket_id: int) -> Ticket | None:
    return await session.get(Ticket, ticket_id)


async def get_existing_ticket_ids(session: AsyncSession, ticket_ids: list[str]) -> set[str]:
    """One query for however many ids a whole CSV import needs checked,
    instead of one query per row — matters for the 10,000-row NFR."""
    if not ticket_ids:
        return set()
    result = await session.execute(select(Ticket.ticket_id).where(Ticket.ticket_id.in_(ticket_ids)))
    return set(result.scalars().all())


async def list_tickets(
    session: AsyncSession,
    *,
    ticket_id: str | None,
    customer: str | None,
    priority: Priority | None,
    status: Status | None,
    hours: Decimal | None,
    assigned_agent_id: int | None,
    sort: SortField,
    order: SortOrder,
    page: int,
    page_size: int,
) -> tuple[list[Ticket], int]:
    filters: list[ColumnElement[bool]] = []
    if ticket_id is not None:
        filters.append(Ticket.ticket_id == ticket_id)
    if customer is not None:
        filters.append(Ticket.customer == customer)
    if priority is not None:
        filters.append(Ticket.priority == priority)
    if status is not None:
        filters.append(Ticket.status == status)
    if hours is not None:
        filters.append(Ticket.hours == hours)
    if assigned_agent_id is not None:
        filters.append(Ticket.assigned_agent_id == assigned_agent_id)

    count_stmt = select(func.count()).select_from(Ticket).where(*filters)
    total = (await session.execute(count_stmt)).scalar_one()

    sort_column = _SORTABLE_COLUMNS[sort]
    ordering = sort_column.desc() if order == "desc" else sort_column.asc()
    # Ticket.id is always the final tiebreaker (never itself user-facing as
    # a sort key — FR11 excludes it) so pagination stays stable when the
    # chosen sort field has duplicate values across many rows.
    items_stmt = (
        select(Ticket)
        .where(*filters)
        .order_by(ordering, Ticket.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = list((await session.execute(items_stmt)).scalars().all())

    return items, total


async def get_summary(session: AsyncSession) -> tuple[dict[str, int], dict[str, int], dict[str, int]]:
    status_rows = (await session.execute(select(Ticket.status, func.count()).group_by(Ticket.status))).all()
    priority_rows = (await session.execute(select(Ticket.priority, func.count()).group_by(Ticket.priority))).all()
    customer_rows = (await session.execute(select(Ticket.customer, func.count()).group_by(Ticket.customer))).all()

    return (
        {row[0].value: row[1] for row in status_rows},
        {row[0].value: row[1] for row in priority_rows},
        {row[0]: row[1] for row in customer_rows},
    )
