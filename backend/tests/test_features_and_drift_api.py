def create_actuator(client):
    response = client.post(
        "/api/v1/actuators",
        json={
            "name": "RAS Test Servo",
            "actuator_type": "servo",
            "location": "test-rig",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def import_synthetic(client, actuator_id: str, profile: str, session_name: str, intensity: float = 0.65):
    response = client.post(
        "/api/v1/simulator/generate/import",
        json={
            "actuator_id": actuator_id,
            "session_name": session_name,
            "duplicate_strategy": "create_new",
            "config": {
                "fault_profile": profile,
                "seed": 123,
                "sample_rate_hz": 50,
                "duration_s": 20,
                "fault_intensity": intensity,
                "sensor_noise_std": 0.02,
                "current_noise_std": 0.01,
                "temperature_noise_std": 0.01,
            },
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_feature_extraction_endpoint_persists_feature_set(client):
    actuator = create_actuator(client)
    imported = import_synthetic(client, actuator["id"], "healthy", "healthy-baseline")

    response = client.post(
        f"/api/v1/sessions/{imported['session_id']}/features/extract",
        json={"smoothing_window": 5, "persist": True},
    )

    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["persisted"] is True
    assert payload["feature_set_id"]
    assert payload["features"]["sample_count"] == 1000
    assert payload["features"]["mean_position_error"] >= 0

    latest = client.get(f"/api/v1/sessions/{imported['session_id']}/features/latest")
    assert latest.status_code == 200
    assert latest.json()["id"] == payload["feature_set_id"]


def test_baseline_and_drift_detection_separates_healthy_from_faulty(client):
    actuator = create_actuator(client)
    healthy = import_synthetic(client, actuator["id"], "healthy", "known-good")
    faulty = import_synthetic(client, actuator["id"], "delayed_response", "faulty-delay", intensity=0.9)

    baseline_response = client.post(
        f"/api/v1/actuators/{actuator['id']}/baselines/from-session",
        json={
            "session_id": healthy["session_id"],
            "name": "Known good baseline",
            "smoothing_window": 5,
            "activate": True,
        },
    )
    assert baseline_response.status_code == 201, baseline_response.text
    baseline = baseline_response.json()
    assert baseline["is_active"] is True
    assert baseline["sample_count"] == 1000

    healthy_analysis = client.post(
        f"/api/v1/sessions/{healthy['session_id']}/drift/analyze",
        json={"baseline_id": baseline["id"], "persist_diagnosis": False},
    )
    assert healthy_analysis.status_code == 200, healthy_analysis.text

    faulty_analysis = client.post(
        f"/api/v1/sessions/{faulty['session_id']}/drift/analyze",
        json={"baseline_id": baseline["id"], "persist_diagnosis": True},
    )
    assert faulty_analysis.status_code == 200, faulty_analysis.text

    healthy_score = healthy_analysis.json()["drift_score"]
    faulty_payload = faulty_analysis.json()
    faulty_score = faulty_payload["drift_score"]

    assert healthy_score < 25
    assert faulty_score > healthy_score
    assert faulty_score >= 25
    assert faulty_payload["evidence"]
    assert faulty_payload["diagnosis_id"]
