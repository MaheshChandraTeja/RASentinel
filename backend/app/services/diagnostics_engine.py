from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.actuator import Actuator
from app.models.baseline import HealthyBaseline
from app.models.diagnosis import DiagnosisResult
from app.models.enums import HealthStatus, SeverityBand
from app.models.feature_set import FeatureSet
from app.models.session_run import SessionRun
from app.schemas.diagnosis import DiagnosisRead, severity_band_from_score
from app.schemas.diagnostics import (
    ActuatorHealthTimelineResponse,
    DiagnosticReportResponse,
    DiagnosisRunRequest,
    DiagnosisRunResponse,
    FaultClassificationResult,
    HealthTimelinePoint,
)
from app.schemas.features import FeatureVector
from app.services.drift_detection import BaselineDriftDetector, DriftDetectionError, DRIFT_ALGORITHM_VERSION
from app.services.fault_classifier import CLASSIFIER_VERSION, FaultClassifier
from app.services.feature_store import FeatureStore
from app.services.signal_processing import ALGORITHM_VERSION

DIAGNOSTICS_ENGINE_VERSION = "diagnostics-api-1.0.0"


class DiagnosticsError(ValueError):
    pass


class DiagnosticsEngine:
    def __init__(
        self,
        *,
        feature_store: FeatureStore | None = None,
        drift_detector: BaselineDriftDetector | None = None,
        classifier: FaultClassifier | None = None,
    ) -> None:
        self.feature_store = feature_store or FeatureStore()
        self.drift_detector = drift_detector or BaselineDriftDetector(self.feature_store)
        self.classifier = classifier or FaultClassifier()

    def run_diagnosis(
        self,
        db: Session,
        *,
        session_id: str,
        payload: DiagnosisRunRequest,
    ) -> DiagnosisRunResponse:
        session = db.get(SessionRun, session_id)
        if session is None:
            raise DiagnosticsError("Session not found")

        actuator = db.get(Actuator, session.actuator_id)
        if actuator is None:
            raise DiagnosticsError("Actuator not found")

        baseline = self._resolve_optional_baseline(
            db,
            actuator_id=session.actuator_id,
            baseline_id=payload.baseline_id,
        )

        drift_response = None
        features: FeatureVector
        feature_set_id: str | None = None
        baseline_features: dict[str, Any] | None = None
        baseline_thresholds: dict[str, Any] | None = None
        drift_score: float | None = None

        if baseline is not None:
            try:
                drift_response = self.drift_detector.analyze_session(
                    db,
                    session_id=session.id,
                    baseline_id=baseline.id,
                    smoothing_window=payload.smoothing_window,
                    persist_diagnosis=False,
                )
            except DriftDetectionError as exc:
                raise DiagnosticsError(str(exc)) from exc

            features = drift_response.features
            feature_set_id = drift_response.feature_set_id
            drift_score = drift_response.drift_score
            baseline_features = baseline.features or {}
            baseline_thresholds = baseline.thresholds or {}
        else:
            features, feature_set = self.feature_store.extract_for_session(
                db,
                session_id=session.id,
                smoothing_window=payload.smoothing_window,
                persist=True,
            )
            assert feature_set is not None
            feature_set_id = feature_set.id

        classification = self.classifier.classify(
            features=features,
            baseline_features=baseline_features,
            baseline_thresholds=baseline_thresholds,
            drift_evidence=drift_response.evidence if drift_response is not None else None,
            use_isolation_forest=payload.use_isolation_forest,
        )

        final_severity = max(classification.severity_score, drift_score or 0.0)
        final_band = severity_band_from_score(final_severity)
        final_confidence = self._final_confidence(classification, drift_score)
        summary = self._summary(classification, drift_score, final_severity)
        recommendation = self._recommendation(classification, drift_score)

        diagnosis_read: DiagnosisRead | None = None
        diagnosis_id: str | None = None

        if payload.persist:
            evidence_payload = {
                "engine_version": DIAGNOSTICS_ENGINE_VERSION,
                "classifier_version": CLASSIFIER_VERSION,
                "signal_processing_version": ALGORITHM_VERSION,
                "drift_algorithm_version": DRIFT_ALGORITHM_VERSION,
                "feature_set_id": feature_set_id,
                "baseline_id": baseline.id if baseline is not None else None,
                "classification": classification.model_dump(mode="json"),
                "drift": drift_response.model_dump(mode="json") if drift_response is not None else None,
            }

            diagnosis = DiagnosisResult(
                session_id=session.id,
                actuator_id=session.actuator_id,
                fault_label=classification.fault_label,
                severity_score=round(final_severity, 4),
                severity_band=final_band,
                confidence_score=final_confidence,
                summary=summary,
                recommendation=recommendation,
                evidence=evidence_payload,
            )
            db.add(diagnosis)
            db.flush()
            diagnosis_id = diagnosis.id
            self._update_actuator_health(actuator, final_band)
            db.add(actuator)
            db.commit()
            db.refresh(diagnosis)
            diagnosis_read = DiagnosisRead.model_validate(diagnosis)
        else:
            db.commit()

        return DiagnosisRunResponse(
            session_id=session.id,
            actuator_id=session.actuator_id,
            diagnosis_id=diagnosis_id,
            feature_set_id=feature_set_id,
            baseline_id=baseline.id if baseline is not None else None,
            drift_score=drift_score,
            diagnosis=diagnosis_read,
            classification=classification,
            features=features,
            report_url=f"/api/v1/reports/{diagnosis_id}" if diagnosis_id else None,
        )

    def get_diagnosis(self, db: Session, *, diagnosis_id: str) -> DiagnosisResult:
        diagnosis = db.get(DiagnosisResult, diagnosis_id)
        if diagnosis is None:
            raise DiagnosticsError("Diagnosis not found")
        return diagnosis

    def get_health_timeline(self, db: Session, *, actuator_id: str) -> ActuatorHealthTimelineResponse:
        actuator = db.get(Actuator, actuator_id)
        if actuator is None:
            raise DiagnosticsError("Actuator not found")

        points: list[HealthTimelinePoint] = []

        diagnosis_stmt = (
            select(DiagnosisResult)
            .where(DiagnosisResult.actuator_id == actuator_id)
            .order_by(DiagnosisResult.diagnosis_time.asc())
        )
        for diagnosis in db.scalars(diagnosis_stmt).all():
            points.append(
                HealthTimelinePoint(
                    timestamp=diagnosis.diagnosis_time,
                    session_id=diagnosis.session_id,
                    diagnosis_id=diagnosis.id,
                    severity_score=diagnosis.severity_score,
                    severity_band=diagnosis.severity_band,
                    health_status=self._health_from_band(diagnosis.severity_band),
                    fault_label=diagnosis.fault_label,
                    summary=diagnosis.summary,
                    metrics={
                        "confidence_score": diagnosis.confidence_score,
                        "recommendation": diagnosis.recommendation,
                    },
                )
            )

        if not points:
            feature_stmt = (
                select(FeatureSet)
                .where(FeatureSet.actuator_id == actuator_id)
                .order_by(FeatureSet.generated_at.asc())
                .limit(100)
            )
            for feature_set in db.scalars(feature_stmt).all():
                band = severity_band_from_score(feature_set.health_deviation_score)
                points.append(
                    HealthTimelinePoint(
                        timestamp=feature_set.generated_at,
                        session_id=feature_set.session_id,
                        feature_set_id=feature_set.id,
                        severity_score=feature_set.health_deviation_score,
                        severity_band=band,
                        health_status=self._health_from_band(band),
                        summary="Feature-only health estimate. No persisted diagnosis exists yet.",
                        metrics={
                            "mean_position_error": feature_set.mean_position_error,
                            "current_drift_percent": feature_set.current_drift_percent,
                            "temperature_rise_rate": feature_set.temperature_rise_rate,
                            "oscillation_score": feature_set.oscillation_score,
                        },
                    )
                )

        return ActuatorHealthTimelineResponse(
            actuator_id=actuator.id,
            actuator_name=actuator.name,
            current_health_status=actuator.health_status,
            points=points,
        )

    def build_report(self, db: Session, *, diagnosis_id: str) -> DiagnosticReportResponse:
        diagnosis = self.get_diagnosis(db, diagnosis_id=diagnosis_id)
        actuator = db.get(Actuator, diagnosis.actuator_id)
        session = db.get(SessionRun, diagnosis.session_id)
        if actuator is None or session is None:
            raise DiagnosticsError("Diagnosis is linked to missing actuator or session")

        evidence = diagnosis.evidence or {}
        feature_set_id = evidence.get("feature_set_id")
        baseline_id = evidence.get("baseline_id")

        feature_payload: dict[str, Any] = {}
        if feature_set_id:
            feature_set = db.get(FeatureSet, feature_set_id)
            if feature_set is not None:
                feature_payload = {
                    "id": feature_set.id,
                    "algorithm_version": feature_set.algorithm_version,
                    "generated_at": feature_set.generated_at.isoformat(),
                    "smoothing_window": feature_set.smoothing_window,
                    "sample_count": feature_set.sample_count,
                    "duration_ms": feature_set.duration_ms,
                    "feature_vector": feature_set.feature_vector,
                    "baseline_comparison": feature_set.baseline_comparison,
                }

        baseline_payload = None
        if baseline_id:
            baseline = db.get(HealthyBaseline, baseline_id)
            if baseline is not None:
                baseline_payload = {
                    "id": baseline.id,
                    "name": baseline.name,
                    "sample_count": baseline.sample_count,
                    "baseline_quality_score": baseline.baseline_quality_score,
                    "algorithm_version": baseline.algorithm_version,
                    "created_at": baseline.created_at.isoformat(),
                    "thresholds": baseline.thresholds,
                }

        return DiagnosticReportResponse(
            diagnosis_id=diagnosis.id,
            generated_at=datetime.now(timezone.utc),
            actuator={
                "id": actuator.id,
                "name": actuator.name,
                "actuator_type": actuator.actuator_type.value,
                "health_status": actuator.health_status.value,
                "location": actuator.location,
                "manufacturer": actuator.manufacturer,
                "model_number": actuator.model_number,
                "serial_number": actuator.serial_number,
            },
            session={
                "id": session.id,
                "name": session.name,
                "source": session.source,
                "sample_count": session.sample_count,
                "started_at": session.started_at.isoformat(),
                "ended_at": session.ended_at.isoformat() if session.ended_at else None,
                "tags": session.tags,
            },
            diagnosis=DiagnosisRead.model_validate(diagnosis),
            features=feature_payload,
            baseline=baseline_payload,
            classification=evidence.get("classification", {}),
            drift=evidence.get("drift"),
            maintenance_action=diagnosis.recommendation or "Review diagnostic evidence and run a follow-up actuator sweep.",
            audit={
                "engine_version": evidence.get("engine_version", DIAGNOSTICS_ENGINE_VERSION),
                "classifier_version": evidence.get("classifier_version", CLASSIFIER_VERSION),
                "signal_processing_version": evidence.get("signal_processing_version", ALGORITHM_VERSION),
                "drift_algorithm_version": evidence.get("drift_algorithm_version", DRIFT_ALGORITHM_VERSION),
                "report_type": "RASentinel actuator diagnostic report",
            },
        )

    def render_markdown_report(self, report: DiagnosticReportResponse) -> str:
        diagnosis = report.diagnosis
        classifier = report.classification or {}
        evidence_items = classifier.get("evidence", []) if isinstance(classifier, dict) else []

        lines = [
            "# RASentinel Diagnostic Report",
            "",
            f"Generated: {report.generated_at.isoformat()}",
            "",
            "## Actuator",
            f"- Name: {report.actuator.get('name')}",
            f"- Type: {report.actuator.get('actuator_type')}",
            f"- Current health: {report.actuator.get('health_status')}",
            f"- Location: {report.actuator.get('location') or 'N/A'}",
            "",
            "## Session",
            f"- Session: {report.session.get('name')}",
            f"- Samples: {report.session.get('sample_count')}",
            f"- Source: {report.session.get('source')}",
            "",
            "## Diagnosis",
            f"- Fault label: {diagnosis.fault_label.value}",
            f"- Severity: {diagnosis.severity_score:.2f}/100 ({diagnosis.severity_band.value})",
            f"- Confidence: {diagnosis.confidence_score:.2f}",
            f"- Summary: {diagnosis.summary}",
            "",
            "## Recommended maintenance action",
            report.maintenance_action,
            "",
            "## Evidence",
        ]

        if evidence_items:
            for item in evidence_items[:10]:
                signal = item.get("signal", "unknown")
                score = item.get("score", 0)
                message = item.get("message", "No message")
                lines.append(f"- {signal}: score {score}. {message}")
        else:
            lines.append("- No detailed classifier evidence was stored.")

        lines.extend([
            "",
            "## Audit",
            f"- Engine: {report.audit.get('engine_version')}",
            f"- Classifier: {report.audit.get('classifier_version')}",
            f"- Signal processing: {report.audit.get('signal_processing_version')}",
            f"- Drift detection: {report.audit.get('drift_algorithm_version')}",
        ])
        return "\n".join(lines) + "\n"

    def _resolve_optional_baseline(
        self,
        db: Session,
        *,
        actuator_id: str,
        baseline_id: str | None,
    ) -> HealthyBaseline | None:
        if baseline_id:
            baseline = db.get(HealthyBaseline, baseline_id)
            if baseline is None:
                raise DiagnosticsError("Baseline not found")
            if baseline.actuator_id != actuator_id:
                raise DiagnosticsError("Baseline does not belong to this actuator")
            return baseline

        stmt = (
            select(HealthyBaseline)
            .where(HealthyBaseline.actuator_id == actuator_id, HealthyBaseline.is_active.is_(True))
            .order_by(HealthyBaseline.created_at.desc())
            .limit(1)
        )
        return db.scalars(stmt).first()

    def _update_actuator_health(self, actuator: Actuator, severity_band: SeverityBand) -> None:
        actuator.health_status = self._health_from_band(severity_band)

    def _health_from_band(self, severity_band: SeverityBand) -> HealthStatus:
        if severity_band == SeverityBand.NONE:
            return HealthStatus.HEALTHY
        if severity_band == SeverityBand.LOW:
            return HealthStatus.WATCH
        if severity_band == SeverityBand.MEDIUM:
            return HealthStatus.DEGRADED
        return HealthStatus.CRITICAL

    def _final_confidence(self, classification: FaultClassificationResult, drift_score: float | None) -> float:
        confidence = classification.confidence_score
        if drift_score is not None:
            confidence += min(0.12, max(0.0, drift_score) / 900.0)
        return round(max(0.05, min(0.98, confidence)), 4)

    def _summary(
        self,
        classification: FaultClassificationResult,
        drift_score: float | None,
        final_severity: float,
    ) -> str:
        drift_text = f" Drift score {drift_score:.1f}/100." if drift_score is not None else " No active baseline was available, so this is classifier-only."
        return f"{classification.summary} Final severity {final_severity:.1f}/100.{drift_text}"

    def _recommendation(self, classification: FaultClassificationResult, drift_score: float | None) -> str:
        if drift_score is not None and drift_score >= 70.0:
            return f"High drift detected. {classification.recommendation} Consider removing the actuator from high-load operation until inspected."
        return classification.recommendation
