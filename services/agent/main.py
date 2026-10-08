"""
Agent Service Main Entrypoint (FastAPI).

Provides endpoints for:
- /healthz (Liveness check)
- /agent/v1/forecast (Demand forecast & backtest)
- /agent/v1/recommendations (SKU reorder points & stock cover)
- /agent/v1/restock/runs (Trigger automated restock agent run in scripted/llm mode)
- /agent/v1/attacks/scenarios (List attack scenarios)
- /agent/v1/attacks/run (Run attack scenarios against MandatePay Gateway)
"""

import uvicorn
from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Any, Optional

from forecast import generate_full_forecast_report
from agent import RestockAgent
from attacks.scenarios import ATTACK_SCENARIOS
from attacks.runner import AttackRunner

app = FastAPI(
    title="TrustRail Restock Agent Service",
    description="AI Forecast, Automated Restock Agent, and Security Attack Simulation Engine",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

restock_agent = RestockAgent()
attack_runner = AttackRunner()

@app.get("/healthz")
def health_check() -> Dict[str, str]:
    return {"status": "ok", "service": "agent", "version": "1.0.0"}

@app.get("/agent/v1/forecast")
def get_forecast() -> Dict[str, Any]:
    """Returns 14-day demand forecasts, backtest metrics (MAE, WAPE), and reorder points for 6 SKUs."""
    reports = generate_full_forecast_report()
    return {
        "status": "success",
        "total_skus": len(reports),
        "forecasts": reports
    }

@app.get("/agent/v1/recommendations")
def get_recommendations() -> Dict[str, Any]:
    """Returns replenishment recommendations based on stock level vs reorder point."""
    recs = restock_agent.get_recommendations()
    return {
        "status": "success",
        "recommendations": recs
    }

@app.post("/agent/v1/restock/runs")
def trigger_restock_run(payload: Dict[str, Any] = Body(default={"mode": "scripted"})) -> Dict[str, Any]:
    """Triggers an automated restock agent run (modes: scripted or llm)."""
    mode = payload.get("mode", "scripted")
    result = restock_agent.run_restock(mode=mode)
    return {
        "status": "success",
        "result": result
    }

@app.get("/agent/v1/attacks/scenarios")
def list_attack_scenarios() -> Dict[str, Any]:
    """Lists available attack scenarios for red-teaming MandatePay."""
    return {
        "scenarios": ATTACK_SCENARIOS
    }

@app.post("/agent/v1/attacks/run")
def run_attack(payload: Dict[str, Any] = Body(default={"scenario_id": "ALL"})) -> Dict[str, Any]:
    """Executes specified attack scenario (or ALL) against MandatePay policy engine."""
    scenario_id = payload.get("scenario_id", "ALL")

    if scenario_id.upper() == "ALL":
        results = attack_runner.run_all_scenarios()
        all_passed = all(r.get("passed", False) for r in results)
        return {
            "status": "success",
            "overall_passed": all_passed,
            "total_scenarios": len(results),
            "results": results
        }
    else:
        result = attack_runner.run_scenario(scenario_id)
        return {
            "status": "success",
            "result": result
        }

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8003, reload=True)
