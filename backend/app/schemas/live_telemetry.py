from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.enums import FaultLabel
from app.schemas.diagnostics import DiagnosisRunResponse
from app.schemas.features import FeatureVector
from app.schemas.imports import DuplicateSessionStrategy
from app.schemas.telemetry import TelemetrySampleCreate, TelemetrySampleRead


class ControllerTransport(StrEnum):
    HTTP_BRIDGE = "http_bridge"
    SERIAL = "serial"
    ROS2 = "ros2"
    CAN = "can"
    MODBUS = "modbus"
    OPC_UA = "opc_ua"
    PLC = "plc"
    CUSTOM = "custom"


class LiveSessionStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"


class LiveSessionStartRequest(BaseModel):
    actuator_id: str
    session_name: str = Field(min_length=1, max_length=180)
    duplicate_strategy: DuplicateSessionStrategy = DuplicateSessionStrategy.CREATE_NEW

    controller_name: str = Field(default="Hardware controller", min_length=1, max_length=180)
    controller_type: str = Field(default="generic", min_length=1, max_length=120)
    transport: ControllerTransport = ControllerTransport.HTTP_BRIDGE
    endpoint: str | None = Field(default=None, max_length=260)
    sample_rate_hint_hz: float | None = Field(default=None, ge=0.1, le=5000)

    notes: str | None = Field(default=None, max_length=2000)
    tags: dict[str, Any] = Field(default_factory=dict)
    connection_metadata: dict[str, Any] = Field(default_factory=dict)

    auto_extract_features: bool = True
    auto_diagnose_every_n_samples: int | None = Field(default=None, ge=50, le=250_000)
    min_diagnosis_samples: int = Field(default=250, ge=25, le=250_000)


class LiveTelemetrySample(BaseModel):
    """A single sample produced by a hardware bridge.

    Sequence and controller timing fields are accepted for live ingestion bookkeeping,
    but only telemetry fields are persisted into the normal telemetry_samples table.
    """

    sequence_number: int | None = Field(default=None, ge=0)
    controller_timestamp: datetime | None = None
    monotonic_ms: float | None = Field(default=None, ge=0)
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

    @field_validator("timestamp", "controller_timestamp")
    @classmethod
    def normalize_datetime(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return value
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    @model_validator(mode="after")
    def fill_timestamp_and_errors(self) -> "LiveTelemetrySample":
        if self.timestamp is None:
            self.timestamp = self.controller_timestamp or datetime.now(timezone.utc)

        if self.error_position is None:
            if self.commanded_position is not None and self.actual_position is not None:
                self.error_position = self.commanded_position - self.actual_position

        if self.error_velocity is None:
            if self.commanded_velocity is not None and self.actual_velocity is not None:
                self.error_velocity = self.commanded_velocity - self.actual_velocity

        return self

    def to_telemetry_create(self) -> TelemetrySampleCreate:
        data = self.model_dump(
            exclude={"sequence_number", "controller_timestamp", "monotonic_ms"},
            exclude_none=True,
        )
        return TelemetrySampleCreate.model_validate(data)


class LiveTelemetryBatchRequest(BaseModel):
    samples: list[LiveTelemetrySample] = Field(min_length=1, max_length=5_000)
    run_diagnosis: bool = False
    baseline_id: str | None = None
    smoothing_window: int = Field(default=5, ge=1, le=301)
    use_isolation_forest: bool = True
    persist_diagnosis: bool = True


class LiveLatestMetrics(BaseModel):
    latest_timestamp: datetime | None = None
    sample_count: int = 0
    batch_count: int = 0
    last_sequence: int | None = None
    commanded_position: float | None = None
    actual_position: float | None = None
    position_error: float | None = None
    velocity_error: float | None = None
    motor_current: float | None = None
    temperature: float | None = None
    control_latency_ms: float | None = None
    health_deviation_score: float | None = None
    rolling_mean_position_error: float | None = None
    rolling_max_position_error: float | None = None
    rolling_mean_current: float | None = None
    rolling_mean_temperature: float | None = None


class LiveSessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    actuator_id: str
    session_id: str
    controller_name: str
    controller_type: str
    transport: ControllerTransport | str
    endpoint: str | None
    status: LiveSessionStatus | str
    sample_rate_hint_hz: float | None
    min_diagnosis_samples: int
    auto_extract_features: bool
    auto_diagnose_every_n_samples: int | None
    batch_count: int
    sample_count: int
    last_sequence: int | None
    latest_metrics: dict[str, Any]
    connection_metadata: dict[str, Any]
    last_error: str | None
    started_at: datetime
    last_seen_at: datetime | None
    ended_at: datetime | None
    created_at: datetime
    updated_at: datetime


class LiveTelemetryBatchResponse(BaseModel):
    live_session: LiveSessionRead
    rows_received: int
    rows_imported: int
    rows_failed: int
    latest_metrics: LiveLatestMetrics
    rolling_features: FeatureVector | None = None
    diagnosis: DiagnosisRunResponse | None = None
    errors: list[str] = Field(default_factory=list)


class LiveDiagnosisRequest(BaseModel):
    baseline_id: str | None = None
    smoothing_window: int = Field(default=5, ge=1, le=301)
    persist: bool = True
    use_isolation_forest: bool = True


class LiveSessionListResponse(BaseModel):
    items: list[LiveSessionRead]
    total: int


class LiveRecentTelemetryResponse(BaseModel):
    live_session_id: str
    session_id: str
    samples: list[TelemetrySampleRead]
