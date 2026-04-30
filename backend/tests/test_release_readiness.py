from app.models.enums import FaultLabel
from app.schemas.imports import DuplicateSessionStrategy
from app.schemas.simulator import ActuatorSimulationConfig, SimulationFaultProfile
from app.services.release_benchmark import BenchmarkConfig, ReleaseBenchmarkRunner
from app.services.simulator import simulator


def test_simulator_produces_reproducible_1000_sample_dataset():
    config = ActuatorSimulationConfig(
        fault_profile=SimulationFaultProfile.FRICTION_INCREASE,
        seed=911,
        sample_rate_hz=50,
        duration_s=20,
        fault_intensity=0.70,
    )

    first = simulator.generate(config)
    second = simulator.generate(config)

    assert first.metadata.sample_count == 1000
    assert len(first.samples) == 1000
    assert [sample.model_dump(mode="json") for sample in first.samples[:25]] == [
        sample.model_dump(mode="json") for sample in second.samples[:25]
    ]
    assert any(sample.fault_label == FaultLabel.FRICTION_INCREASE for sample in first.samples)


def test_full_simulator_to_diagnosis_flow_through_api(client):
    actuator_response = client.post(
        "/api/v1/actuators",
        json={
            "name": "Module 10 Release Test Servo",
            "actuator_type": "servo",
            "location": "release-readiness-test-rig",
        },
    )
    assert actuator_response.status_code == 201
    actuator_id = actuator_response.json()["id"]

    healthy_response = client.post(
        "/api/v1/telemetry/simulate",
        json={
            "actuator_id": actuator_id,
            "session_name": "Healthy release baseline",
            "duplicate_strategy": DuplicateSessionStrategy.CREATE_NEW.value,
            "config": {
                "fault_profile": "healthy",
                "seed": 501,
                "sample_rate_hz": 50,
                "duration_s": 20,
                "fault_intensity": 0,
            },
        },
    )
    assert healthy_response.status_code == 200
    healthy_session_id = healthy_response.json()["session_id"]
    assert healthy_response.json()["rows_imported"] == 1000

    baseline_response = client.post(
        f"/api/v1/actuators/{actuator_id}/baselines/from-session",
        json={
            "session_id": healthy_session_id,
            "name": "Release healthy baseline",
            "smoothing_window": 5,
            "activate": True,
        },
    )
    assert baseline_response.status_code == 201
    baseline_id = baseline_response.json()["id"]

    faulty_response = client.post(
        "/api/v1/telemetry/simulate",
        json={
            "actuator_id": actuator_id,
            "session_name": "Delayed response release fault",
            "duplicate_strategy": DuplicateSessionStrategy.CREATE_NEW.value,
            "config": {
                "fault_profile": "delayed_response",
                "seed": 502,
                "sample_rate_hz": 50,
                "duration_s": 20,
                "fault_intensity": 0.85,
            },
        },
    )
    assert faulty_response.status_code == 200
    faulty_session_id = faulty_response.json()["session_id"]

    diagnosis_response = client.post(
        f"/api/v1/diagnostics/run/{faulty_session_id}",
        json={
            "baseline_id": baseline_id,
            "smoothing_window": 5,
            "persist": True,
            "use_isolation_forest": True,
        },
    )
    assert diagnosis_response.status_code == 201
    diagnosis_payload = diagnosis_response.json()
    assert diagnosis_payload["diagnosis_id"]
    assert diagnosis_payload["classification"]["confidence_score"] > 0
    assert diagnosis_payload["classification"]["evidence"]
    assert diagnosis_payload["classification"]["fault_label"] in {
        "response_delay",
        "friction_increase",
        "unknown_anomaly",
    }

    report_response = client.post(f"/api/v1/reports/{diagnosis_payload['diagnosis_id']}/audit")
    assert report_response.status_code == 200
    report_payload = report_response.json()
    assert report_payload["audit_report"]["diagnosis_id"] == diagnosis_payload["diagnosis_id"]
    assert report_payload["record"]["file_path"]


def test_release_benchmark_runner_returns_core_metrics(db_session):
    runner = ReleaseBenchmarkRunner()
    result = runner.run(
        db_session,
        BenchmarkConfig(
            sample_count=220,
            sample_rate_hz=50,
            healthy_trials=2,
            fault_intensity=0.78,
            use_isolation_forest=False,
            seed=1234,
        ),
    )

    payload = result.to_dict()
    metric_names = {item["name"] for item in payload["metrics"]}

    assert "telemetry_import" in metric_names
    assert "feature_extraction" in metric_names
    assert "diagnosis_runtime" in metric_names
    assert payload["diagnosis_id"]
    assert 0 <= payload["classifier_accuracy"] <= 1
    assert 0 <= payload["healthy_false_positive_rate"] <= 1
    assert payload["classification_cases"]
