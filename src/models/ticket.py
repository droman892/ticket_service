import enum
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base
from .user import User


class Priority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Status(str, enum.Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    CLOSED = "closed"


class Ticket(Base):
    __tablename__ = "tickets"
    __table_args__ = (
        CheckConstraint("ticket_id ~ '^[0-9]{9}$'", name="ck_tickets_ticket_id_format"),
        CheckConstraint("hours >= 0.5 AND hours <= 40", name="ck_tickets_hours_range"),
        # hours must land on a 0.5 step: doubling it must give a whole number.
        CheckConstraint("(hours * 2) = TRUNC(hours * 2)", name="ck_tickets_hours_step"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[str] = mapped_column(String(9), unique=True, index=True)
    customer: Mapped[str] = mapped_column(String(30))
    priority: Mapped[Priority] = mapped_column(
        Enum(Priority, name="priority", values_callable=lambda e: [m.value for m in e])
    )
    status: Mapped[Status] = mapped_column(
        Enum(Status, name="status", values_callable=lambda e: [m.value for m in e]),
        default=Status.OPEN,
    )
    hours: Mapped[Decimal] = mapped_column(Numeric(4, 1))
    assigned_agent_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    assigned_agent: Mapped[User | None] = relationship()
