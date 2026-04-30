from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMBase


class FeatureVector(BaseModel):
    sample_count: int = 0
    duration_ms: float = 0.0

    mean_position_error: float = 0.0
    max_position_error: float = 0.0
    mean_velocity_error: float = 0.0
    max_velocity_error: float = 0.0

    response_delay_ms: float = 0.0
    overshoot_percent: float = 0.0
    settling_time_ms: float = 0.0
    steady_state_error: float = 0.0

    current_drift_percent: float = 0.0
    temperature_rise_rate: float = 0.0
    error_variance: float = 0.0
    noise_level: float = 0.0
    oscillation_score: float = 0.0
    health_deviation_score: float = 0.0

    commanded_position_range: float = 0.0
    actual_position_range: float = 0.0
    mean_motor_current: float = 0.0
    max_motor_current: float = 0.0
    mean_temperature: float = 0.0
    max_temperature: float = 0.0
    mean_latency_ms: float = 0.0
    max_latency_ms: float = 0.0


class FeatureExtractionRequest(BaseModel):
    smoothing_window: int = Field(default=5, ge=1, le=301)
    persist: bool = True


class FeatureSetRead(ORMBase):
    id: str
    session_id: str
    actuator_id: str
    generated_at: datetime
    algorithm_version: str
    smoothing_window: int
    sample_count: int
    duration_ms: float

    mean_position_error: float
    max_position_error: float
    mean_velocity_error: float
    max_velocity_error: float
    response_delay_ms: float
    overshoot_percent: float
    settling_time_ms: float
    steady_state_error: float
    current_drift_percent: float
    temperature_rise_rate: float
    error_variance: float
    noise_level: float
    oscillation_score: float
    health_deviation_score: float

    feature_vector: dict
    baseline_comparison: dict


class FeatureExtractionResponse(BaseModel):
    session_id: str
    actuator_id: str
    persisted: bool
    feature_set_id: str | None
    features: FeatureVector
