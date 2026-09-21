from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Ticket


async def get_by_id(session: AsyncSession, ticket_id: int) -> Ticket | None:
    return await session.get(Ticket, ticket_id)
