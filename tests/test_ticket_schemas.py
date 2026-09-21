import pytest
from pydantic import ValidationError

from src.schemas.ticket import TicketUpdate


@pytest.mark.parametrize("field_name", ["customer", "priority", "status", "hours"])
def test_explicit_null_is_rejected_for_non_nullable_fields(field_name: str) -> None:
    with pytest.raises(ValidationError):
        TicketUpdate(**{field_name: None})


def test_omitting_a_field_is_fine() -> None:
    TicketUpdate()  # does not raise


def test_explicit_null_is_allowed_for_assigned_agent_id() -> None:
    update = TicketUpdate(assigned_agent_id=None)

    assert "assigned_agent_id" in update.model_fields_set
    assert update.assigned_agent_id is None
