def test_health_check(client):
    response = client.get("/api/v1/health")

    assert response.status_code == 200

    payload = response.json()
    assert payload["app"] == "RASentinel"
    assert payload["status"] in {"ok", "degraded"}