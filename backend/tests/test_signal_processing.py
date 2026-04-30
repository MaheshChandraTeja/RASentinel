from datetime import datetime, timedelta, timezone

import pytest

from app.schemas.telemetry import TelemetrySampleCreate
from app.services.signal_processing import SignalProcessor


def sample_at(index: int, *, commanded: float, actual: float, current: float, temperature: float):
    timestamp = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(milliseconds=100 * index)
    return TelemetrySampleCreate(
        timestamp=timestamp,
        commanded_position=commanded,
        actual_position=actual,
        commanded_velocity=1.0,
        actual_velocity=0.9,
        motor_current=current,
        temperature=temperature,
        control_latency_ms=10.0,
        encoder_position=actual,
    )


def test_feature_extraction_calculates_expected_core_features():
    samples = [
        sample_at(0, commanded=0.0, actual=0.0, current=2.0, temperature=30.0),
        sample_at(1, commanded=1.0, actual=0.8, current=2.0, temperature=30.5),
        sample_at(2, commanded=2.0, actual=1.7, current=2.2, temperature=31.0),
        sample_at(3, commanded=3.0, actual=2.7, current=2.4, temperature=31.5),
        sample_at(4, commanded=4.0, actual=3.6, current=2.8, temperature=32.0),
    ]

    features = SignalProcessor().extract_features(samples, smoothing_window=3)

    assert features.sample_count == 5
    assert features.duration_ms == pytest.approx(400.0)
    assert features.mean_position_error == pytest.approx(0.24)
    assert features.max_position_error == pytest.approx(0.4)
    assert features.mean_velocity_error == pytest.approx(0.1)
    assert features.current_drift_percent > 0
    assert features.temperature_rise_rate == pytest.approx(5.0)
    assert features.error_variance > 0


def test_feature_extraction_handles_missing_values_safely():
    samples = [
        TelemetrySampleCreate(timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc), motor_current=2.0),
        TelemetrySampleCreate(timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=1), temperature=31.0),
    ]

    features = SignalProcessor().extract_features(samples, smoothing_window=5)

    assert features.sample_count == 2
    assert features.mean_position_error == 0
    assert features.mean_velocity_error == 0
    assert features.health_deviation_score >= 0
