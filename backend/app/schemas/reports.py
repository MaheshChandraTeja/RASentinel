from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import FaultLabel, HealthStatus, SeverityBand
from app.schemas.diagnosis import DiagnosisRead


class EvidenceSignal(BaseModel):
    signal: str
    score: float = Field(default=0.0, ge=0.0, le=100.0)
    observed: float | None = None
    expected: float | None = None
    message: str
    recommendation: str | None = None


class DriftTimelinePoint(BaseModel):
    timestamp: datetime
    position_error: float | None = None
    velocity_error: float | None = None
    motor_current: float | None = None
    temperature: float | None = None
    latency_ms: float | None = None
    fault_label: FaultLabel | str | None = None


class ReportSection(BaseModel):
    title: str
    body: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class AuditReportResponse(BaseModel):
    diagnosis_id: str
    generated_at: datetime
    title: str
    actuator_information: dict[str, Any]
    telemetry_session_summary: dict[str, Any]
    detected_fault: dict[str, Any]
    severity_and_confidence: dict[str, Any]
    evidence_signals: list[EvidenceSignal]
    drift_timeline: list[DriftTimelinePoint]
    recommended_action: str
    technical_notes: list[str]
    diagnosis_history_count: int
    report_record_id: str | None = None
    html_url: str


class ReportRecordRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    diagnosis_id: str
    actuator_id: str
    session_id: str
    title: str
    report_format: str
    file_path: str | None
    content_hash: str
    fault_label: str
    severity_band: str
    summary: str
    generated_at: datetime


class ReportHistoryResponse(BaseModel):
    items: list[ReportRecordRead]
    total: int
    query: str | None = None


class ReportGenerationResponse(BaseModel):
    record: ReportRecordRead
    audit_report: AuditReportResponse
