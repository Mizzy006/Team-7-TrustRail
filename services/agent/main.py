"""
Agent Service Main Entrypoint (FastAPI).

Provides Section 4.9 compliant endpoints for:
- GET /healthz
- GET /agent/v1/forecast?sku_id=
- GET /agent/v1/recommendations
- POST /agent/v1/restock/runs
- GET /agent/v1/restock/runs/{run_id}
- GET /agent/v1/attacks
- POST /agent/v1/attacks/{scenario_id}/run
- GET /agent/v1/attacks/summary
- POST /demo/v1/reset
"""

import logging
import uvicorn
from fastapi import FastAPI, HTTPException, Body, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Any, List, Optional

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
    allow_origins=[
        "https://mandatemarket.vercel.app",
        "http://localhost:3000",
        "http://localhost:5173",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

logger = logging.getLogger(__name__)

restock_agent = RestockAgent()
attack_runner = AttackRunner()

# In-memory store for runs and attack history
runs_store: Dict[str, Dict[str, Any]] = {}
attack_history: List[Dict[str, Any]] = []

@app.get("/healthz")
def health_check() -> Dict[str, str]:
    return {"status": "ok", "service": "agent", "version": "1.0.0"}

@app.get("/agent/v1/forecast")
def get_forecast(sku_id: Optional[str] = Query(None)) -> List[Dict[str, Any]]:
    """Returns 14-day demand forecasts, backtest metrics, and reorder points."""
    reports = generate_full_forecast_report(target_sku=sku_id)
    return reports

@app.get("/agent/v1/recommendations")
def get_recommendations() -> List[Dict[str, Any]]:
    """Returns restock recommendations for the retailer."""
    return restock_agent.get_recommendations()

@app.post("/agent/v1/restock/runs")
def trigger_restock_run(payload: Dict[str, Any] = Body(default={"mode": "scripted"})) -> Dict[str, Any]:
    """Starts a restock run and returns run_id and initial status."""
    mode = payload.get("mode", "scripted")
    run_res = restock_agent.run_restock(mode=mode)
    run_id = run_res["run_id"]
    runs_store[run_id] = run_res
    return {
        "run_id": run_id,
        "status": run_res["status"],
        "mode": mode,
        "summary": run_res.get("decisions_summary")
    }

@app.get("/agent/v1/restock/runs/{run_id}")
def get_restock_run(run_id: str) -> Dict[str, Any]:
    """Returns step trace and outcomes for a restock run."""
    if run_id not in runs_store:
        # Return fallback run if requested
        return restock_agent.run_restock(mode="scripted")
    return runs_store[run_id]

@app.get("/agent/v1/attacks")
def list_attack_scenarios() -> List[Dict[str, Any]]:
    """Lists attack scenarios per section 4.9."""
    return ATTACK_SCENARIOS

@app.post("/agent/v1/attacks/{scenario_id}/run")
def run_attack_scenario(scenario_id: str) -> Dict[str, Any]:
    """Executes a specific attack scenario (S1 to S6 or ALL)."""
    try:
        if scenario_id.upper() == "ALL":
            results = attack_runner.run_all_scenarios()
            for r in results:
                attack_history.append(r)
            return {
                "scenario_id": "ALL",
                "verdict": "contained" if all(r.get("invariant_held", False) for r in results) else "breached",
                "results": results
            }

        res = attack_runner.run_scenario(scenario_id)
        attack_history.append(res)
        return res
    except Exception as exc:
        logger.exception("Attack scenario %s failed", scenario_id)
        raise HTTPException(
            status_code=502,
            detail="The agent could not complete the security run. Check the agent logs for the gateway error.",
        ) from exc

@app.get("/agent/v1/attacks/summary")
def get_attack_summary() -> Dict[str, Any]:
    """Running totals for the blast-radius meter (section 4.9)."""
    attempts = len(attack_history)
    blocked = sum(1 for a in attack_history if a.get("actual_decision") == "block")
    asked = sum(1 for a in attack_history if a.get("actual_decision") == "ask")
    executed = sum(1 for a in attack_history if a.get("actual_decision") == "allow")
    executed_total_minor = sum(a.get("executed_total_minor", 0) for a in attack_history)
    breaches = sum(1 for a in attack_history if not a.get("invariant_held", True))

    return {
        "attempts": attempts,
        "blocked": blocked,
        "asked": asked,
        "executed": executed,
        "executed_total_minor": executed_total_minor,
        "breaches": breaches
    }

@app.post("/demo/v1/reset")
def reset_demo() -> Dict[str, Any]:
    """Resets agent history and demo marketplace orders."""
    runs_store.clear()
    attack_history.clear()
    restock_agent.market.reset_demo_orders()
    return {"status": "reset_complete", "runs_cleared": True, "attacks_cleared": True, "orders_cleared": True}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8003, reload=True)
