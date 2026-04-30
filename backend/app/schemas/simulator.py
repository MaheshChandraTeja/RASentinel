from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.enums import FaultLabel
from app.schemas.common import normalize_datetime
from app.schemas.imports import DuplicateSessionStrategy, TelemetryImportResponse
from app.schemas.telemetry import TelemetrySampleCreate


class SimulationFaultProfile(StrEnum):
    HEALTHY = "healthy"
    FRICTION_INCREASE = "friction_increase"
    BACKLASH = "backlash"
    ENCODER_NOISE = "encoder_noise"
    MOTOR_WEAKENING = "motor_weakening"
    OVERHEATING = "overheating"
    DELAYED_RESPONSE = "delayed_response"
    LOAD_IMBALANCE = "load_imbalance"
    OSCILLATION_CONTROL_INSTABILITY = "oscillation_control_instability"
    CURRENT_SPIKE_ANOMALY = "current_spike_anomaly"


FAULT_PROFILE_TO_LABEL: dict[SimulationFaultProfile, FaultLabel] = {
    SimulationFaultProfile.HEALTHY: FaultLabel.NONE,
    SimulationFaultProfile.FRICTION_INCREASE: FaultLabel.FRICTION_INCREASE,
    SimulationFaultProfile.BACKLASH: FaultLabel.BACKLASH,
    SimulationFaultProfile.ENCODER_NOISE: FaultLabel.ENCODER_INCONSISTENCY,
    SimulationFaultProfile.MOTOR_WEAKENING: FaultLabel.LOAD_ANOMALY,
    SimulationFaultProfile.OVERHEATING: FaultLabel.THERMAL_RISE,
    SimulationFaultProfile.DELAYED_RESPONSE: FaultLabel.RESPONSE_DELAY,
    SimulationFaultProfile.LOAD_IMBALANCE: FaultLabel.LOAD_ANOMALY,
    SimulationFaultProfile.OSCILLATION_CONTROL_INSTABILITY: FaultLabel.OSCILLATION,
    SimulationFaultProfile.CURRENT_SPIKE_ANOMALY: FaultLabel.CURRENT_SPIKE,
}


class ActuatorSimulationConfig(BaseModel):
    fault_profile: SimulationFaultProfile = SimulationFaultProfile.HEALTHY
    seed: int | None = Field(default=42, ge=0, le=2_147_483_647)

    sample_rate_hz: float = Field(default=50.0, ge=1.0, le=1_000.0)
    duration_s: float = Field(default=20.0, ge=0.1, le=3_600.0)
    start_time: datetime = Field(default_factory=lambda: datetime(2026, 1, 1, tzinfo=timezone.utc))

    commanded_amplitude: float = Field(default=45.0, gt=0.0, le=360.0)
    command_frequency_hz: float = Field(default=0.2, gt=0.0, le=20.0)
    nominal_current_a: float = Field(default=2.2, ge=0.01, le=500.0)
    nominal_temperature_c: float = Field(default=34.0, gt=-273.15, le=250.0)
    nominal_load: float = Field(default=0.45, ge=0.0, le=5.0)
    response_time_constant_s: float = Field(default=0.08, ge=0.001, le=10.0)
    base_latency_ms: float = Field(default=12.0, ge=0.0, le=5_000.0)
    sensor_noise_std: float = Field(default=0.04, ge=0.0, le=20.0)
    current_noise_std: float = Field(default=0.03, ge=0.0, le=20.0)
    temperature_noise_std: float = Field(default=0.05, ge=0.0, le=20.0)
    fault_intensity: float = Field(default=0.65, ge=0.0, le=1.0)

    @field_validator("start_time")
    @classmethod
    def validate_start_time(cls, value: datetime) -> datetime:
        normalized = normalize_datetime(value)
        assert normalized is not None
        return normalized

    @model_validator(mode="after")
    def validate_sample_count(self) -> "ActuatorSimulationConfig":
        sample_count = int(round(self.sample_rate_hz * self.duration_s))
        if sample_count < 1:
            raise ValueError("simulation must produce at least one sample")
        if sample_count > 250_000:
            raise ValueError("simulation sample count cannot exceed 250,000")
        return self

    @property
    def sample_count(self) -> int:
        return int(round(self.sample_rate_hz * self.duration_s))


class SimulationGenerateRequest(BaseModel):
    config: ActuatorSimulationConfig = Field(default_factory=ActuatorSimulationConfig)


class SimulationMetadata(BaseModel):
    fault_profile: SimulationFaultProfile
    fault_label: FaultLabel
    seed: int | None
    sample_rate_hz: float
    duration_s: float
    sample_count: int
    generated_by: str = "RASentinel actuator telemetry simulator"


class SimulationGenerateResponse(BaseModel):
    metadata: SimulationMetadata
    samples: list[TelemetrySampleCreate]


class SimulationImportRequest(BaseModel):
    actuator_id: str = Field(min_length=1)
    session_name: str = Field(default="Synthetic actuator telemetry", min_length=1, max_length=180)
    duplicate_strategy: DuplicateSessionStrategy = DuplicateSessionStrategy.CREATE_NEW
    notes: str | None = Field(default=None, max_length=2000)
    tags: dict = Field(default_factory=dict)
    config: ActuatorSimulationConfig = Field(default_factory=ActuatorSimulationConfig)


class SimulationImportResponse(TelemetryImportResponse):
    metadata: SimulationMetadata


class SimulationFaultProfileInfo(BaseModel):
    key: SimulationFaultProfile
    label: str
    description: str
    expected_pattern: str
