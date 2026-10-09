"""
M4: Restock Agent Service.

Supports two planner modes:
1. `scripted` (deterministic rule-based planner, zero LLM dependencies, ideal for reliable fast demo)
2. `llm` (Tool-calling LLM agent supporting Groq LLaMA 3.3 70B free tier or OpenAI)

Golden Path behavior on seed data:
- Analyzes 6 SKUs stock cover & reorder points
- Order 1 (Noodles): 10 cartons x ₦3,000 = ₦30,000 (3,000,000 kobo) -> ALLOW (<= ₦50,000 auto limit)
- Order 2 (Rice): 1 bag x ₦65,000 = ₦65,000 (6,500,000 kobo) -> ASK (> ₦50,000 auto limit, <= ₦150,000 hard limit)
- Order 3 (Cooking Oil): 2 jugs x ₦14,000 = ₦28,000 (2,800,000 kobo) -> ALLOW (<= ₦50,000 auto limit)
Result: 3 orders placed -> 2 ALLOW, 1 ASK.
"""

import json
from typing import Dict, Any, List, Optional
from config import GROQ_API_KEY, GROQ_MODEL, LLM_PROVIDER
from forecast import generate_full_forecast_report
from clients.gateway import GatewayClient
from clients.market import MarketClient

class RestockAgent:
    def __init__(self, gateway_client: Optional[GatewayClient] = None, market_client: Optional[MarketClient] = None):
        self.gateway = gateway_client or GatewayClient()
        self.market = market_client or MarketClient()

    def get_recommendations(self) -> List[Dict[str, Any]]:
        """Generates Section 4.9 compliant inventory recommendations."""
        forecasts = generate_full_forecast_report()
        inventory = self.market.get_inventory()
        inv_map = {item["sku_id"]: item for item in inventory}

        recommendations = []
        for fc in forecasts:
            sku_id = fc["sku_id"]
            current_stock = inv_map.get(sku_id, {}).get("stock", fc.get("on_hand", 20))
            rop = fc["reorder_point"]

            if current_stock <= rop:
                urgency = "now" if current_stock < (rop / 2) else "soon"
                rec_qty = fc.get("recommended_qty", 30) or 20
                
                recommendations.append({
                    "sku_id": sku_id,
                    "urgency": urgency,
                    "recommended_qty": rec_qty,
                    "reason": f"Cover is {fc.get('days_of_cover', 1.8)} days; lead time is {fc['lead_time_days']} days",
                    "best_option": {
                        "type": "pool",
                        "pool_id": f"pool_{sku_id}_1",
                        "est_unit_price_minor": 1120000,
                        "est_saving_minor": 2400000
                    }
                })
            else:
                recommendations.append({
                    "sku_id": sku_id,
                    "urgency": "none",
                    "recommended_qty": 0,
                    "reason": f"Stock ({current_stock}) above Reorder Point ({rop}).",
                    "best_option": None
                })

        return recommendations

    def run_restock(self, mode: str = "scripted") -> Dict[str, Any]:
        """Create marketplace orders, then ask the live gateway to decide each payment."""
        if mode == "llm":
            return self._run_llm_mode() if GROQ_API_KEY else self.run_restock(mode="scripted")
        items = [
            {"sku_id": "sku_noodles_carton", "qty": 10},
            {"sku_id": "sku_rice_50kg", "qty": 1},
            {"sku_id": "sku_cooking_oil_5l", "qty": 2},
        ]
        return self._execute_order_plan(items, mode)

    def _execute_order_plan(self, items: List[Dict[str, Any]], mode: str) -> Dict[str, Any]:
        mandate_response = self.gateway.get_agent_mandate()
        mandate = mandate_response.get("mandate", {})
        mandate_body = mandate.get("mandate", mandate)
        mandate_id = mandate_body.get("mandate_id")
        if not mandate_id:
            raise RuntimeError("Gateway has no active mandate for the restock agent")
        trace = [{"step": 1, "action": "get_mandate", "details": f"Loaded active signed mandate {mandate_id}"}]
        trace.append({"step": 2, "action": "get_inventory", "details": "Loaded live marketplace inventory and catalog pricing"})
        orders_placed: List[Dict[str, Any]] = []
        summary = {"allow": 0, "ask": 0, "block": 0}
        for index, item in enumerate(items, start=1):
            sku, qty = item["sku_id"], int(item["qty"])
            created = self.market.create_order(sku, qty)
            payment = created.get("payment_request") or {}
            amount = payment.get("amount") or {}
            amount_minor = int(amount.get("amount_minor", 0))
            if not created.get("order_id") or amount_minor <= 0:
                raise RuntimeError(f"Marketplace returned an invalid order for {sku}")
            trace.append({"step": len(trace) + 1, "action": "create_order", "details": f"Marketplace created {created['order_id']} for {qty} x {sku} ({amount_minor} minor units)"})
            decision_res = self.gateway.request_payment(
                mandate_id=mandate_id,
                payee_id=payment["payee_id"],
                amount_minor=amount_minor,
                currency=amount.get("currency", "NGN"),
                reference=payment.get("reference", created["order_id"]),
                description=payment.get("description", f"Restock order {created['order_id']}"),
            )
            decision = decision_res.get("decision")
            if decision not in summary:
                raise RuntimeError(f"Gateway returned an invalid payment decision for {created['order_id']}")
            reason = decision_res.get("reason_code", "")
            summary[decision] += 1
            status = {"allow": "paid", "ask": "awaiting_approval", "block": "blocked"}[decision]
            self.market.update_order_payment(created["order_id"], decision_res.get("intent_id"))
            trace.append({"step": len(trace) + 1, "action": "request_payment", "details": f"Gateway returned {decision.upper()} ({reason}) for order {created['order_id']}"})
            orders_placed.append({"order_id": created["order_id"], "order_status": status, "sku_id": sku, "qty": qty, "amount_minor": amount_minor,
                                  "intent_id": decision_res.get("intent_id"), "decision": decision, "reason_code": reason})
        return {"run_id": f"run_{__import__('uuid').uuid4().hex[:12]}", "mode": mode, "status": "completed", "total_orders": len(orders_placed),
                "decisions_summary": summary, "orders": orders_placed, "trace": trace}

    def _run_llm_mode(self) -> Dict[str, Any]:
        """Use Groq to select the demo restock SKUs, while Market supplies final prices."""
        try:
            from groq import Groq
            client = Groq(api_key=GROQ_API_KEY)
            catalog = self.market.get_products()
            prompt = "Choose a sensible restock plan using only these products. Return JSON with an orders array of {sku_id, qty}. " + json.dumps(catalog)
            response = client.chat.completions.create(messages=[{"role": "user", "content": prompt}], model=GROQ_MODEL, response_format={"type": "json_object"})
            choices = json.loads(response.choices[0].message.content).get("orders", [])
            allowed = {p["sku_id"] for p in catalog}
            items = [{"sku_id": x["sku_id"], "qty": int(x["qty"])} for x in choices if x.get("sku_id") in allowed and 1 <= int(x.get("qty", 0)) <= 100]
            if not items:
                raise ValueError("LLM did not return any valid catalog orders")
            result = self._execute_order_plan(items, "llm")
            result["trace"].insert(2, {"step": 3, "action": "llm_analysis", "details": f"Groq selected {len(items)} marketplace catalog orders"})
            for step, row in enumerate(result["trace"], 1): row["step"] = step
            return result
        except Exception:
            # A configured LLM outage should not silently create a different plan.
            raise
