from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.actuator import Actuator
from app.models.live_telemetry import LiveTelemetrySession
from app.models.session_run import SessionRun
from app.models.telemetry import TelemetrySample
from app.schemas.diagnostics import DiagnosisRunRequest, DiagnosisRunResponse
from app.schemas.features import FeatureVector
from app.schemas.imports import DuplicateSessionStrategy
from app.schemas.live_telemetry import (
    LiveDiagnosisRequest,
    LiveLatestMetrics,
    LiveSessionListResponse,
    LiveSessionRead,
    LiveSessionStartRequest,
    LiveSessionStatus,
    LiveTelemetryBatchRequest,
    LiveTelemetryBatchResponse,
    LiveRecentTelemetryResponse,
)
from app.schemas.telemetry import TelemetrySampleRead
from app.services.diagnostics_engine import DiagnosticsEngine, DiagnosticsError
from app.services.feature_store import FeatureStore, FeatureStoreError


class LiveTelemetryError(ValueError):
    pass


class LiveTelemetryService:
    """Read-only live telemetry ingestion for actuator controllers.

    This service intentionally does not send commands to hardware. It only creates live
    capture sessions, persists incoming telemetry, computes rolling features, and can
    trigger diagnostics on the stored data.
    """

    def __init__(
        self,
        *,
        feature_store: FeatureStore | None = None,
        diagnostics_engine: DiagnosticsEngine | None = None,
    ) -> None:
        self.feature_store = feature_store or FeatureStore()
        self.diagnostics_engine = diagnostics_engine or DiagnosticsEngine()

    def start_session(self, db: Session, payload: LiveSessionStartRequest) -> LiveSessionRead:
        actuator = db.get(Actuator, payload.actuator_id)
        if actuator is None:
            raise LiveTelemetryError("Actuator not found")

        session = self._create_session(
            db,
            actuator_id=payload.actuator_id,
            session_name=payload.session_name,
            duplicate_strategy=payload.duplicate_strategy,
            source=f"live_{payload.transport.value}",
            notes=payload.notes,
            tags={
                **payload.tags,
                "live_capture": True,
                "controller_name": payload.controller_name,
                "controller_type": payload.controller_type,
                "transport": payload.transport.value,
            },
        )

        live_session = LiveTelemetrySession(
            actuator_id=payload.actuator_id,
            session_id=session.id,
            controller_name=payload.controller_name,
            controller_type=payload.controller_type,
            transport=payload.transport.value,
            endpoint=payload.endpoint,
            status=LiveSessionStatus.ACTIVE.value,
            sample_rate_hint_hz=payload.sample_rate_hint_hz,
            min_diagnosis_samples=payload.min_diagnosis_samples,
            auto_extract_features=payload.auto_extract_features,
            auto_diagnose_every_n_samples=payload.auto_diagnose_every_n_samples,
            latest_metrics={},
            connection_metadata=payload.connection_metadata,
        )
        db.add(live_session)
        db.commit()
        db.refresh(live_session)
        return LiveSessionRead.model_validate(live_session)

    def list_sessions(
        self,
        db: Session,
        *,
        actuator_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> LiveSessionListResponse:
        stmt = select(LiveTelemetrySession)
        if actuator_id:
            stmt = stmt.where(LiveTelemetrySession.actuator_id == actuator_id)
        if status:
            stmt = stmt.where(LiveTelemetrySession.status == status)
        stmt = stmt.order_by(LiveTelemetrySession.started_at.desc()).limit(limit)
        items = list(db.scalars(stmt).all())
        return LiveSessionListResponse(
            items=[LiveSessionRead.model_validate(item) for item in items],
            total=len(items),
        )

    def get_session(self, db: Session, live_session_id: str) -> LiveSessionRead:
        live_session = self._get_live_session(db, live_session_id)
        return LiveSessionRead.model_validate(live_session)

    def ingest_batch(
        self,
        db: Session,
        *,
        live_session_id: str,
        payload: LiveTelemetryBatchRequest,
    ) -> LiveTelemetryBatchResponse:
        live_session = self._get_live_session(db, live_session_id)
        if live_session.status == LiveSessionStatus.STOPPED.value:
            raise LiveTelemetryError("Live telemetry session is stopped")
        if live_session.status == LiveSessionStatus.PAUSED.value:
            raise LiveTelemetryError("Live telemetry session is paused")

        session = db.get(SessionRun, live_session.session_id)
        if session is None:
            live_session.status = LiveSessionStatus.ERROR.value
            live_session.last_error = "Linked telemetry session was not found"
            db.add(live_session)
            db.commit()
            raise LiveTelemetryError("Linked telemetry session was not found")

        now = datetime.now(timezone.utc)
        telemetry_models: list[TelemetrySample] = []
        errors: list[str] = []
        last_sequence = live_session.last_sequence

        for index, sample in enumerate(payload.samples, start=1):
            try:
                telemetry_create = sample.to_telemetry_create()
            except Exception as exc:
                errors.append(f"Sample {index}: {exc}")
                continue

            if sample.sequence_number is not None:
                if last_sequence is not None and sample.sequence_number <= last_sequence:
                    errors.append(
                        f"Sample {index}: sequence {sample.sequence_number} is not greater than previous {last_sequence}"
                    )
                last_sequence = max(last_sequence or sample.sequence_number, sample.sequence_number)

            telemetry_models.append(
                TelemetrySample(
                    session_id=session.id,
                    actuator_id=session.actuator_id,
                    **telemetry_create.model_dump(exclude_none=True),
                )
            )

        if not telemetry_models:
            raise LiveTelemetryError("No valid telemetry samples were received")

        db.add_all(telemetry_models)
        session.sample_count += len(telemetry_models)
        db.add(session)

        live_session.status = LiveSessionStatus.ACTIVE.value
        live_session.sample_count += len(telemetry_models)
        live_session.batch_count += 1
        live_session.last_sequence = last_sequence
        live_session.last_seen_at = now
        live_session.last_error = "; ".join(errors[:5]) if errors else None

        db.add(live_session)
        db.commit()
        db.refresh(live_session)

        rolling_features: FeatureVector | None = None
        feature_error: str | None = None
        if live_session.auto_extract_features:
            try:
                rolling_features, _ = self.feature_store.extract_for_session(
                    db,
                    session_id=session.id,
                    smoothing_window=payload.smoothing_window,
                    persist=False,
                )
            except Exception as exc:
                # Live ingestion must not fail just because rolling analytics failed.
                # Persist the telemetry first, then surface the analytics issue in the response/session.
                feature_error = f"Rolling feature extraction failed: {exc}"

        latest_metrics = self._build_latest_metrics(
            live_session=live_session,
            latest_sample=telemetry_models[-1],
            rolling_features=rolling_features,
        )
        live_session.latest_metrics = latest_metrics.model_dump(mode="json")
        if feature_error and not live_session.last_error:
            live_session.last_error = feature_error
        db.add(live_session)
        db.commit()
        db.refresh(live_session)

        diagnosis: DiagnosisRunResponse | None = None
        should_auto_diagnose = self._should_auto_diagnose(live_session)
        if payload.run_diagnosis or should_auto_diagnose:
            if live_session.sample_count >= live_session.min_diagnosis_samples:
                try:
                    diagnosis = self.diagnostics_engine.run_diagnosis(
                        db,
                        session_id=session.id,
                        payload=DiagnosisRunRequest(
                            baseline_id=payload.baseline_id,
                            smoothing_window=payload.smoothing_window,
                            persist=payload.persist_diagnosis,
                            use_isolation_forest=payload.use_isolation_forest,
                        ),
                    )
                except Exception as exc:
                    # A live controller stream should keep accepting telemetry even if a diagnosis pass fails.
                    errors.append(f"Live diagnosis failed: {exc}")
            else:
                errors.append(
                    f"Diagnosis requires at least {live_session.min_diagnosis_samples} samples; "
                    f"received {live_session.sample_count}."
                )

        return LiveTelemetryBatchResponse(
            live_session=LiveSessionRead.model_validate(live_session),
            rows_received=len(payload.samples),
            rows_imported=len(telemetry_models),
            rows_failed=len(payload.samples) - len(telemetry_models),
            latest_metrics=latest_metrics,
            rolling_features=rolling_features,
            diagnosis=diagnosis,
            errors=errors,
        )

    def stop_session(self, db: Session, live_session_id: str) -> LiveSessionRead:
        live_session = self._get_live_session(db, live_session_id)
        now = datetime.now(timezone.utc)
        live_session.status = LiveSessionStatus.STOPPED.value
        live_session.ended_at = now
        live_session.last_seen_at = live_session.last_seen_at or now

        session = db.get(SessionRun, live_session.session_id)
        if session is not None:
            session.ended_at = now
            db.add(session)

        db.add(live_session)
        db.commit()
        db.refresh(live_session)
        return LiveSessionRead.model_validate(live_session)

    def run_diagnosis(
        self,
        db: Session,
        *,
        live_session_id: str,
        payload: LiveDiagnosisRequest,
    ) -> DiagnosisRunResponse:
        live_session = self._get_live_session(db, live_session_id)
        if live_session.sample_count < live_session.min_diagnosis_samples:
            raise LiveTelemetryError(
                f"Diagnosis requires at least {live_session.min_diagnosis_samples} samples; "
                f"this live session has {live_session.sample_count}."
            )

        try:
            return self.diagnostics_engine.run_diagnosis(
                db,
                session_id=live_session.session_id,
                payload=DiagnosisRunRequest(
                    baseline_id=payload.baseline_id,
                    smoothing_window=payload.smoothing_window,
                    persist=payload.persist,
                    use_isolation_forest=payload.use_isolation_forest,
                ),
            )
        except DiagnosticsError as exc:
            raise LiveTelemetryError(str(exc)) from exc

    def recent_telemetry(
        self,
        db: Session,
        *,
        live_session_id: str,
        limit: int = 500,
    ) -> LiveRecentTelemetryResponse:
        live_session = self._get_live_session(db, live_session_id)
        stmt = (
            select(TelemetrySample)
            .where(TelemetrySample.session_id == live_session.session_id)
            .order_by(TelemetrySample.timestamp.desc(), TelemetrySample.id.desc())
            .limit(limit)
        )
        samples = list(reversed(list(db.scalars(stmt).all())))
        return LiveRecentTelemetryResponse(
            live_session_id=live_session.id,
            session_id=live_session.session_id,
            samples=[TelemetrySampleRead.model_validate(sample) for sample in samples],
        )

    def _get_live_session(self, db: Session, live_session_id: str) -> LiveTelemetrySession:
        live_session = db.get(LiveTelemetrySession, live_session_id)
        if live_session is None:
            raise LiveTelemetryError("Live telemetry session not found")
        return live_session

    def _create_session(
        self,
        db: Session,
        *,
        actuator_id: str,
        session_name: str,
        duplicate_strategy: DuplicateSessionStrategy,
        source: str,
        notes: str | None,
        tags: dict[str, Any],
    ) -> SessionRun:
        existing = list(
            db.scalars(
                select(SessionRun).where(
                    SessionRun.actuator_id == actuator_id,
                    SessionRun.name == session_name,
                )
            ).all()
        )

        if existing and duplicate_strategy == DuplicateSessionStrategy.REJECT:
            raise LiveTelemetryError(
                "A session with this name already exists for the actuator. Use create_new or replace."
            )

        if existing and duplicate_strategy == DuplicateSessionStrategy.REPLACE:
            for session in existing:
                db.delete(session)
            db.flush()

        final_name = session_name
        if existing and duplicate_strategy == DuplicateSessionStrategy.CREATE_NEW:
            suffix = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
            final_name = f"{session_name} ({suffix})"

        session = SessionRun(
            actuator_id=actuator_id,
            name=final_name,
            source=source,
            notes=notes,
            tags=tags,
        )
        db.add(session)
        db.flush()
        return session

    def _build_latest_metrics(
        self,
        *,
        live_session: LiveTelemetrySession,
        latest_sample: TelemetrySample,
        rolling_features: FeatureVector | None,
    ) -> LiveLatestMetrics:
        return LiveLatestMetrics(
            latest_timestamp=latest_sample.timestamp,
            sample_count=live_session.sample_count,
            batch_count=live_session.batch_count,
            last_sequence=live_session.last_sequence,
            commanded_position=latest_sample.commanded_position,
            actual_position=latest_sample.actual_position,
            position_error=latest_sample.error_position,
            velocity_error=latest_sample.error_velocity,
            motor_current=latest_sample.motor_current,
            temperature=latest_sample.temperature,
            control_latency_ms=latest_sample.control_latency_ms,
            health_deviation_score=rolling_features.health_deviation_score if rolling_features else None,
            rolling_mean_position_error=rolling_features.mean_position_error if rolling_features else None,
            rolling_max_position_error=rolling_features.max_position_error if rolling_features else None,
            rolling_mean_current=rolling_features.mean_motor_current if rolling_features else None,
            rolling_mean_temperature=rolling_features.mean_temperature if rolling_features else None,
        )

    def _should_auto_diagnose(self, live_session: LiveTelemetrySession) -> bool:
        every = live_session.auto_diagnose_every_n_samples
        if not every or every <= 0:
            return False
        if live_session.sample_count < live_session.min_diagnosis_samples:
            return False
        previous_count = max(0, live_session.sample_count - 1)
        return previous_count // every < live_session.sample_count // every


live_telemetry_service = LiveTelemetryService()
