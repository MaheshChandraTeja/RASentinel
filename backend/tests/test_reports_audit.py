def _create_diagnosed_session(client):
    actuator_response = client.post(
        "/api/v1/actuators",
        json={
            "name": "Audit Joint Servo",
            "actuator_type": "servo",
            "location": "QA Rig / Axis 2",
        },
    )
    assert actuator_response.status_code == 201, actuator_response.text
    actuator = actuator_response.json()

    session_response = client.post(
        f"/api/v1/actuators/{actuator['id']}/sessions",
        json={"name": "Audit thermal sweep", "source": "pytest"},
    )
    assert session_response.status_code == 201, session_response.text
    session = session_response.json()

    samples = []
    for i in range(120):
        commanded = float(i) * 0.25
        drift = max(0.0, i - 40) * 0.018
        actual = commanded - 0.2 - drift
        samples.append(
            {
                "commanded_position": commanded,
                "actual_position": actual,
                "commanded_velocity": 1.5,
                "actual_velocity": 1.25 - drift * 0.05,
                "motor_current": 2.0 + drift,
                "temperature": 35.0 + drift * 8,
                "control_latency_ms": 12.0 + drift * 20,
                "encoder_position": actual,
                "fault_label": "thermal_rise" if drift > 0.6 else "none",
            }
        )

    telemetry_response = client.post(
        f"/api/v1/sessions/{session['id']}/telemetry",
        json={"samples": samples},
    )
    assert telemetry_response.status_code == 201, telemetry_response.text

    diagnosis_response = client.post(
        f"/api/v1/diagnostics/run/{session['id']}",
        json={"persist": True, "use_isolation_forest": False},
    )
    assert diagnosis_response.status_code == 201, diagnosis_response.text
    diagnosis = diagnosis_response.json()
    assert diagnosis["diagnosis_id"]
    return actuator, session, diagnosis


def test_audit_report_html_and_history(client):
    actuator, _session, diagnosis = _create_diagnosed_session(client)
    diagnosis_id = diagnosis["diagnosis_id"]

    audit_response = client.get(f"/api/v1/reports/{diagnosis_id}/audit?persist=true")
    assert audit_response.status_code == 200, audit_response.text
    audit = audit_response.json()
    assert audit["diagnosis_id"] == diagnosis_id
    assert audit["actuator_information"]["name"] == "Audit Joint Servo"
    assert isinstance(audit["evidence_signals"], list)
    assert audit["html_url"].endswith(f"/reports/{diagnosis_id}/html")

    html_response = client.get(f"/api/v1/reports/{diagnosis_id}/html")
    assert html_response.status_code == 200, html_response.text
    assert "text/html" in html_response.headers["content-type"]
    assert "RASentinel Diagnostic Report" in html_response.text

    history_response = client.get(f"/api/v1/reports/history?actuator_id={actuator['id']}&query=thermal")
    assert history_response.status_code == 200, history_response.text
    history = history_response.json()
    assert history["total"] >= 1
    assert history["items"][0]["diagnosis_id"] == diagnosis_id
