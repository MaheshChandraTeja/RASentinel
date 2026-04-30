def create_actuator(client):
    response = client.post(
        "/api/v1/actuators",
        json={
            "name": "RAS Test Servo",
            "actuator_type": "servo",
            "location": "diagnostics-test-rig",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def simulate(client, actuator_id: str, session_name: str, fault_profile: str, seed: int):
    response = client.post(
        "/api/v1/telemetry/simulate",
        json={
            "actuator_id": actuator_id,
            "session_name": session_name,
            "duplicate_strategy": "create_new",
            "config": {
                "fault_profile": fault_profile,
                "seed": seed,
                "sample_rate_hz": 50,
                "duration_s": 20,
                "commanded_amplitude": 45,
                "command_frequency_hz": 0.2,
                "nominal_current_a": 2.2,
                "nominal_temperature_c": 34,
                "nominal_load": 0.45,
                "response_time_constant_s": 0.08,
                "base_latency_ms": 12,
                "sensor_noise_std": 0.04,
                "current_noise_std": 0.03,
                "temperature_noise_std": 0.05,
                "fault_intensity": 0.75,
            },
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["rows_imported"] == 1000
    return payload


def test_full_simulator_baseline_diagnosis_report_flow(client):
    actuator = create_actuator(client)

    healthy_import = simulate(client, actuator["id"], "Healthy baseline run", "healthy", 101)
    delayed_import = simulate(client, actuator["id"], "Delayed response run", "delayed_response", 202)

    baseline_response = client.post(
        f"/api/v1/actuators/{actuator['id']}/baselines/from-session",
        json={
            "session_id": healthy_import["session_id"],
            "name": "Known-good baseline",
            "smoothing_window": 5,
            "activate": True,
        },
    )
    assert baseline_response.status_code == 201, baseline_response.text
    baseline = baseline_response.json()

    diagnosis_response = client.post(
        f"/api/v1/diagnostics/run/{delayed_import['session_id']}",
        json={
            "baseline_id": baseline["id"],
            "smoothing_window": 5,
            "persist": True,
            "use_isolation_forest": False,
        },
    )
    assert diagnosis_response.status_code == 201, diagnosis_response.text
    diagnosis_payload = diagnosis_response.json()

    assert diagnosis_payload["diagnosis_id"]
    assert diagnosis_payload["classification"]["fault_label"] in {"response_delay", "delayed_response"}
    assert diagnosis_payload["classification"]["confidence_score"] > 0.3
    assert diagnosis_payload["classification"]["evidence"]
    assert diagnosis_payload["drift_score"] is not None

    diagnosis_id = diagnosis_payload["diagnosis_id"]

    get_response = client.get(f"/api/v1/diagnostics/{diagnosis_id}")
    assert get_response.status_code == 200, get_response.text
    assert get_response.json()["id"] == diagnosis_id

    timeline_response = client.get(f"/api/v1/actuators/{actuator['id']}/health")
    assert timeline_response.status_code == 200, timeline_response.text
    assert timeline_response.json()["points"]

    report_response = client.get(f"/api/v1/reports/{diagnosis_id}")
    assert report_response.status_code == 200, report_response.text
    report = report_response.json()
    assert report["diagnosis_id"] == diagnosis_id
    assert report["classification"]
    assert report["maintenance_action"]

    markdown_response = client.get(f"/api/v1/reports/{diagnosis_id}/markdown")
    assert markdown_response.status_code == 200, markdown_response.text
    assert "RASentinel Diagnostic Report" in markdown_response.text
