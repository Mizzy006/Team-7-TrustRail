"""
Unit tests for ML Agent Service.
"""

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_healthz():
    res = client.get("/healthz")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"

def test_forecast_endpoint():
    res = client.get("/agent/v1/forecast")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert len(data) == 6
    first = data[0]
    assert "sku_id" in first
    assert "reorder_point" in first
    assert "daily_forecast" in first

def test_recommendations_endpoint():
    res = client.get("/agent/v1/recommendations")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)

def test_restock_run():
    res = client.post("/agent/v1/restock/runs", json={"mode": "scripted"})
    assert res.status_code == 200
    data = res.json()
    assert "run_id" in data
    run_id = data["run_id"]

    # Check trace retrieval
    trace_res = client.get(f"/agent/v1/restock/runs/{run_id}")
    assert trace_res.status_code == 200
    trace_data = trace_res.json()
    assert trace_data["decisions_summary"]["allow"] == 2
    assert trace_data["decisions_summary"]["ask"] == 1

def test_attacks_endpoints():
    scenarios_res = client.get("/agent/v1/attacks")
    assert scenarios_res.status_code == 200
    assert len(scenarios_res.json()) == 6

    run_s1 = client.post("/agent/v1/attacks/S1/run")
    assert run_s1.status_code == 200
    assert run_s1.json()["passed"] is True

    summary_res = client.get("/agent/v1/attacks/summary")
    assert summary_res.status_code == 200
    summary = summary_res.json()
    assert summary["attempts"] >= 1
    assert summary["breaches"] == 0
