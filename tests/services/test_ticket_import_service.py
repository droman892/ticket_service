import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.ticket_import_service import MalformedCsvError, import_tickets_csv

HEADER = "ticket_id,customer,priority,status,hours\n"


def _csv(*rows: str) -> bytes:
    return (HEADER + "\n".join(rows)).encode("utf-8")


async def test_valid_rows_are_all_inserted(db_session: AsyncSession) -> None:
    content = _csv(
        "111111111,Acme,low,open,1.5",
        "222222222,Globex,high,closed,4.0",
    )

    result = await import_tickets_csv(db_session, content)

    assert result.total == 2
    assert result.inserted == 2
    assert result.skipped == 0
    assert result.errors == []


async def test_invalid_row_is_reported_and_others_still_import(db_session: AsyncSession) -> None:
    content = _csv(
        "111111111,Acme,low,open,1.5",
        "not-nine-digits,Globex,high,open,1.0",
        "333333333,Initech,medium,open,2.0",
    )

    result = await import_tickets_csv(db_session, content)

    assert result.total == 3
    assert result.inserted == 2
    assert result.skipped == 1
    assert result.errors[0].row_number == 2
    assert result.errors[0].ticket_id == "not-nine-digits"


async def test_duplicate_ticket_id_within_the_file_is_reported_on_the_second_occurrence(
    db_session: AsyncSession,
) -> None:
    content = _csv(
        "111111111,Acme,low,open,1.5",
        "111111111,Acme,low,open,2.0",
    )

    result = await import_tickets_csv(db_session, content)

    assert result.inserted == 1
    assert result.skipped == 1
    assert result.errors[0].row_number == 2
    assert "earlier in this file" in result.errors[0].reason


async def test_ticket_id_already_in_the_db_is_skipped_and_not_overwritten(db_session: AsyncSession) -> None:
    await import_tickets_csv(db_session, _csv("111111111,Original,low,open,1.5"))

    result = await import_tickets_csv(db_session, _csv("111111111,Different,high,closed,4.0"))

    assert result.inserted == 0
    assert result.skipped == 1
    assert "already exists" in result.errors[0].reason


async def test_hours_off_step_is_reported(db_session: AsyncSession) -> None:
    result = await import_tickets_csv(db_session, _csv("111111111,Acme,low,open,1.3"))

    assert result.inserted == 0
    assert result.skipped == 1


async def test_malformed_headers_raise_before_any_row_is_processed(db_session: AsyncSession) -> None:
    content = b"wrong,columns,entirely\nfoo,bar,baz\n"

    with pytest.raises(MalformedCsvError):
        await import_tickets_csv(db_session, content)


async def test_non_utf8_content_raises_malformed_csv_error(db_session: AsyncSession) -> None:
    content = "111111111,Ación,low,open,1.5".encode("latin-1")  # non-UTF-8 byte sequence
    content = HEADER.encode("utf-8") + content

    with pytest.raises(MalformedCsvError):
        await import_tickets_csv(db_session, content)


async def test_empty_file_with_only_a_header_imports_nothing(db_session: AsyncSession) -> None:
    result = await import_tickets_csv(db_session, HEADER.encode("utf-8"))

    assert result.total == 0
    assert result.inserted == 0
    assert result.errors == []
