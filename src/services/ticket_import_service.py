import csv
import io

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Ticket
from ..repositories import ticket_repository
from ..schemas.ticket import TicketCreate
from ..schemas.ticket_import import ImportResult, ImportRowError

REQUIRED_COLUMNS = {"ticket_id", "customer", "priority", "status", "hours"}


class MalformedCsvError(Exception):
    pass


def _summarize_validation_error(exc: ValidationError) -> str:
    parts = [f"{'.'.join(str(loc) for loc in err['loc'])}: {err['msg']}" for err in exc.errors()]
    return "; ".join(parts)


async def import_tickets_csv(session: AsyncSession, content: bytes) -> ImportResult:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        raise MalformedCsvError("File is not valid UTF-8 text")

    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None or set(reader.fieldnames) != REQUIRED_COLUMNS:
        raise MalformedCsvError(
            f"CSV header must be exactly: {', '.join(sorted(REQUIRED_COLUMNS))}"
        )

    rows = list(reader)

    # Pass 1: validate every row against the same rules POST /tickets uses
    # (TicketCreate), without touching the DB yet. status is always taken
    # from the column — unlike POST /tickets, it must not default to
    # "open" here, since the header check above guarantees the column
    # exists and an empty/bad value should be reported, not silently
    # replaced.
    validated: dict[int, TicketCreate] = {}
    errors: list[ImportRowError] = []
    for row_number, row in enumerate(rows, start=1):
        raw_ticket_id = (row.get("ticket_id") or "").strip()
        try:
            validated[row_number] = TicketCreate(
                ticket_id=row.get("ticket_id", ""),
                customer=row.get("customer", ""),
                priority=row.get("priority", ""),
                status=row.get("status", ""),
                hours=row.get("hours", ""),
            )
        except ValidationError as exc:
            errors.append(
                ImportRowError(row_number=row_number, ticket_id=raw_ticket_id, reason=_summarize_validation_error(exc))
            )

    # One bulk query for every ticket_id already in the DB, instead of one
    # query per row.
    candidate_ids = [tc.ticket_id for tc in validated.values()]
    existing_ids = await ticket_repository.get_existing_ticket_ids(session, candidate_ids)

    # Pass 2: apply the two conflict rules in file order, so the first
    # occurrence of a ticket_id wins and later ones are reported as
    # duplicates — matches requirements.md's "existing row is not
    # overwritten" for DB conflicts, extended the same way to in-file ones.
    seen_in_file: set[str] = set()
    to_insert: list[Ticket] = []
    for row_number, data in validated.items():
        if data.ticket_id in existing_ids:
            errors.append(
                ImportRowError(row_number=row_number, ticket_id=data.ticket_id, reason="duplicate ticket_id: already exists")
            )
        elif data.ticket_id in seen_in_file:
            errors.append(
                ImportRowError(
                    row_number=row_number,
                    ticket_id=data.ticket_id,
                    reason="duplicate ticket_id: appears earlier in this file",
                )
            )
        else:
            seen_in_file.add(data.ticket_id)
            to_insert.append(
                Ticket(
                    ticket_id=data.ticket_id,
                    customer=data.customer,
                    priority=data.priority,
                    status=data.status,
                    hours=data.hours,
                )
            )

    # One transaction for the whole batch: if something unexpected fails
    # here (a DB error, not a row-validation failure — those were already
    # filtered out above), everything rolls back together rather than
    # leaving a partial import (NFR: reliability/error handling).
    session.add_all(to_insert)
    await session.commit()

    errors.sort(key=lambda e: e.row_number)
    return ImportResult(total=len(rows), inserted=len(to_insert), skipped=len(errors), errors=errors)
