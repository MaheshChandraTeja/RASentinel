def test_release_benchmark_api_route(client):
    response = client.post(
        "/api/v1/release/benchmark",
        json={
            "sample_count": 180,
            "sample_rate_hz": 60,
            "healthy_trials": 1,
            "fault_intensity": 0.75,
            "use_isolation_forest": False,
            "smoothing_window": 5,
            "seed": 777,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["sample_count"] == 180
    assert payload["diagnosis_runtime_ms"] >= 0
    assert any(metric["name"] == "diagnosis_runtime" for metric in payload["metrics"])
    assert "classification_cases" in payload
