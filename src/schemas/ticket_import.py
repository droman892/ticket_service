from pydantic import BaseModel


class ImportRowError(BaseModel):
    row_number: int
    ticket_id: str
    reason: str


class ImportResult(BaseModel):
    total: int
    inserted: int
    skipped: int
    errors: list[ImportRowError]
