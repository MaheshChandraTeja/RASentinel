def test_actuator_session_telemetry_diagnosis_workflow(client):
    actuator_response = client.post(
        "/api/v1/actuators",
        json={
            "name": "Joint A1 Shoulder Servo",
            "actuator_type": "servo",
            "manufacturer": "Kairais Lab",
            "model_number": "RS-SV-01",
            "location": "Arm Rig / Joint A1",
            "rated_torque_nm": 12.5,
            "rated_current_a": 4.2,
            "rated_voltage_v": 24,
        },
    )

    assert actuator_response.status_code == 201
    actuator = actuator_response.json()
    assert actuator["name"] == "Joint A1 Shoulder Servo"

    session_response = client.post(
        f"/api/v1/actuators/{actuator['id']}/sessions",
        json={
            "name": "Baseline sweep test",
            "source": "manual",
            "tags": {"rig": "lab-arm-v1"},
        },
    )

    assert session_response.status_code == 201
    session = session_response.json()

    telemetry_response = client.post(
        f"/api/v1/sessions/{session['id']}/telemetry",
        json={
            "samples": [
                {
                    "commanded_position": 10.0,
                    "actual_position": 9.7,
                    "commanded_velocity": 2.0,
                    "actual_velocity": 1.8,
                    "commanded_torque": 1.2,
                    "estimated_torque": 1.4,
                    "motor_current": 2.1,
                    "temperature": 36.5,
                    "load_estimate": 0.42,
                    "control_latency_ms": 18.0,
                    "encoder_position": 9.69,
                    "fault_label": "none",
                }
            ]
        },
    )

    assert telemetry_response.status_code == 201
    samples = telemetry_response.json()
    assert len(samples) == 1
    assert samples[0]["error_position"] == 0.3000000000000007

    diagnosis_response = client.post(
        f"/api/v1/sessions/{session['id']}/diagnoses",
        json={
            "fault_label": "response_delay",
            "severity_score": 31.5,
            "confidence_score": 0.78,
            "summary": "Minor response delay detected during sweep.",
            "recommendation": "Re-run sweep and inspect drivetrain friction.",
            "evidence": {
                "latency_ms": 18.0,
                "position_error": 0.3,
            },
        },
    )

    assert diagnosis_response.status_code == 201
    diagnosis = diagnosis_response.json()
    assert diagnosis["severity_band"] == "medium"
    assert diagnosis["fault_label"] == "response_delay"