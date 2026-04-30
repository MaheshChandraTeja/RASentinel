from datetime import datetime

from pydantic import Field, field_validator

from app.models.enums import CommandMode
from app.schemas.common import ORMBase, ensure_finite_number, normalize_datetime


class CommandSignalCreate(ORMBase):
    timestamp: datetime | None = None
    command_mode: CommandMode = CommandMode.POSITION

    commanded_position: float | None = None
    commanded_velocity: float | None = None
    commanded_torque: float | None = None

    expected_response_ms: float | None = None
    command_source: str = Field(default="manual", min_length=1, max_length=120)

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp(cls, value: datetime | None) -> datetime | None:
        return normalize_datetime(value)

    @field_validator(
        "commanded_position",
        "commanded_velocity",
        "commanded_torque",
        "expected_response_ms",
    )
    @classmethod
    def validate_numeric(cls, value: float | None) -> float | None:
        return ensure_finite_number(value, "command field")


class CommandSignalRead(ORMBase):
    id: int
    session_id: str
    actuator_id: str
    timestamp: datetime
    command_mode: CommandMode

    commanded_position: float | None
    commanded_velocity: float | None
    commanded_torque: float | None

    expected_response_ms: float | None
    command_source: str