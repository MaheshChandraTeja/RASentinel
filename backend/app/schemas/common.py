from datetime import datetime, timezone
from math import isfinite
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator


class ORMBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class MessageResponse(BaseModel):
    message: str


class PaginatedResponse(BaseModel):
    items: list[Any]
    total: int


def ensure_finite_number(value: float | None, field_name: str) -> float | None:
    if value is None:
        return value

    if not isfinite(value):
        raise ValueError(f"{field_name} must be a finite number")

    return value


def normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return value

    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)

    return value