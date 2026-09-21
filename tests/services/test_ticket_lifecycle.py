import pytest

from src.models import Priority, Status, Ticket
from src.services.ticket_lifecycle import TicketNotEditableError, ensure_editable


def _ticket(status: Status) -> Ticket:
    return Ticket(ticket_id="123456789", customer="Acme", priority=Priority.LOW, status=status, hours=1)


@pytest.mark.parametrize("status", [Status.OPEN, Status.IN_PROGRESS])
def test_open_and_in_progress_tickets_are_editable(status: Status) -> None:
    ensure_editable(_ticket(status))  # does not raise


def test_closed_ticket_is_not_editable() -> None:
    with pytest.raises(TicketNotEditableError):
        ensure_editable(_ticket(Status.CLOSED))
