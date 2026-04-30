from datetime import datetime

from pydantic import Field, field_validator, model_validator

from app.models.enums import FaultLabel
from app.schemas.common import ORMBase, ensure_finite_number, normalize_datetime


class TelemetrySampleCreate(ORMBase):
    timestamp: datetime | None = None

    commanded_position: float | None = None
    actual_position: float | None = None

    commanded_velocity: float | None = None
    actual_velocity: float | None = None

    commanded_torque: float | None = None
    estimated_torque: float | None = None

    motor_current: float | None = None
    temperature: float | None = None
    load_estimate: float | None = None

    control_latency_ms: float | None = None
    encoder_position: float | None = None

    error_position: float | None = None
    error_velocity: float | None = None

    fault_label: FaultLabel = FaultLabel.NONE

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp(cls, value: datetime | None) -> datetime | None:
        return normalize_datetime(value)

    @field_validator(
        "commanded_position",
        "actual_position",
        "commanded_velocity",
        "actual_velocity",
        "commanded_torque",
        "estimated_torque",
        "motor_current",
        "temperature",
        "load_estimate",
        "control_latency_ms",
        "encoder_position",
        "error_position",
        "error_velocity",
    )
    @classmethod
    def validate_numeric(cls, value: float | None) -> float | None:
        return ensure_finite_number(value, "telemetry field")

    @model_validator(mode="after")
    def validate_ranges(self) -> "TelemetrySampleCreate":
        if self.motor_current is not None and self.motor_current < 0:
            raise ValueError("motor_current cannot be negative")

        if self.control_latency_ms is not None and self.control_latency_ms < 0:
            raise ValueError("control_latency_ms cannot be negative")

        if self.temperature is not None and self.temperature <= -273.15:
            raise ValueError("temperature must be above absolute zero")

        if self.error_position is None:
            if self.commanded_position is not None and self.actual_position is not None:
                self.error_position = self.commanded_position - self.actual_position

        if self.error_velocity is None:
            if self.commanded_velocity is not None and self.actual_velocity is not None:
                self.error_velocity = self.commanded_velocity - self.actual_velocity

        return self


class TelemetryBulkCreate(ORMBase):
    samples: list[TelemetrySampleCreate] = Field(min_length=1, max_length=10_000)


class TelemetrySampleRead(ORMBase):
    id: int
    session_id: str
    actuator_id: str
    timestamp: datetime

    commanded_position: float | None
    actual_position: float | None

    commanded_velocity: float | None
    actual_velocity: float | None

    commanded_torque: float | None
    estimated_torque: float | None

    motor_current: float | None
    temperature: float | None
    load_estimate: float | None

    control_latency_ms: float | None
    encoder_position: float | None

    error_position: float | None
    error_velocity: float | None

    fault_label: FaultLabel