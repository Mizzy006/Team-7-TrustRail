#!/usr/bin/env python3
"""
Standalone test runner for Agent Service.
"""

import sys
from fastapi.testclient import TestClient
from main import app

def run_all_tests():
    client = TestClient(app)
    print("--> Testing /healthz...")
    r = client.get("/healthz")
    assert r.status_code == 200, f"Healthz failed: {r.text}"
    print("    [PASS] Healthz ok")

    print("--> Testing /agent/v1/forecast...")
    r = client.get("/agent/v1/forecast")
    assert r.status_code == 200
    forecasts = r.json()
    assert len(forecasts) == 6
    print(f"    [PASS] Returned {len(forecasts)} SKU forecasts")

    print("--> Testing /agent/v1/recommendations...")
    r = client.get("/agent/v1/recommendations")
    assert r.status_code == 200
    print("    [PASS] Recommendations ok")

    print("--> Testing /agent/v1/restock/runs (Golden Path: 2 ALLOW, 1 ASK)...")
    r = client.post("/agent/v1/restock/runs", json={"mode": "scripted"})
    assert r.status_code == 200
    run_id = r.json()["run_id"]
    r_trace = client.get(f"/agent/v1/restock/runs/{run_id}")
    trace_data = r_trace.json()
    summary = trace_data["decisions_summary"]
    assert summary["allow"] == 2 and summary["ask"] == 1, f"Expected 2 ALLOW, 1 ASK, got {summary}"
    print(f"    [PASS] Restock run produced 2 ALLOW, 1 ASK (summary: {summary})")

    print("--> Testing Attack Scenarios S1-S6...")
    r_att = client.post("/agent/v1/attacks/ALL/run")
    assert r_att.status_code == 200
    att_data = r_att.json()
    assert att_data.get("verdict") == "contained", f"Attack verdict failed: {att_data}"
    print("    [PASS] Attack scenarios passed with verdict: CONTAINED")

    print("--> Testing /agent/v1/attacks/summary...")
    r_sum = client.get("/agent/v1/attacks/summary")
    assert r_sum.status_code == 200
    sum_data = r_sum.json()
    assert sum_data["breaches"] == 0
    print(f"    [PASS] Summary blast-radius meter ok: {sum_data}")

    print("\nALL AGENT SERVICE TESTS PASSED 100%!")

if __name__ == "__main__":
    try:
        run_all_tests()
        sys.exit(0)
    except Exception as e:
        import traceback
        traceback.print_exc()
        sys.exit(1)
