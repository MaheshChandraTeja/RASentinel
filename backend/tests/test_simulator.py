def test_simulator_reproducible_seed(client):
    payload = {
        "config": {
            "fault_profile": "friction_increase",
            "seed": 123,
            "sample_rate_hz": 20,
            "duration_s": 2,
            "fault_intensity": 0.7,
        }
    }

    first = client.post("/api/v1/simulator/generate", json=payload)
    second = client.post("/api/v1/simulator/generate", json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()
    assert first.json()["metadata"]["sample_count"] == 40


def test_simulator_can_import_1000_samples(client):
    actuator_response = client.post(
        "/api/v1/actuators",
        json={"name": "Synthetic Servo", "actuator_type": "servo"},
    )
    assert actuator_response.status_code == 201
    actuator_id = actuator_response.json()["id"]

    import_response = client.post(
        "/api/v1/simulator/generate/import",
        json={
            "actuator_id": actuator_id,
            "session_name": "1000 sample synthetic delayed response",
            "duplicate_strategy": "reject",
            "config": {
                "fault_profile": "delayed_response",
                "seed": 999,
                "sample_rate_hz": 50,
                "duration_s": 20,
            },
        },
    )

    assert import_response.status_code == 201
    payload = import_response.json()
    assert payload["rows_imported"] == 1000
    assert payload["metadata"]["sample_count"] == 1000

    telemetry_response = client.get(f"/api/v1/sessions/{payload['session_id']}/telemetry?limit=1000")
    assert telemetry_response.status_code == 200
    assert len(telemetry_response.json()) == 1000
