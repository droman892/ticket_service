from ..models import Status, Ticket


class TicketNotEditableError(Exception):
    """Raised for any edit attempt on a closed ticket."""


def ensure_editable(ticket: Ticket) -> None:
    """A closed ticket is 100% immutable — every other transition (open <->
    in_progress, either -> closed) is allowed, so the only rule worth
    encoding is this one: nothing changes once status is closed, for
    anyone, no admin override (requirements.md, ticket lifecycle)."""
    if ticket.status is Status.CLOSED:
        raise TicketNotEditableError()
