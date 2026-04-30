from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.feature_set import FeatureSet
from app.models.session_run import SessionRun
from app.models.telemetry import TelemetrySample
from app.schemas.features import FeatureVector
from app.services.signal_processing import ALGORITHM_VERSION, SignalProcessor


class FeatureStoreError(ValueError):
    pass


class FeatureStore:
    def __init__(self, processor: SignalProcessor | None = None) -> None:
        self.processor = processor or SignalProcessor()

    def extract_for_session(
        self,
        db: Session,
        *,
        session_id: str,
        smoothing_window: int = 5,
        persist: bool = True,
    ) -> tuple[FeatureVector, FeatureSet | None]:
        session = db.get(SessionRun, session_id)
        if session is None:
            raise FeatureStoreError("Session not found")

        samples = self._load_samples(db, session_id)
        if not samples:
            raise FeatureStoreError("Feature extraction requires telemetry samples")

        features = self.processor.extract_features(samples, smoothing_window=smoothing_window)
        if not persist:
            return features, None

        feature_set = self.persist_features(
            db,
            session=session,
            features=features,
            smoothing_window=smoothing_window,
        )
        return features, feature_set

    def persist_features(
        self,
        db: Session,
        *,
        session: SessionRun,
        features: FeatureVector,
        smoothing_window: int,
        baseline_comparison: dict | None = None,
    ) -> FeatureSet:
        vector = features.model_dump()
        feature_set = FeatureSet(
            session_id=session.id,
            actuator_id=session.actuator_id,
            algorithm_version=ALGORITHM_VERSION,
            smoothing_window=smoothing_window,
            sample_count=features.sample_count,
            duration_ms=features.duration_ms,
            mean_position_error=features.mean_position_error,
            max_position_error=features.max_position_error,
            mean_velocity_error=features.mean_velocity_error,
            max_velocity_error=features.max_velocity_error,
            response_delay_ms=features.response_delay_ms,
            overshoot_percent=features.overshoot_percent,
            settling_time_ms=features.settling_time_ms,
            steady_state_error=features.steady_state_error,
            current_drift_percent=features.current_drift_percent,
            temperature_rise_rate=features.temperature_rise_rate,
            error_variance=features.error_variance,
            noise_level=features.noise_level,
            oscillation_score=features.oscillation_score,
            health_deviation_score=features.health_deviation_score,
            feature_vector=vector,
            baseline_comparison=baseline_comparison or {},
        )
        db.add(feature_set)
        db.commit()
        db.refresh(feature_set)
        return feature_set

    def latest_for_session(self, db: Session, *, session_id: str) -> FeatureSet | None:
        stmt = (
            select(FeatureSet)
            .where(FeatureSet.session_id == session_id)
            .order_by(FeatureSet.generated_at.desc())
            .limit(1)
        )
        return db.scalars(stmt).first()

    def list_for_session(self, db: Session, *, session_id: str, limit: int = 25) -> list[FeatureSet]:
        stmt = (
            select(FeatureSet)
            .where(FeatureSet.session_id == session_id)
            .order_by(FeatureSet.generated_at.desc())
            .limit(limit)
        )
        return list(db.scalars(stmt).all())

    def _load_samples(self, db: Session, session_id: str) -> list[TelemetrySample]:
        stmt = (
            select(TelemetrySample)
            .where(TelemetrySample.session_id == session_id)
            .order_by(TelemetrySample.timestamp.asc(), TelemetrySample.id.asc())
        )
        return list(db.scalars(stmt).all())
