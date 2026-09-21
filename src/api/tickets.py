from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import Role, Ticket, User
from ..repositories import ticket_repository
from ..schemas.ticket import TicketCreate, TicketResponse, TicketUpdate
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
