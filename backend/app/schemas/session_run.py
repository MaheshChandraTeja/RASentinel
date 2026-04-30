from datetime import datetime

from pydantic import Field, field_validator

from app.schemas.common import ORMBase, normalize_datetime


class SessionRunCreate(ORMBase):
    name: str = Field(min_length=1, max_length=180)
    source: str = Field(default="manual", min_length=1, max_length=120)
    notes: str | None = Field(default=None, max_length=2000)
    started_at: datetime | None = None
    ended_at: datetime | None = None
    tags: dict = Field(default_factory=dict)

    @field_validator("started_at", "ended_at")
    @classmethod
    def validate_datetime(cls, value: datetime | None) -> datetime | None:
        return normalize_datetime(value)


class SessionRunRead(ORMBase):
    id: str
    actuator_id: str
    name: str
    source: str
    notes: str | None
    started_at: datetime
    ended_at: datetime | None
    sample_count: int
    tags: dict