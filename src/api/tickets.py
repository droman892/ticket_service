from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import Priority, Role, Status, Ticket, User
from ..repositories import ticket_repository
from ..schemas.ticket import (
    SortField,
    SortOrder,
    TicketCreate,
    TicketPage,
    TicketResponse,
    TicketSummary,
    TicketUpdate,
)
from ..services.ticket_lifecycle import TicketNotEditableError
from ..services.ticket_service import DuplicateTicketIdError, InvalidAssignedAgentError, create_ticket, update_ticket
from .deps import get_current_user

router = APIRouter(prefix="/tickets", tags=["tickets"])


@router.post("", response_model=TicketResponse, status_code=status.HTTP_201_CREATED)
async def create(
    body: TicketCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Ticket:
    if (
        current_user.role is Role.AGENT
        and body.assigned_agent_id is not None
        and body.assigned_agent_id != current_user.id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Agents can only assign a new ticket to themselves",
        )

    try:
        return await create_ticket(session, body)
    except DuplicateTicketIdError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="ticket_id already exists")
    except InvalidAssignedAgentError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


@router.get("/summary", response_model=TicketSummary)
async def summary(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> TicketSummary:
    # Registered before /{ticket_id}: routes match in registration order,
    # and an unqualified /{ticket_id} would otherwise capture "/summary"
    # first and fail trying to parse "summary" as an int.
    by_status, by_priority, by_customer = await ticket_repository.get_summary(session)
    return TicketSummary(by_status=by_status, by_priority=by_priority, by_customer=by_customer)


@router.get("", response_model=TicketPage)
async def list_tickets(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    ticket_id: str | None = Query(default=None),
    customer: str | None = Query(default=None),
    priority: Priority | None = Query(default=None),
    status_: Status | None = Query(default=None, alias="status"),
    hours: Decimal | None = Query(default=None),
    assigned_agent_id: int | None = Query(default=None),
    sort: SortField = Query(default="created_at"),
    order: SortOrder = Query(default="desc"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=30, ge=1, le=100),
) -> TicketPage:
    items, total = await ticket_repository.list_tickets(
        session,
        ticket_id=ticket_id,
        customer=customer,
        priority=priority,
        status=status_,
        hours=hours,
        assigned_agent_id=assigned_agent_id,
        sort=sort,
        order=order,
        page=page,
        page_size=page_size,
    )
    return TicketPage(
        items=[TicketResponse.model_validate(t) for t in items], total=total, page=page, page_size=page_size
    )


@router.get("/{ticket_id}", response_model=TicketResponse)
async def get(
    ticket_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Ticket:
    ticket = await ticket_repository.get_by_id(session, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")
    return ticket


@router.patch("/{ticket_id}", response_model=TicketResponse)
async def update(
    ticket_id: int,
    body: TicketUpdate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Ticket:
    ticket = await ticket_repository.get_by_id(session, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")

    if current_user.role is Role.AGENT:
        if ticket.assigned_agent_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not permitted")
        if "assigned_agent_id" in body.model_fields_set:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only an admin can reassign a ticket",
            )

    try:
        return await update_ticket(session, ticket, body)
    except TicketNotEditableError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ticket is closed and cannot be edited",
        )
    except InvalidAssignedAgentError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
