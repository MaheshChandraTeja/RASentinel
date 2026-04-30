from __future__ import annotations

import math
from dataclasses import dataclass

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.actuator import Actuator
from app.models.baseline import HealthyBaseline
from app.models.diagnosis import DiagnosisResult
from app.models.enums import FaultLabel, HealthStatus, SeverityBand
from app.models.feature_set import FeatureSet
from app.models.session_run import SessionRun
from app.schemas.baseline import DriftDetectionResponse, DriftEvidenceItem
from app.schemas.diagnosis import severity_band_from_score
from app.schemas.features import FeatureVector
from app.services.feature_store import FeatureStore
from app.services.signal_processing import ALGORITHM_VERSION

DRIFT_ALGORITHM_VERSION = "drift-1.0.0"


@dataclass(frozen=True)
class MetricSpec:
    key: str
    label: str
    weight: float
    floor: float
    multiplier: float
    margin: float
    absolute: bool = False
    positive_only: bool = False


METRIC_SPECS: tuple[MetricSpec, ...] = (
    MetricSpec("mean_position_error", "Mean position error", 18.0, 0.10, 2.5, 0.08),
    MetricSpec("max_position_error", "Max position error", 10.0, 0.40, 2.5, 0.15),
    MetricSpec("mean_velocity_error", "Mean velocity error", 10.0, 0.15, 2.5, 0.08),
    MetricSpec("response_delay_ms", "Response delay", 14.0, 12.0, 2.0, 8.0),
    MetricSpec("overshoot_percent", "Overshoot", 9.0, 2.0, 2.5, 1.0),
    MetricSpec("settling_time_ms", "Settling time", 6.0, 100.0, 1.8, 50.0),
    MetricSpec("steady_state_error", "Steady-state error", 10.0, 0.10, 2.5, 0.05),
    MetricSpec("current_drift_percent", "Current drift", 8.0, 6.0, 2.2, 4.0, absolute=True),
    MetricSpec("temperature_rise_rate", "Temperature rise rate", 7.0, 0.08, 2.0, 0.04, positive_only=True),
    MetricSpec("error_variance", "Error variance", 4.0, 0.05, 2.5, 0.02),
    MetricSpec("noise_level", "Noise level", 4.0, 0.04, 2.8, 0.03),
    MetricSpec("oscillation_score", "Oscillation score", 10.0, 4.0, 2.0, 2.5),
)


class DriftDetectionError(ValueError):
    pass


class BaselineDriftDetector:
    def __init__(self, feature_store: FeatureStore | None = None) -> None:
        self.feature_store = feature_store or FeatureStore()

    def create_baseline_from_session(
        self,
        db: Session,
        *,
        actuator_id: str,
        session_id: str,
        name: str,
        notes: str | None,
        smoothing_window: int,
        activate: bool,
    ) -> HealthyBaseline:
        actuator = db.get(Actuator, actuator_id)
        if actuator is None:
            raise DriftDetectionError("Actuator not found")

        session = db.get(SessionRun, session_id)
        if session is None:
            raise DriftDetectionError("Session not found")
        if session.actuator_id != actuator_id:
            raise DriftDetectionError("Session does not belong to this actuator")

        features, feature_set = self.feature_store.extract_for_session(
            db,
            session_id=session_id,
            smoothing_window=smoothing_window,
            persist=True,
        )
        assert feature_set is not None

        thresholds = self._build_thresholds(features)
        quality_score = self._baseline_quality_score(features)

        if activate:
            db.execute(
                update(HealthyBaseline)
                .where(HealthyBaseline.actuator_id == actuator_id)
                .values(is_active=False)
            )

        baseline = HealthyBaseline(
            actuator_id=actuator_id,
            source_session_id=session_id,
            source_feature_set_id=feature_set.id,
            name=name,
            notes=notes,
            algorithm_version=DRIFT_ALGORITHM_VERSION,
            sample_count=features.sample_count,
            baseline_quality_score=quality_score,
            features=features.model_dump(),
            thresholds=thresholds,
            baseline_metadata={
                "smoothing_window": smoothing_window,
                "signal_algorithm_version": ALGORITHM_VERSION,
                "warning": "Baselines should be created from known-good actuator sessions.",
            },
            is_active=activate,
        )
        db.add(baseline)
        db.commit()
        db.refresh(baseline)
        return baseline

    def analyze_session(
        self,
        db: Session,
        *,
        session_id: str,
        baseline_id: str | None,
        smoothing_window: int,
        persist_diagnosis: bool,
    ) -> DriftDetectionResponse:
        session = db.get(SessionRun, session_id)
        if session is None:
            raise DriftDetectionError("Session not found")

        baseline = self._resolve_baseline(db, actuator_id=session.actuator_id, baseline_id=baseline_id)
        features, feature_set = self.feature_store.extract_for_session(
            db,
            session_id=session_id,
            smoothing_window=smoothing_window,
            persist=True,
        )
        assert feature_set is not None

        score, evidence = self._score_against_baseline(features, baseline)
        severity_band = severity_band_from_score(score)
        is_drifted = score >= 25.0
        summary = self._summary(score, severity_band, evidence)
        recommendation = self._recommendation(score, evidence)
        diagnosis_id: str | None = None

        comparison_payload = {
            "baseline_id": baseline.id,
            "drift_score": score,
            "severity_band": severity_band.value,
            "evidence": [item.model_dump() for item in evidence],
        }
        feature_set.baseline_comparison = comparison_payload
        db.add(feature_set)

        if persist_diagnosis:
            diagnosis = DiagnosisResult(
                session_id=session.id,
                actuator_id=session.actuator_id,
                fault_label=self._probable_fault_label(evidence),
                severity_score=score,
                severity_band=severity_band,
                confidence_score=self._confidence_score(score, evidence),
                summary=summary,
                recommendation=recommendation,
                evidence=comparison_payload,
            )
            db.add(diagnosis)
            db.flush()
            diagnosis_id = diagnosis.id
            self._update_actuator_health(db, session.actuator_id, severity_band)

        db.commit()
        return DriftDetectionResponse(
            session_id=session.id,
            actuator_id=session.actuator_id,
            baseline_id=baseline.id,
            drift_score=round(score, 4),
            severity_band=severity_band,
            is_drifted=is_drifted,
            feature_set_id=feature_set.id,
            diagnosis_id=diagnosis_id,
            summary=summary,
            recommendation=recommendation,
            features=features,
            evidence=evidence,
        )

    def _resolve_baseline(self, db: Session, *, actuator_id: str, baseline_id: str | None) -> HealthyBaseline:
        if baseline_id:
            baseline = db.get(HealthyBaseline, baseline_id)
            if baseline is None:
                raise DriftDetectionError("Baseline not found")
            if baseline.actuator_id != actuator_id:
                raise DriftDetectionError("Baseline does not belong to this actuator")
            return baseline

        stmt = (
            select(HealthyBaseline)
            .where(HealthyBaseline.actuator_id == actuator_id, HealthyBaseline.is_active.is_(True))
            .order_by(HealthyBaseline.created_at.desc())
            .limit(1)
        )
        baseline = db.scalars(stmt).first()
        if baseline is None:
            raise DriftDetectionError("No active baseline found for this actuator")
        return baseline

    def _build_thresholds(self, features: FeatureVector) -> dict[str, dict[str, float]]:
        data = features.model_dump()
        thresholds: dict[str, dict[str, float]] = {}
        for spec in METRIC_SPECS:
            baseline = self._metric_value(data.get(spec.key, 0.0), spec)
            threshold = max(spec.floor, baseline * spec.multiplier + spec.margin)
            thresholds[spec.key] = {
                "baseline": baseline,
                "threshold": threshold,
                "weight": spec.weight,
                "floor": spec.floor,
                "multiplier": spec.multiplier,
                "margin": spec.margin,
            }
        return thresholds

    def _score_against_baseline(
        self,
        features: FeatureVector,
        baseline: HealthyBaseline,
    ) -> tuple[float, list[DriftEvidenceItem]]:
        observed = features.model_dump()
        baseline_features = baseline.features or {}
        thresholds = baseline.thresholds or self._build_thresholds(FeatureVector(**baseline_features))

        total_weight = sum(spec.weight for spec in METRIC_SPECS)
        weighted_score = 0.0
        evidence: list[DriftEvidenceItem] = []

        for spec in METRIC_SPECS:
            raw_observed = observed.get(spec.key, 0.0)
            raw_baseline = baseline_features.get(spec.key, 0.0)
            threshold_payload = thresholds.get(spec.key, {})

            observed_value = self._metric_value(raw_observed, spec)
            baseline_value = self._metric_value(raw_baseline, spec)
            threshold = float(threshold_payload.get("threshold", max(spec.floor, baseline_value * spec.multiplier + spec.margin)))
            excess = max(0.0, observed_value - threshold)
            z_score = excess / max(threshold, 1e-9)
            contribution = min(100.0, z_score * 100.0)
            weighted_score += contribution * spec.weight

            if contribution > 0.0:
                evidence.append(
                    DriftEvidenceItem(
                        signal=spec.key,
                        observed=round(observed_value, 6),
                        baseline=round(baseline_value, 6),
                        threshold=round(threshold, 6),
                        z_score=round(z_score, 6),
                        contribution=round(contribution, 6),
                        message=f"{spec.label} exceeded baseline threshold.",
                    )
                )

        score = weighted_score / max(total_weight, 1e-9)
        evidence.sort(key=lambda item: item.contribution, reverse=True)
        return min(100.0, max(0.0, score)), evidence[:8]

    def _metric_value(self, value: object, spec: MetricSpec) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return 0.0
        if not math.isfinite(number):
            return 0.0
        if spec.absolute:
            return abs(number)
        if spec.positive_only:
            return max(0.0, number)
        return max(0.0, number)

    def _baseline_quality_score(self, features: FeatureVector) -> float:
        penalties = 0.0
        penalties += min(30.0, features.health_deviation_score * 0.5)
        penalties += 15.0 if features.sample_count < 100 else 0.0
        penalties += min(20.0, max(0.0, features.current_drift_percent) * 0.5)
        penalties += min(20.0, max(0.0, features.temperature_rise_rate) * 12.0)
        return max(0.0, min(100.0, 100.0 - penalties))

    def _summary(self, score: float, severity_band: SeverityBand, evidence: list[DriftEvidenceItem]) -> str:
        if not evidence:
            return f"No meaningful actuator drift detected. Drift score {score:.1f}/100."
        top = ", ".join(item.signal for item in evidence[:3])
        return f"{severity_band.value.title()} actuator drift detected. Drift score {score:.1f}/100. Main contributors: {top}."

    def _recommendation(self, score: float, evidence: list[DriftEvidenceItem]) -> str:
        signals = {item.signal for item in evidence[:5]}
        if score < 25:
            return "Continue normal monitoring. Re-run baseline checks after the next maintenance cycle."
        if {"current_drift_percent", "temperature_rise_rate"} & signals:
            return "Inspect mechanical load, lubrication, motor current draw, thermal path, and recent duty-cycle changes."
        if {"response_delay_ms", "settling_time_ms", "steady_state_error"} & signals:
            return "Run a controlled sweep test and inspect control-loop tuning, drivetrain friction, and actuator command latency."
        if {"overshoot_percent", "oscillation_score"} & signals:
            return "Check PID gains, backlash, mounting rigidity, and feedback-loop stability before returning actuator to high-load operation."
        return "Review the top drift evidence and compare against recent maintenance or payload changes."

    def _confidence_score(self, score: float, evidence: list[DriftEvidenceItem]) -> float:
        evidence_factor = min(0.35, len(evidence) * 0.06)
        score_factor = min(0.55, score / 140.0)
        return round(min(0.95, 0.25 + evidence_factor + score_factor), 4)

    def _probable_fault_label(self, evidence: list[DriftEvidenceItem]) -> FaultLabel:
        signals = [item.signal for item in evidence[:4]]
        if "temperature_rise_rate" in signals:
            return FaultLabel.THERMAL_RISE
        if "current_drift_percent" in signals:
            return FaultLabel.CURRENT_SPIKE
        if "response_delay_ms" in signals or "settling_time_ms" in signals:
            return FaultLabel.RESPONSE_DELAY
        if "overshoot_percent" in signals:
            return FaultLabel.OVERSHOOT
        if "oscillation_score" in signals:
            return FaultLabel.OSCILLATION
        if "noise_level" in signals:
            return FaultLabel.ENCODER_INCONSISTENCY
        if signals:
            return FaultLabel.UNKNOWN
        return FaultLabel.NONE

    def _update_actuator_health(self, db: Session, actuator_id: str, severity_band: SeverityBand) -> None:
        actuator = db.get(Actuator, actuator_id)
        if actuator is None:
            return
        if severity_band in {SeverityBand.NONE, SeverityBand.LOW}:
            actuator.health_status = HealthStatus.HEALTHY if severity_band == SeverityBand.NONE else HealthStatus.WATCH
        elif severity_band == SeverityBand.MEDIUM:
            actuator.health_status = HealthStatus.DEGRADED
        else:
            actuator.health_status = HealthStatus.CRITICAL
        db.add(actuator)
