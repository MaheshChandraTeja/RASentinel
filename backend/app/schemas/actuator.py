from datetime import datetime

from pydantic import Field, field_validator

from app.models.enums import ActuatorType, HealthStatus
from app.schemas.common import ORMBase, ensure_finite_number


class ActuatorCreate(ORMBase):
    name: str = Field(min_length=1, max_length=160)
    actuator_type: ActuatorType = ActuatorType.UNKNOWN

    manufacturer: str | None = Field(default=None, max_length=160)
    model_number: str | None = Field(default=None, max_length=160)
    serial_number: str | None = Field(default=None, max_length=160)
    location: str | None = Field(default=None, max_length=240)

    rated_torque_nm: float | None = None
    rated_current_a: float | None = None
    rated_voltage_v: float | None = None

    @field_validator("rated_torque_nm", "rated_current_a", "rated_voltage_v")
    @classmethod
    def validate_positive_rating(cls, value: float | None) -> float | None:
        value = ensure_finite_number(value, "rating")
        if value is not None and value < 0:
            raise ValueError("rating values cannot be negative")
        return value


class ActuatorUpdate(ORMBase):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    actuator_type: ActuatorType | None = None

    manufacturer: str | None = Field(default=None, max_length=160)
    model_number: str | None = Field(default=None, max_length=160)
    serial_number: str | None = Field(default=None, max_length=160)
    location: str | None = Field(default=None, max_length=240)

    rated_torque_nm: float | None = None
    rated_current_a: float | None = None
    rated_voltage_v: float | None = None
    health_status: HealthStatus | None = None


class ActuatorRead(ORMBase):
    id: str
    name: str
    actuator_type: ActuatorType

    manufacturer: str | None
    model_number: str | None
    serial_number: str | None
    location: str | None

    rated_torque_nm: float | None
    rated_current_a: float | None
    rated_voltage_v: float | None

    health_status: HealthStatus
    created_at: datetime
    updated_at: datetime