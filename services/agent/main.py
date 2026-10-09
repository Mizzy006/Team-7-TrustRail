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
import json
import re
import uuid
import uvicorn
from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI, HTTPException, Body, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Any, List, Optional

from forecast import generate_full_forecast_report
from agent import RestockAgent
from attacks.scenarios import ATTACK_SCENARIOS
from attacks.runner import AttackRunner
from config import GROQ_API_KEY, GROQ_MODEL

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
run_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="restock-run")

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

@app.post("/agent/v1/assistant/chat")
def assistant_chat(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Answer a shopping query using the live Market catalog and Groq when configured."""
    message = str(payload.get("message", "")).strip()
    if not message or len(message) > 2000:
        raise HTTPException(status_code=422, detail="Enter a message between 1 and 2000 characters.")
    try:
        products = restock_agent.market.get_products()
    except Exception as exc:
        logger.exception("Could not load marketplace catalog for assistant")
        raise HTTPException(status_code=502, detail="The marketplace catalog is unavailable right now.") from exc
    if not products:
        raise HTTPException(status_code=503, detail="The marketplace has no products to recommend right now.")

    reply = ""
    selected: List[Dict[str, Any]] = []
    if GROQ_API_KEY:
        try:
            from groq import Groq
            response = Groq(api_key=GROQ_API_KEY).chat.completions.create(
                model=GROQ_MODEL,
                messages=[
                    {"role": "system", "content": "You are MandatePay's shopping assistant. Recommend only SKU ids present in the provided catalog. Do not invent stock, suppliers, ratings, distance, delivery promises, or payment outcomes. Return JSON with a concise helpful 'reply' and an 'items' array of {sku_id, qty}. If no catalog product fits, return an empty items array and ask a brief clarifying question."},
                    {"role": "user", "content": json.dumps({"request": message, "catalog": products})},
                ],
                response_format={"type": "json_object"},
            )
            result = json.loads(response.choices[0].message.content or "{}")
            reply = str(result.get("reply", "")).strip()
            selected = result.get("items", []) if isinstance(result.get("items", []), list) else []
        except Exception:
            logger.exception("Groq assistant request failed; using catalog matching")

    valid_products = {p["sku_id"]: p for p in products if p.get("sku_id") and isinstance(p.get("price_minor"), int)}
    normalized = []
    for item in selected:
        if not isinstance(item, dict) or item.get("sku_id") not in valid_products:
            continue
        try:
            qty = max(1, min(100, int(item.get("qty", 1))))
        except (TypeError, ValueError):
            continue
        normalized.append({"sku_id": item["sku_id"], "qty": qty})

    if not normalized:
        tokens = [t for t in re.findall(r"[a-z0-9]+", message.lower()) if len(t) > 2]
        ranked = sorted(products, key=lambda p: sum(token in f"{p.get('name', '')} {p.get('sku_id', '')}".lower() for token in tokens), reverse=True)
        score = sum(token in f"{ranked[0].get('name', '')} {ranked[0].get('sku_id', '')}".lower() for token in tokens) if ranked and tokens else 0
        if score:
            quantity_match = re.search(r"\b(\d{1,3})\b", message)
            normalized = [{"sku_id": ranked[0]["sku_id"], "qty": int(quantity_match.group(1)) if quantity_match else 1}]
        if not reply:
            reply = "I can help find items in the marketplace catalog. Tell me what you need and how many." if not normalized else "I found a catalog match. The card below uses the current marketplace price."

    options = [{"sku_id": item["sku_id"], "name": valid_products[item["sku_id"]]["name"], "qty": item["qty"],
                "unit_price_minor": valid_products[item["sku_id"]]["price_minor"],
                "total_minor": valid_products[item["sku_id"]]["price_minor"] * item["qty"]} for item in normalized]
    if GROQ_API_KEY and not reply:
        reply = "Here are the closest matches from the current marketplace catalog."
    return {"reply": reply, "options": options, "mode": "llm" if GROQ_API_KEY else "catalog"}

@app.post("/agent/v1/restock/runs")
def trigger_restock_run(payload: Dict[str, Any] = Body(default={"mode": "scripted"})) -> Dict[str, Any]:
    """Start a restock run in the background so service-to-service calls don't hold the browser open."""
    mode = payload.get("mode", "scripted")
    if mode not in {"scripted", "llm"}:
        raise HTTPException(status_code=422, detail="mode must be scripted or llm")
    run_id = f"run_{uuid.uuid4().hex[:12]}"
    runs_store[run_id] = {"run_id": run_id, "mode": mode, "status": "running"}
    run_executor.submit(_execute_restock_run, run_id, mode)
    return {
        "run_id": run_id,
        "status": "running",
        "mode": mode,
    }

def _execute_restock_run(run_id: str, mode: str) -> None:
    try:
        result = restock_agent.run_restock(mode=mode)
        result["run_id"] = run_id
        runs_store[run_id] = result
    except Exception as exc:
        logger.exception("Restock run %s failed", run_id)
        runs_store[run_id] = {"run_id": run_id, "mode": mode, "status": "failed", "error": str(exc)}

@app.get("/agent/v1/restock/runs/{run_id}")
def get_restock_run(run_id: str) -> Dict[str, Any]:
    """Returns step trace and outcomes for a restock run."""
    if run_id not in runs_store:
        raise HTTPException(status_code=404, detail="Restock run not found")
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
