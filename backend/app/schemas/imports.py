from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class DuplicateSessionStrategy(StrEnum):
    REJECT = "reject"
    CREATE_NEW = "create_new"
    REPLACE = "replace"


class ImportSourceFormat(StrEnum):
    CSV = "csv"
    JSON = "json"
    SYNTHETIC = "synthetic"


class ImportValidationIssue(BaseModel):
    row: int | None = None
    field: str | None = None
    message: str


class TelemetryImportResponse(BaseModel):
    import_job_id: str
    actuator_id: str
    session_id: str
    session_name: str
    source_format: ImportSourceFormat
    duplicate_strategy: DuplicateSessionStrategy
    rows_received: int
    rows_imported: int
    rows_failed: int
    status: str
    errors: list[ImportValidationIssue] = Field(default_factory=list)
    created_at: datetime
