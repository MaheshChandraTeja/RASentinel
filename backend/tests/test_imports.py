import io


def create_actuator(client) -> str:
    response = client.post(
        "/api/v1/actuators",
        json={"name": "Import Test Servo", "actuator_type": "servo"},
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_valid_csv_import_and_duplicate_reject(client):
    actuator_id = create_actuator(client)
    csv_text = """timestamp,commanded_position,actual_position,commanded_velocity,actual_velocity,motor_current,temperature,control_latency_ms,fault_label
2026-01-01T00:00:00+00:00,0,0,1,0.95,2.1,35.0,12,none
2026-01-01T00:00:00.020000+00:00,1,0.92,1,0.91,2.2,35.1,13,none
"""

    response = client.post(
        f"/api/v1/actuators/{actuator_id}/imports/csv",
        data={
            "session_name": "CSV baseline import",
            "duplicate_strategy": "reject",
            "tags_json": '{"source":"pytest"}',
        },
        files={"file": ("telemetry.csv", io.BytesIO(csv_text.encode("utf-8")), "text/csv")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["rows_imported"] == 2

    duplicate = client.post(
        f"/api/v1/actuators/{actuator_id}/imports/csv",
        data={"session_name": "CSV baseline import", "duplicate_strategy": "reject"},
        files={"file": ("telemetry.csv", io.BytesIO(csv_text.encode("utf-8")), "text/csv")},
    )
    assert duplicate.status_code == 409


def test_invalid_csv_returns_clean_errors(client):
    actuator_id = create_actuator(client)
    csv_text = """timestamp,commanded_position,bad_column
2026-01-01T00:00:00+00:00,1,999
"""

    response = client.post(
        f"/api/v1/actuators/{actuator_id}/imports/csv",
        data={"session_name": "Bad CSV"},
        files={"file": ("bad.csv", io.BytesIO(csv_text.encode("utf-8")), "text/csv")},
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert "message" in detail
    assert detail["errors"][0]["field"] == "bad_column"


def test_valid_json_import(client):
    actuator_id = create_actuator(client)
    json_text = """
{
  "session_name": "JSON telemetry import",
  "samples": [
    {
      "timestamp": "2026-01-01T00:00:00+00:00",
      "commanded_position": 10,
      "actual_position": 9.7,
      "motor_current": 2.4,
      "temperature": 36.2,
      "fault_label": "none"
    }
  ]
}
"""

    response = client.post(
        f"/api/v1/actuators/{actuator_id}/imports/json",
        data={"duplicate_strategy": "reject"},
        files={"file": ("telemetry.json", io.BytesIO(json_text.encode("utf-8")), "application/json")},
    )

    assert response.status_code == 200
    assert response.json()["rows_imported"] == 1
