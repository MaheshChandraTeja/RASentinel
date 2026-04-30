from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.enums import FaultLabel, HealthStatus, SeverityBand
from app.schemas.diagnosis import DiagnosisRead
from app.schemas.features import FeatureVector


class FaultEvidenceItem(BaseModel):
    signal: str
    score: float = Field(ge=0.0, le=100.0)
    observed: float | None = None
    expected: float | None = None
    message: str
    recommendation: str | None = None


class FaultClassificationResult(BaseModel):
    fault_label: FaultLabel
    confidence_score: float = Field(ge=0.0, le=1.0)
    severity_score: float = Field(ge=0.0, le=100.0)
    severity_band: SeverityBand
    anomaly_score: float = Field(ge=0.0, le=100.0)
    classifier_version: str
    summary: str
    recommendation: str
    evidence: list[FaultEvidenceItem]
    rule_hits: list[str] = Field(default_factory=list)
    model_used: str = "rule_based"


class DiagnosisRunRequest(BaseModel):
    baseline_id: str | None = None
    smoothing_window: int = Field(default=5, ge=1, le=301)
    persist: bool = True
    use_isolation_forest: bool = True


class DiagnosisRunResponse(BaseModel):
    session_id: str
    actuator_id: str
    diagnosis_id: str | None
    feature_set_id: str | None
    baseline_id: str | None
    drift_score: float | None
    diagnosis: DiagnosisRead | None
    classification: FaultClassificationResult
    features: FeatureVector
    report_url: str | None


class HealthTimelinePoint(BaseModel):
    timestamp: datetime
    session_id: str | None = None
    diagnosis_id: str | None = None
    feature_set_id: str | None = None
    severity_score: float = 0.0
    severity_band: SeverityBand = SeverityBand.NONE
    health_status: HealthStatus = HealthStatus.UNKNOWN
    fault_label: FaultLabel = FaultLabel.NONE
    summary: str
    metrics: dict[str, Any] = Field(default_factory=dict)


class ActuatorHealthTimelineResponse(BaseModel):
    actuator_id: str
    actuator_name: str
    current_health_status: HealthStatus
    points: list[HealthTimelinePoint]


class DiagnosticReportResponse(BaseModel):
    diagnosis_id: str
    generated_at: datetime
    actuator: dict[str, Any]
    session: dict[str, Any]
    diagnosis: DiagnosisRead
    features: dict[str, Any]
    baseline: dict[str, Any] | None
    classification: dict[str, Any]
    drift: dict[str, Any] | None
    maintenance_action: str
    audit: dict[str, Any]
