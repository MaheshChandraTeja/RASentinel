from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Any, Iterable

from app.models.enums import FaultLabel, SeverityBand
from app.schemas.baseline import DriftEvidenceItem
from app.schemas.diagnosis import severity_band_from_score
from app.schemas.diagnostics import FaultClassificationResult, FaultEvidenceItem
from app.schemas.features import FeatureVector

CLASSIFIER_VERSION = "fault-classifier-1.0.0"

try:  # Optional dependency. The classifier works without it.
    from sklearn.ensemble import IsolationForest  # type: ignore

    SKLEARN_AVAILABLE = True
except Exception:  # pragma: no cover - depends on local environment
    IsolationForest = None  # type: ignore
    SKLEARN_AVAILABLE = False


@dataclass(frozen=True)
class RuleSignal:
    key: str
    warn: float
    bad: float
    weight: float
    message: str
    recommendation: str
    baseline_relative: bool = False
    positive_only: bool = True


@dataclass(frozen=True)
class FaultRule:
    name: str
    label: FaultLabel
    signals: tuple[RuleSignal, ...]
    summary: str
    recommendation: str


FEATURE_KEYS: tuple[str, ...] = (
    "mean_position_error",
    "max_position_error",
    "mean_velocity_error",
    "max_velocity_error",
    "response_delay_ms",
    "overshoot_percent",
    "settling_time_ms",
    "steady_state_error",
    "current_drift_percent",
    "temperature_rise_rate",
    "error_variance",
    "noise_level",
    "oscillation_score",
    "health_deviation_score",
    "commanded_position_range",
    "actual_position_range",
    "mean_motor_current",
    "max_motor_current",
    "mean_temperature",
    "max_temperature",
    "mean_latency_ms",
    "max_latency_ms",
)


class IsolationForestAnomalyScorer:
    """Small optional ML anomaly layer on top of extracted features.

    A single current feature vector is not enough to train a serious model, so when
    a healthy baseline exists we synthesize a deterministic cloud around the baseline
    using baseline thresholds. If scikit-learn is unavailable, we fall back to a
    deterministic heuristic. No mystery oracle nonsense.
    """

    def score(
        self,
        *,
        features: FeatureVector,
        baseline_features: dict[str, Any] | None,
        baseline_thresholds: dict[str, Any] | None,
        enabled: bool,
        seed: int = 42,
    ) -> tuple[float, str]:
        if not enabled:
            return self._heuristic_score(features), "heuristic_disabled_ml"

        if not SKLEARN_AVAILABLE or IsolationForest is None:
            return self._heuristic_score(features), "heuristic_no_sklearn"

        if not baseline_features or not baseline_thresholds:
            return self._heuristic_score(features), "heuristic_no_baseline"

        baseline_vector = self._vector_from_mapping(baseline_features)
        current_vector = self._vector_from_mapping(features.model_dump())
        if len(baseline_vector) != len(current_vector):
            return self._heuristic_score(features), "heuristic_vector_mismatch"

        rng = random.Random(seed)
        training: list[list[float]] = []
        for _ in range(96):
            row: list[float] = []
            for key, base in zip(FEATURE_KEYS, baseline_vector):
                threshold_payload = baseline_thresholds.get(key, {}) if isinstance(baseline_thresholds, dict) else {}
                threshold = _safe_float(threshold_payload.get("threshold"), abs(base) * 1.5 + 1.0)
                sigma = max(abs(threshold - base) / 3.5, abs(base) * 0.03, 1e-3)
                row.append(base + rng.gauss(0.0, sigma))
            training.append(row)

        try:
            model = IsolationForest(
                n_estimators=80,
                contamination=0.08,
                random_state=seed,
            )
            model.fit(training)
            decision = float(model.decision_function([current_vector])[0])
            anomaly = max(0.0, min(100.0, (0.18 - decision) * 260.0))
            return round(anomaly, 4), "isolation_forest"
        except Exception:
            return self._heuristic_score(features), "heuristic_model_error"

    def _vector_from_mapping(self, mapping: dict[str, Any]) -> list[float]:
        return [_safe_float(mapping.get(key), 0.0) for key in FEATURE_KEYS]

    def _heuristic_score(self, features: FeatureVector) -> float:
        components = [
            min(100.0, max(0.0, features.health_deviation_score)),
            min(100.0, max(0.0, features.oscillation_score) * 8.0),
            min(100.0, max(0.0, abs(features.current_drift_percent)) * 2.5),
            min(100.0, max(0.0, features.temperature_rise_rate) * 55.0),
            min(100.0, max(0.0, features.response_delay_ms) / 2.5),
            min(100.0, max(0.0, features.noise_level) * 80.0),
        ]
        return round(sum(components) / len(components), 4)


class FaultClassifier:
    def __init__(self, anomaly_scorer: IsolationForestAnomalyScorer | None = None) -> None:
        self.anomaly_scorer = anomaly_scorer or IsolationForestAnomalyScorer()
        self.rules = self._build_rules()

    def classify(
        self,
        *,
        features: FeatureVector,
        baseline_features: dict[str, Any] | None = None,
        baseline_thresholds: dict[str, Any] | None = None,
        drift_evidence: Iterable[DriftEvidenceItem] | None = None,
        use_isolation_forest: bool = True,
    ) -> FaultClassificationResult:
        feature_data = features.model_dump()
        drift_by_signal = {item.signal: item for item in (drift_evidence or [])}

        scored_rules: list[tuple[FaultRule, float, list[FaultEvidenceItem]]] = []
        for rule in self.rules:
            score, evidence = self._score_rule(
                rule,
                feature_data=feature_data,
                baseline_features=baseline_features or {},
                drift_by_signal=drift_by_signal,
            )
            scored_rules.append((rule, score, evidence))

        scored_rules.sort(key=lambda item: item[1], reverse=True)
        top_rule, top_score, top_evidence = scored_rules[0]
        second_score = scored_rules[1][1] if len(scored_rules) > 1 else 0.0

        anomaly_score, model_used = self.anomaly_scorer.score(
            features=features,
            baseline_features=baseline_features,
            baseline_thresholds=baseline_thresholds,
            enabled=use_isolation_forest,
        )

        health_score = max(0.0, min(100.0, features.health_deviation_score))
        severity_score = max(top_score, anomaly_score * 0.82, health_score)
        severity_band = severity_band_from_score(severity_score)

        if severity_score < 12.0 and top_score < 18.0:
            label = FaultLabel.NONE
            summary = "No likely actuator fault detected. Signals are within expected operating behavior."
            recommendation = "Continue normal monitoring and keep this session as a candidate healthy reference."
            evidence = []
            rule_hits: list[str] = []
            confidence = 0.72 if anomaly_score < 15.0 else 0.55
        elif top_score < 35.0 and anomaly_score >= 38.0:
            label = FaultLabel.UNKNOWN_ANOMALY
            summary = "Unknown actuator anomaly detected. Pattern is unusual but does not cleanly match a known fault family."
            recommendation = "Inspect raw telemetry, rerun the sweep, and compare against a fresh known-good baseline before replacing hardware."
            evidence = self._generic_anomaly_evidence(features, anomaly_score)
            rule_hits = ["unknown_anomaly"]
            confidence = self._confidence(top_score, second_score, anomaly_score, len(evidence), unknown=True)
        else:
            label = top_rule.label
            summary = top_rule.summary
            recommendation = top_rule.recommendation
            evidence = top_evidence[:8]
            rule_hits = [top_rule.name]
            if anomaly_score >= 45.0:
                rule_hits.append("ml_anomaly_score")
            confidence = self._confidence(top_score, second_score, anomaly_score, len(evidence), unknown=False)

        if not evidence and label != FaultLabel.NONE:
            evidence = self._generic_anomaly_evidence(features, anomaly_score)

        return FaultClassificationResult(
            fault_label=label,
            confidence_score=confidence,
            severity_score=round(max(0.0, min(100.0, severity_score)), 4),
            severity_band=severity_band,
            anomaly_score=round(max(0.0, min(100.0, anomaly_score)), 4),
            classifier_version=CLASSIFIER_VERSION,
            summary=summary,
            recommendation=recommendation,
            evidence=evidence,
            rule_hits=rule_hits,
            model_used=model_used,
        )

    def _score_rule(
        self,
        rule: FaultRule,
        *,
        feature_data: dict[str, Any],
        baseline_features: dict[str, Any],
        drift_by_signal: dict[str, DriftEvidenceItem],
    ) -> tuple[float, list[FaultEvidenceItem]]:
        weighted = 0.0
        total_weight = 0.0
        evidence: list[FaultEvidenceItem] = []

        for signal in rule.signals:
            observed = self._value_for_signal(signal.key, feature_data)
            if signal.positive_only:
                observed_for_score = max(0.0, observed)
            else:
                observed_for_score = abs(observed)

            expected = _safe_float(baseline_features.get(signal.key), 0.0) if baseline_features else None
            if signal.baseline_relative and expected is not None:
                observed_for_score = max(0.0, observed_for_score - abs(expected))

            score = _scale(observed_for_score, signal.warn, signal.bad)

            drift_item = drift_by_signal.get(signal.key)
            if drift_item is not None:
                score = max(score, min(100.0, drift_item.contribution))

            weighted += score * signal.weight
            total_weight += signal.weight

            if score >= 18.0:
                evidence.append(
                    FaultEvidenceItem(
                        signal=signal.key,
                        score=round(score, 4),
                        observed=round(observed, 6),
                        expected=round(expected, 6) if expected is not None else None,
                        message=signal.message,
                        recommendation=signal.recommendation,
                    )
                )

        final_score = weighted / max(total_weight, 1e-9)
        evidence.sort(key=lambda item: item.score, reverse=True)
        return round(max(0.0, min(100.0, final_score)), 4), evidence

    def _value_for_signal(self, key: str, feature_data: dict[str, Any]) -> float:
        if key == "range_deficit_percent":
            commanded_range = _safe_float(feature_data.get("commanded_position_range"), 0.0)
            actual_range = _safe_float(feature_data.get("actual_position_range"), 0.0)
            if commanded_range <= 1e-9:
                return 0.0
            return max(0.0, ((commanded_range - actual_range) / commanded_range) * 100.0)
        return _safe_float(feature_data.get(key), 0.0)

    def _generic_anomaly_evidence(self, features: FeatureVector, anomaly_score: float) -> list[FaultEvidenceItem]:
        candidates = [
            ("health_deviation_score", features.health_deviation_score),
            ("mean_position_error", features.mean_position_error),
            ("response_delay_ms", features.response_delay_ms),
            ("current_drift_percent", abs(features.current_drift_percent)),
            ("temperature_rise_rate", features.temperature_rise_rate),
            ("oscillation_score", features.oscillation_score),
            ("noise_level", features.noise_level),
        ]
        candidates.sort(key=lambda item: item[1], reverse=True)
        return [
            FaultEvidenceItem(
                signal="anomaly_score",
                score=round(anomaly_score, 4),
                observed=round(anomaly_score, 4),
                expected=None,
                message="Feature pattern deviates from expected actuator behavior.",
                recommendation="Review raw telemetry and compare against a known-good baseline.",
            ),
            *[
                FaultEvidenceItem(
                    signal=key,
                    score=round(min(100.0, max(0.0, value)), 4),
                    observed=round(value, 6),
                    expected=None,
                    message=f"{key} is one of the strongest anomaly contributors.",
                    recommendation="Use this signal when inspecting actuator logs and mechanical condition.",
                )
                for key, value in candidates[:3]
                if value > 0
            ],
        ][:6]

    def _confidence(
        self,
        top_score: float,
        second_score: float,
        anomaly_score: float,
        evidence_count: int,
        *,
        unknown: bool,
    ) -> float:
        separation = max(0.0, top_score - second_score)
        base = 0.30 + min(0.28, top_score / 260.0) + min(0.18, separation / 220.0)
        base += min(0.18, evidence_count * 0.035)
        base += min(0.12, anomaly_score / 600.0)
        if unknown:
            base -= 0.10
        return round(max(0.05, min(0.96, base)), 4)

    def _build_rules(self) -> tuple[FaultRule, ...]:
        return (
            FaultRule(
                name="friction_increase",
                label=FaultLabel.FRICTION_INCREASE,
                signals=(
                    RuleSignal("current_drift_percent", 8.0, 38.0, 1.2, "Current draw increased beyond expected tracking demand.", "Inspect lubrication, bearings, drivetrain drag, and payload friction."),
                    RuleSignal("response_delay_ms", 35.0, 180.0, 0.8, "Response delay increased, consistent with mechanical resistance.", "Run a controlled low-load sweep to isolate friction from control latency."),
                    RuleSignal("mean_position_error", 0.35, 4.0, 0.7, "Mean position error increased under command tracking.", "Check actuator alignment and mechanical binding."),
                    RuleSignal("temperature_rise_rate", 0.08, 0.65, 0.6, "Temperature trend increased during operation.", "Inspect thermal path and duty cycle."),
                ),
                summary="Likely friction increase detected. The actuator appears to require more effort to track the same motion.",
                recommendation="Inspect lubrication, bearings, linkage drag, gearbox condition, and recent payload changes before continued high-load operation.",
            ),
            FaultRule(
                name="backlash",
                label=FaultLabel.BACKLASH,
                signals=(
                    RuleSignal("steady_state_error", 0.30, 3.0, 1.0, "Persistent steady-state error suggests looseness or lost motion.", "Inspect gearbox play, coupling looseness, belt tension, and joint fasteners."),
                    RuleSignal("overshoot_percent", 3.0, 24.0, 0.9, "Overshoot increased around command transitions.", "Check mechanical play and retune compensation only after hardware inspection."),
                    RuleSignal("error_variance", 0.12, 3.5, 0.8, "Error variance is elevated, consistent with inconsistent catch-up motion.", "Review reversal segments in the telemetry trace."),
                    RuleSignal("max_position_error", 1.0, 9.0, 0.6, "Peak position error is elevated.", "Inspect backlash near direction reversals."),
                ),
                summary="Likely backlash or mechanical looseness detected.",
                recommendation="Inspect drivetrain play, gear mesh, couplers, belts, pulleys, and joint fasteners. Recalibrate only after mechanical looseness is ruled out.",
            ),
            FaultRule(
                name="encoder_fault",
                label=FaultLabel.ENCODER_FAULT,
                signals=(
                    RuleSignal("noise_level", 0.12, 1.2, 1.3, "Signal noise increased, consistent with encoder or sensor inconsistency.", "Inspect encoder wiring, shielding, connector seating, and grounding."),
                    RuleSignal("error_variance", 0.10, 2.4, 0.9, "Position error variance is elevated.", "Compare encoder readings against an external reference if available."),
                    RuleSignal("max_position_error", 0.9, 8.0, 0.45, "Peak position mismatch increased.", "Check encoder calibration and dropped counts."),
                ),
                summary="Likely encoder or feedback sensor fault detected.",
                recommendation="Inspect encoder wiring, connector integrity, shielding, grounding, calibration, and possible intermittent feedback loss.",
            ),
            FaultRule(
                name="motor_weakening",
                label=FaultLabel.MOTOR_WEAKENING,
                signals=(
                    RuleSignal("mean_velocity_error", 0.40, 5.0, 1.1, "Velocity tracking weakened under commanded motion.", "Check motor driver output, supply voltage sag, winding condition, and torque margin."),
                    RuleSignal("range_deficit_percent", 8.0, 35.0, 0.9, "Actual movement range is reduced versus the commanded range.", "Compare commanded and actual travel range under low and high load."),
                    RuleSignal("current_drift_percent", 10.0, 42.0, 0.75, "Current draw increased while tracking quality worsened.", "Inspect motor, driver, and power supply health."),
                    RuleSignal("settling_time_ms", 180.0, 900.0, 0.65, "Settling time increased, suggesting reduced actuation authority.", "Perform torque/load characterization."),
                ),
                summary="Likely motor weakening or loss of actuation authority detected.",
                recommendation="Inspect motor windings, driver output, supply voltage, torque margin, and load-side resistance. Avoid high-load duty until verified.",
            ),
            FaultRule(
                name="thermal_stress",
                label=FaultLabel.THERMAL_STRESS,
                signals=(
                    RuleSignal("temperature_rise_rate", 0.10, 0.80, 1.4, "Temperature is rising faster than expected.", "Inspect cooling, duty cycle, ambient temperature, and friction sources."),
                    RuleSignal("max_temperature", 45.0, 85.0, 1.0, "Peak temperature is elevated.", "Verify thermal limits before continued operation."),
                    RuleSignal("current_drift_percent", 10.0, 38.0, 0.65, "Current drift may be contributing to heat buildup.", "Check current draw under equivalent command profiles."),
                ),
                summary="Likely thermal stress detected.",
                recommendation="Reduce duty cycle, inspect cooling path, check current draw, and verify whether friction or load changes are causing heat buildup.",
            ),
            FaultRule(
                name="control_instability",
                label=FaultLabel.CONTROL_INSTABILITY,
                signals=(
                    RuleSignal("oscillation_score", 4.0, 16.0, 1.35, "Oscillation score is elevated.", "Review PID gains, control loop timing, and mechanical resonance."),
                    RuleSignal("overshoot_percent", 4.0, 30.0, 1.0, "Overshoot suggests poor damping or unstable control response.", "Reduce aggressive gains and inspect mounting rigidity."),
                    RuleSignal("error_variance", 0.18, 4.0, 0.55, "Error variance is high during tracking.", "Inspect loop stability and noisy feedback."),
                ),
                summary="Likely control instability or oscillation detected.",
                recommendation="Check PID gains, loop timing, actuator saturation, feedback latency, resonance, and mounting rigidity before production use.",
            ),
            FaultRule(
                name="delayed_response",
                label=FaultLabel.RESPONSE_DELAY,
                signals=(
                    RuleSignal("response_delay_ms", 30.0, 220.0, 1.5, "Response delay is elevated against command timing.", "Inspect controller scheduling, communication delay, and actuator response time."),
                    RuleSignal("settling_time_ms", 150.0, 850.0, 0.75, "Settling time increased after command changes.", "Run a step/sweep response test and verify control-loop latency."),
                    RuleSignal("mean_latency_ms", 20.0, 180.0, 0.8, "Telemetry latency is elevated.", "Inspect bus timing and command path jitter."),
                    RuleSignal("steady_state_error", 0.25, 3.0, 0.45, "Persistent lag leaves residual tracking error.", "Review command tracking and controller timing."),
                ),
                summary="Likely delayed actuator response detected.",
                recommendation="Inspect command bus latency, controller scheduling, response-time constants, friction, and driver saturation. Run a controlled step response test.",
            ),
            FaultRule(
                name="load_imbalance",
                label=FaultLabel.LOAD_ANOMALY,
                signals=(
                    RuleSignal("current_drift_percent", 8.0, 36.0, 1.0, "Current draw changed in a way consistent with load variation.", "Inspect payload balance, external load, and mechanism alignment."),
                    RuleSignal("mean_velocity_error", 0.35, 4.2, 0.75, "Velocity tracking changed under load.", "Run a no-load comparison sweep."),
                    RuleSignal("error_variance", 0.12, 3.2, 0.70, "Error variance suggests changing mechanical demand.", "Check asymmetric loading across the movement cycle."),
                    RuleSignal("mean_position_error", 0.35, 4.5, 0.55, "Position tracking error increased.", "Inspect payload and fixture alignment."),
                ),
                summary="Likely load imbalance or external load anomaly detected.",
                recommendation="Inspect payload distribution, arm fixture alignment, binding under load, and recent changes to tooling or carried mass.",
            ),
            FaultRule(
                name="current_spike_anomaly",
                label=FaultLabel.CURRENT_SPIKE,
                signals=(
                    RuleSignal("max_motor_current", 4.0, 14.0, 1.25, "Peak motor current is elevated.", "Inspect driver, wiring, short spikes, and abrupt load changes."),
                    RuleSignal("current_drift_percent", 15.0, 55.0, 1.0, "Current drift indicates abnormal electrical or mechanical demand.", "Compare current against command and load traces."),
                    RuleSignal("temperature_rise_rate", 0.08, 0.55, 0.45, "Thermal rise may follow repeated current spikes.", "Check whether spikes correlate with heat buildup."),
                ),
                summary="Likely current spike anomaly detected.",
                recommendation="Inspect motor driver, wiring, power supply stability, sudden load changes, and command segments that correlate with current spikes.",
            ),
        )


def _scale(value: float, warn: float, bad: float) -> float:
    if not math.isfinite(value):
        return 0.0
    if value <= warn:
        return 0.0
    if bad <= warn:
        return 100.0 if value > warn else 0.0
    return max(0.0, min(100.0, ((value - warn) / (bad - warn)) * 100.0))


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(number):
        return default
    return number
