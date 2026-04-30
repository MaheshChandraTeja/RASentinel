from datetime import datetime

from pydantic import Field, field_validator

from app.models.enums import FaultLabel, SeverityBand
from app.schemas.common import ORMBase, normalize_datetime


def severity_band_from_score(score: float) -> SeverityBand:
    if score <= 0:
        return SeverityBand.NONE
    if score < 25:
        return SeverityBand.LOW
    if score < 50:
        return SeverityBand.MEDIUM
    if score < 75:
        return SeverityBand.HIGH
    return SeverityBand.CRITICAL


class DiagnosisCreate(ORMBase):
    diagnosis_time: datetime | None = None

    fault_label: FaultLabel = FaultLabel.NONE
    severity_score: float = Field(default=0, ge=0, le=100)
    severity_band: SeverityBand | None = None
    confidence_score: float = Field(default=0, ge=0, le=1)

    summary: str = Field(min_length=1, max_length=1200)
    recommendation: str | None = Field(default=None, max_length=1600)
    evidence: dict = Field(default_factory=dict)

    @field_validator("diagnosis_time")
    @classmethod
    def validate_datetime(cls, value: datetime | None) -> datetime | None:
        return normalize_datetime(value)


class DiagnosisRead(ORMBase):
    id: str
    session_id: str
    actuator_id: str

    diagnosis_time: datetime
    fault_label: FaultLabel
    severity_score: float
    severity_band: SeverityBand
    confidence_score: float

    summary: str
    recommendation: str | None
    evidence: dict
    created_at: datetime