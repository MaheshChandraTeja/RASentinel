from app.models.enums import FaultLabel
from app.schemas.features import FeatureVector
from app.services.fault_classifier import FaultClassifier


def test_fault_classifier_identifies_delayed_response():
    features = FeatureVector(
        sample_count=1000,
        duration_ms=20_000,
        mean_position_error=1.2,
        max_position_error=5.5,
        mean_velocity_error=1.0,
        response_delay_ms=260.0,
        settling_time_ms=900.0,
        steady_state_error=1.1,
        current_drift_percent=8.0,
        temperature_rise_rate=0.05,
        error_variance=0.4,
        noise_level=0.08,
        oscillation_score=1.2,
        health_deviation_score=52.0,
        commanded_position_range=90.0,
        actual_position_range=84.0,
        mean_motor_current=2.3,
        max_motor_current=3.1,
        mean_temperature=36.0,
        max_temperature=39.0,
        mean_latency_ms=240.0,
        max_latency_ms=280.0,
    )

    result = FaultClassifier().classify(features=features, use_isolation_forest=False)

    assert result.fault_label == FaultLabel.RESPONSE_DELAY
    assert result.severity_score >= 50.0
    assert result.confidence_score > 0.4
    assert result.evidence


def test_fault_classifier_keeps_healthy_low_severity():
    features = FeatureVector(
        sample_count=1000,
        duration_ms=20_000,
        mean_position_error=0.04,
        max_position_error=0.18,
        mean_velocity_error=0.03,
        response_delay_ms=8.0,
        overshoot_percent=0.8,
        settling_time_ms=80.0,
        steady_state_error=0.03,
        current_drift_percent=1.0,
        temperature_rise_rate=0.01,
        error_variance=0.01,
        noise_level=0.02,
        oscillation_score=0.4,
        health_deviation_score=4.0,
        commanded_position_range=90.0,
        actual_position_range=89.5,
        mean_motor_current=2.2,
        max_motor_current=2.5,
        mean_temperature=34.0,
        max_temperature=35.0,
        mean_latency_ms=10.0,
        max_latency_ms=14.0,
    )

    result = FaultClassifier().classify(features=features, use_isolation_forest=False)

    assert result.fault_label == FaultLabel.NONE
    assert result.severity_score < 15.0
