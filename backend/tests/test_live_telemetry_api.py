from __future__ import annotations


def _create_actuator(client) -> str:
    response = client.post(
        "/api/v1/actuators",
        json={"name": "Live Servo Controller", "actuator_type": "servo"},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _sample(index: int) -> dict:
    commanded = float(index) * 0.25
    actual = commanded - 0.08
    return {
        "sequence_number": index,
        "commanded_position": commanded,
        "actual_position": actual,
        "commanded_velocity": 1.5,
        "actual_velocity": 1.42,
        "motor_current": 2.1 + index * 0.001,
        "temperature": 35.0 + index * 0.002,
        "control_latency_ms": 14.0,
        "encoder_position": actual,
    }


def test_live_session_accepts_real_controller_batches(client):
    actuator_id = _create_actuator(client)

    start_response = client.post(
        "/api/v1/live/sessions",
        json={
            "actuator_id": actuator_id,
            "session_name": "Live hardware smoke test",
            "duplicate_strategy": "create_new",
            "controller_name": "Bench ESP32 controller",
            "controller_type": "esp32_pwm_encoder",
            "transport": "serial",
            "sample_rate_hint_hz": 50,
            "min_diagnosis_samples": 50,
            "connection_metadata": {"port": "COM_TEST", "baud": 115200},
        },
    )
    assert start_response.status_code == 201, start_response.text
    live_session = start_response.json()
    assert live_session["status"] == "active"
    assert live_session["sample_count"] == 0

    batch_response = client.post(
        f"/api/v1/live/sessions/{live_session['id']}/samples",
        json={"samples": [_sample(index) for index in range(1, 121)]},
    )
    assert batch_response.status_code == 200, batch_response.text
    batch = batch_response.json()
    assert batch["rows_imported"] == 120
    assert batch["latest_metrics"]["sample_count"] == 120
    assert batch["rolling_features"]["sample_count"] == 120

    status_response = client.get(f"/api/v1/live/sessions/{live_session['id']}")
    assert status_response.status_code == 200
    status_payload = status_response.json()
    assert status_payload["sample_count"] == 120
    assert status_payload["batch_count"] == 1

    recent_response = client.get(f"/api/v1/live/sessions/{live_session['id']}/telemetry/recent?limit=25")
    assert recent_response.status_code == 200
    assert len(recent_response.json()["samples"]) == 25

    diagnosis_response = client.post(f"/api/v1/live/sessions/{live_session['id']}/diagnose", json={})
    assert diagnosis_response.status_code == 201, diagnosis_response.text
    assert diagnosis_response.json()["diagnosis_id"] is not None

    stop_response = client.post(f"/api/v1/live/sessions/{live_session['id']}/stop")
    assert stop_response.status_code == 200
    assert stop_response.json()["status"] == "stopped"
