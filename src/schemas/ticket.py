from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..models import Priority, Status

TICKET_ID_PATTERN = r"^[0-9]{9}$"


def _validate_half_hour_step(value: Decimal | None) -> Decimal | None:
    if value is not None and (value * 2) % 1 != 0:
        raise ValueError("hours must be in increments of 0.5")
    return value


class TicketCreate(BaseModel):
    ticket_id: str = Field(pattern=TICKET_ID_PATTERN)
    customer: str = Field(min_length=1, max_length=30)
    priority: Priority
    status: Status = Status.OPEN
    hours: Decimal = Field(ge=Decimal("0.5"), le=Decimal("40"))
    assigned_agent_id: int | None = None

    @field_validator("hours")
    @classmethod
    def hours_step(cls, v: Decimal) -> Decimal:
        result = _validate_half_hour_step(v)
        assert result is not None
        return result


class TicketUpdate(BaseModel):
    """All fields optional (PATCH semantics). ticket_id is deliberately
    absent — it's the immutable external business identifier.

    assigned_agent_id uses model_fields_set (checked by callers, not here)
    to distinguish "omitted" from "explicitly set to null" (unassign) —
    a plain `is not None` check can't tell those apart."""

    customer: str | None = Field(default=None, min_length=1, max_length=30)
    priority: Priority | None = None
    status: Status | None = None
    hours: Decimal | None = Field(default=None, ge=Decimal("0.5"), le=Decimal("40"))
    assigned_agent_id: int | None = None

    @field_validator("hours")
    @classmethod
    def hours_step(cls, v: Decimal | None) -> Decimal | None:
        return _validate_half_hour_step(v)

    @model_validator(mode="after")
    def reject_explicit_null_for_non_nullable_fields(self) -> "TicketUpdate":
        # Only assigned_agent_id has a meaningful null ("unassign"). For
        # the rest, None only ever means "field omitted" — but Optional[X]
        # can't stop a client from sending an explicit JSON null, which
        # would otherwise reach the DB's NOT NULL constraint as an
        # unhandled error instead of a clean 422.
        for field_name in ("customer", "priority", "status", "hours"):
            if field_name in self.model_fields_set and getattr(self, field_name) is None:
                raise ValueError(f"{field_name} cannot be null")
        return self


class TicketResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticket_id: str
    customer: str
    priority: Priority
    status: Status
    hours: Decimal
    assigned_agent_id: int | None
    created_at: datetime
    updated_at: datetime
