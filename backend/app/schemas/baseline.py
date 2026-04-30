from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import SeverityBand
from app.schemas.common import ORMBase
from app.schemas.features import FeatureVector


class BaselineCreateRequest(BaseModel):
    session_id: str = Field(min_length=1)
    name: str = Field(default="Healthy actuator baseline", min_length=1, max_length=180)
    notes: str | None = Field(default=None, max_length=2000)
    smoothing_window: int = Field(default=5, ge=1, le=301)
    activate: bool = True


class BaselineRead(ORMBase):
    id: str
    actuator_id: str
    source_session_id: str
    source_feature_set_id: str | None
    name: str
    notes: str | None
    algorithm_version: str
    sample_count: int
    baseline_quality_score: float
    features: dict
    thresholds: dict
    metadata: dict = Field(default_factory=dict, validation_alias="baseline_metadata")
    is_active: bool
    created_at: datetime
    updated_at: datetime


class DriftDetectionRequest(BaseModel):
    baseline_id: str | None = None
    smoothing_window: int = Field(default=5, ge=1, le=301)
    persist_diagnosis: bool = True


class DriftEvidenceItem(BaseModel):
    signal: str
    observed: float
    baseline: float
    threshold: float
    z_score: float
    contribution: float
    message: str


class DriftDetectionResponse(BaseModel):
    session_id: str
    actuator_id: str
    baseline_id: str
    drift_score: float
    severity_band: SeverityBand
    is_drifted: bool
    feature_set_id: str | None
    diagnosis_id: str | None
    summary: str
    recommendation: str
    features: FeatureVector
    evidence: list[DriftEvidenceItem]
