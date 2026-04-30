from __future__ import annotations

import gc
import json
import time
from dataclasses import asdict, dataclass

from pydantic import BaseModel, Field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

try:
    import psutil  # type: ignore
except Exception:  # pragma: no cover
    psutil = None  # type: ignore

from sqlalchemy.orm import Session

from app.models.actuator import Actuator
from app.models.enums import ActuatorType, FaultLabel
from app.schemas.diagnostics import DiagnosisRunRequest
from app.schemas.imports import DuplicateSessionStrategy, ImportSourceFormat
from app.schemas.simulator import ActuatorSimulationConfig, SimulationFaultProfile
from app.services.diagnostics_engine import DiagnosticsEngine
from app.services.drift_detection import BaselineDriftDetector
from app.services.feature_store import FeatureStore
from app.services.simulator import simulator
from app.services.telemetry_importer import telemetry_importer


class BenchmarkConfig(BaseModel):
    sample_count: int = Field(default=1_000, ge=50, le=250_000)
    sample_rate_hz: float = Field(default=50.0, ge=1.0, le=1_000.0)
    healthy_trials: int = Field(default=5, ge=1, le=50)
    fault_intensity: float = Field(default=0.72, ge=0.0, le=1.0)
    use_isolation_forest: bool = True
    smoothing_window: int = Field(default=5, ge=1, le=101)
    seed: int = Field(default=20260429, ge=0, le=2_147_483_647)


@dataclass(frozen=True)
class TimedMetric:
    name: str
    elapsed_ms: float
    detail: str


@dataclass(frozen=True)
class ClassificationCaseResult:
    fault_profile: str
    expected_label: str
    predicted_label: str
    severity_score: float
    confidence_score: float
    passed: bool


@dataclass(frozen=True)
class BenchmarkResult:
    generated_at: str
    sample_count: int
    metrics: list[TimedMetric]
    memory_before_mb: float | None
    memory_after_mb: float | None
    memory_delta_mb: float | None
    classifier_accuracy: float
    healthy_false_positive_rate: float
    classification_cases: list[ClassificationCaseResult]
    diagnosis_id: str | None
    diagnosis_runtime_ms: float
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "sample_count": self.sample_count,
            "metrics": [asdict(metric) for metric in self.metrics],
            "memory_before_mb": self.memory_before_mb,
            "memory_after_mb": self.memory_after_mb,
            "memory_delta_mb": self.memory_delta_mb,
            "classifier_accuracy": self.classifier_accuracy,
            "healthy_false_positive_rate": self.healthy_false_positive_rate,
            "classification_cases": [asdict(case) for case in self.classification_cases],
            "diagnosis_id": self.diagnosis_id,
            "diagnosis_runtime_ms": self.diagnosis_runtime_ms,
            "notes": self.notes,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)


EXPECTED_LABELS: dict[SimulationFaultProfile, set[FaultLabel]] = {
    SimulationFaultProfile.HEALTHY: {FaultLabel.NONE},
    SimulationFaultProfile.FRICTION_INCREASE: {FaultLabel.FRICTION_INCREASE},
    SimulationFaultProfile.BACKLASH: {FaultLabel.BACKLASH},
    SimulationFaultProfile.ENCODER_NOISE: {FaultLabel.ENCODER_FAULT, FaultLabel.ENCODER_INCONSISTENCY},
    SimulationFaultProfile.MOTOR_WEAKENING: {FaultLabel.MOTOR_WEAKENING, FaultLabel.LOAD_ANOMALY},
    SimulationFaultProfile.OVERHEATING: {FaultLabel.THERMAL_STRESS, FaultLabel.THERMAL_RISE},
    SimulationFaultProfile.DELAYED_RESPONSE: {FaultLabel.RESPONSE_DELAY},
    SimulationFaultProfile.LOAD_IMBALANCE: {FaultLabel.LOAD_ANOMALY},
    SimulationFaultProfile.OSCILLATION_CONTROL_INSTABILITY: {FaultLabel.CONTROL_INSTABILITY, FaultLabel.OSCILLATION},
    SimulationFaultProfile.CURRENT_SPIKE_ANOMALY: {FaultLabel.CURRENT_SPIKE},
}


class ReleaseBenchmarkRunner:
    """Runs a real local benchmark through the simulator, importer, features, baseline and diagnosis layers."""

    def __init__(
        self,
        *,
        feature_store: FeatureStore | None = None,
        drift_detector: BaselineDriftDetector | None = None,
        diagnostics_engine: DiagnosticsEngine | None = None,
    ) -> None:
        self.feature_store = feature_store or FeatureStore()
        self.drift_detector = drift_detector or BaselineDriftDetector(self.feature_store)
        self.diagnostics_engine = diagnostics_engine or DiagnosticsEngine(
            feature_store=self.feature_store,
            drift_detector=self.drift_detector,
        )

    def run(self, db: Session, config: BenchmarkConfig | None = None) -> BenchmarkResult:
        cfg = config or BenchmarkConfig()
        notes: list[str] = []
        metrics: list[TimedMetric] = []
        gc.collect()
        memory_before = self._memory_mb()

        actuator = self._create_actuator(db)

        healthy_generated, elapsed = self._time(
            lambda: simulator.generate(self._simulation_config(SimulationFaultProfile.HEALTHY, cfg, cfg.seed, 0.0))
        )
        metrics.append(TimedMetric("healthy_simulation", elapsed, f"{len(healthy_generated.samples)} samples"))

        healthy_import, elapsed = self._time(
            lambda: telemetry_importer.persist_samples(
                db,
                actuator_id=actuator.id,
                session_name=self._unique_name("Benchmark healthy baseline"),
                source_format=ImportSourceFormat.SYNTHETIC,
                samples=healthy_generated.samples,
                duplicate_strategy=DuplicateSessionStrategy.CREATE_NEW,
                source_name="release_benchmark_healthy",
                source="release_benchmark",
                notes="Generated by Module 10 release benchmark.",
                tags={"release_benchmark": True, "profile": "healthy"},
                metadata={"sample_count": len(healthy_generated.samples)},
            )
        )
        metrics.append(TimedMetric("telemetry_import", elapsed, f"session={healthy_import.session_id}"))

        _, elapsed = self._time(
            lambda: self.feature_store.extract_for_session(
                db,
                session_id=healthy_import.session_id,
                smoothing_window=cfg.smoothing_window,
                persist=True,
            )
        )
        metrics.append(TimedMetric("feature_extraction", elapsed, f"session={healthy_import.session_id}"))

        baseline, elapsed = self._time(
            lambda: self.drift_detector.create_baseline_from_session(
                db,
                actuator_id=actuator.id,
                session_id=healthy_import.session_id,
                name=self._unique_name("Benchmark baseline"),
                notes="Module 10 benchmark baseline.",
                smoothing_window=cfg.smoothing_window,
                activate=True,
            )
        )
        metrics.append(TimedMetric("baseline_creation", elapsed, f"baseline={baseline.id}"))

        faulty_import = self._import_profile(
            db,
            actuator.id,
            SimulationFaultProfile.DELAYED_RESPONSE,
            cfg,
            seed=cfg.seed + 1,
            session_prefix="Benchmark delayed response",
        )

        diagnosis_response, diagnosis_elapsed = self._time(
            lambda: self.diagnostics_engine.run_diagnosis(
                db,
                session_id=faulty_import.session_id,
                payload=DiagnosisRunRequest(
                    baseline_id=baseline.id,
                    smoothing_window=cfg.smoothing_window,
                    persist=True,
                    use_isolation_forest=cfg.use_isolation_forest,
                ),
            )
        )
        metrics.append(TimedMetric("diagnosis_runtime", diagnosis_elapsed, f"diagnosis={diagnosis_response.diagnosis_id}"))

        classification_cases = self._classification_accuracy_cases(db, actuator.id, baseline.id, cfg)
        classifier_accuracy = self._accuracy(classification_cases)
        healthy_false_positive_rate = self._healthy_false_positive_rate(db, actuator.id, baseline.id, cfg)

        if classifier_accuracy < 0.50:
            notes.append("Classifier accuracy is below the suggested demo threshold. Revisit simulator intensity or classifier thresholds.")
        if healthy_false_positive_rate > 0.40:
            notes.append("Healthy false positive rate is high. Baseline may be too strict.")
        if diagnosis_elapsed > 2_500:
            notes.append("Diagnosis exceeded 2.5 seconds for this benchmark sample size.")

        gc.collect()
        memory_after = self._memory_mb()

        return BenchmarkResult(
            generated_at=datetime.now(timezone.utc).isoformat(),
            sample_count=cfg.sample_count,
            metrics=metrics,
            memory_before_mb=memory_before,
            memory_after_mb=memory_after,
            memory_delta_mb=round(memory_after - memory_before, 4) if memory_before is not None and memory_after is not None else None,
            classifier_accuracy=classifier_accuracy,
            healthy_false_positive_rate=healthy_false_positive_rate,
            classification_cases=classification_cases,
            diagnosis_id=diagnosis_response.diagnosis_id,
            diagnosis_runtime_ms=round(diagnosis_elapsed, 4),
            notes=notes,
        )

    def _classification_accuracy_cases(
        self,
        db: Session,
        actuator_id: str,
        baseline_id: str,
        cfg: BenchmarkConfig,
    ) -> list[ClassificationCaseResult]:
        cases: list[ClassificationCaseResult] = []
        profiles = [
            SimulationFaultProfile.FRICTION_INCREASE,
            SimulationFaultProfile.BACKLASH,
            SimulationFaultProfile.ENCODER_NOISE,
            SimulationFaultProfile.MOTOR_WEAKENING,
            SimulationFaultProfile.OVERHEATING,
            SimulationFaultProfile.DELAYED_RESPONSE,
            SimulationFaultProfile.LOAD_IMBALANCE,
            SimulationFaultProfile.OSCILLATION_CONTROL_INSTABILITY,
            SimulationFaultProfile.CURRENT_SPIKE_ANOMALY,
        ]

        for index, profile in enumerate(profiles, start=10):
            imported = self._import_profile(db, actuator_id, profile, cfg, seed=cfg.seed + index, session_prefix=f"Benchmark {profile.value}")
            response = self.diagnostics_engine.run_diagnosis(
                db,
                session_id=imported.session_id,
                payload=DiagnosisRunRequest(
                    baseline_id=baseline_id,
                    smoothing_window=cfg.smoothing_window,
                    persist=True,
                    use_isolation_forest=cfg.use_isolation_forest,
                ),
            )
            expected = EXPECTED_LABELS[profile]
            predicted = response.classification.fault_label
            cases.append(
                ClassificationCaseResult(
                    fault_profile=profile.value,
                    expected_label="/".join(sorted(label.value for label in expected)),
                    predicted_label=predicted.value,
                    severity_score=response.classification.severity_score,
                    confidence_score=response.classification.confidence_score,
                    passed=predicted in expected,
                )
            )
        return cases

    def _healthy_false_positive_rate(self, db: Session, actuator_id: str, baseline_id: str, cfg: BenchmarkConfig) -> float:
        false_positives = 0
        for trial in range(cfg.healthy_trials):
            imported = self._import_profile(
                db,
                actuator_id,
                SimulationFaultProfile.HEALTHY,
                cfg,
                seed=cfg.seed + 100 + trial,
                session_prefix=f"Benchmark healthy trial {trial + 1}",
                intensity=0.0,
            )
            response = self.diagnostics_engine.run_diagnosis(
                db,
                session_id=imported.session_id,
                payload=DiagnosisRunRequest(
                    baseline_id=baseline_id,
                    smoothing_window=cfg.smoothing_window,
                    persist=True,
                    use_isolation_forest=cfg.use_isolation_forest,
                ),
            )
            if response.classification.fault_label != FaultLabel.NONE or response.classification.severity_score >= 25.0:
                false_positives += 1
        return round(false_positives / max(cfg.healthy_trials, 1), 4)

    def _import_profile(
        self,
        db: Session,
        actuator_id: str,
        profile: SimulationFaultProfile,
        cfg: BenchmarkConfig,
        *,
        seed: int,
        session_prefix: str,
        intensity: float | None = None,
    ):
        generated = simulator.generate(
            self._simulation_config(profile, cfg, seed, cfg.fault_intensity if intensity is None else intensity)
        )
        return telemetry_importer.persist_samples(
            db,
            actuator_id=actuator_id,
            session_name=self._unique_name(session_prefix),
            source_format=ImportSourceFormat.SYNTHETIC,
            samples=generated.samples,
            duplicate_strategy=DuplicateSessionStrategy.CREATE_NEW,
            source_name=f"release_benchmark_{profile.value}",
            source="release_benchmark",
            notes="Generated by release readiness benchmark.",
            tags={"release_benchmark": True, "profile": profile.value},
            metadata={"sample_count": len(generated.samples)},
        )

    def _simulation_config(self, profile: SimulationFaultProfile, cfg: BenchmarkConfig, seed: int, intensity: float) -> ActuatorSimulationConfig:
        return ActuatorSimulationConfig(
            fault_profile=profile,
            seed=seed,
            sample_rate_hz=cfg.sample_rate_hz,
            duration_s=cfg.sample_count / cfg.sample_rate_hz,
            fault_intensity=intensity,
        )

    def _create_actuator(self, db: Session) -> Actuator:
        actuator = Actuator(
            name=self._unique_name("RASentinel Benchmark Servo"),
            actuator_type=ActuatorType.SERVO,
            manufacturer="RASentinel Lab",
            model_number="RS-BENCH-01",
            serial_number=f"BENCH-{uuid4().hex[:10]}",
            location="Module 10 benchmark rig",
            rated_torque_nm=12.5,
            rated_current_a=4.2,
            rated_voltage_v=24.0,
        )
        db.add(actuator)
        db.commit()
        db.refresh(actuator)
        return actuator

    def _time(self, fn):
        start = time.perf_counter()
        result = fn()
        return result, round((time.perf_counter() - start) * 1000.0, 4)

    def _memory_mb(self) -> float | None:
        if psutil is None:
            return None
        process = psutil.Process()
        return round(process.memory_info().rss / (1024 * 1024), 4)

    def _accuracy(self, cases: list[ClassificationCaseResult]) -> float:
        if not cases:
            return 0.0
        return round(sum(1 for case in cases if case.passed) / len(cases), 4)

    def _unique_name(self, prefix: str) -> str:
        return f"{prefix} {uuid4().hex[:8]}"
