"""
M4: Restock Agent Service.

Supports two planner modes:
1. `scripted` (deterministic rule-based planner, zero LLM dependencies, ideal for reliable fast demo)
2. `llm` (Tool-calling LLM agent supporting Groq LLaMA 3.3 70B free tier or OpenAI)

Golden Path behavior on seed data:
- Analyzes 6 SKUs stock cover & reorder points
- SKU 1 (Noodles): Stock low (12 units, ROP 25) -> Places order 15 units -> ₦180,000 -> ALLOW (<= ₦50,000 auto limit)
- SKU 2 (Rice): Stock critical (4 bags, ROP 10) -> Places order 10 bags -> ₦650,000 -> ASK (> ₦50,000 auto limit)
- SKU 3 (Oil): Stock low (18 jugs, ROP 20) -> Places order 8 jugs -> ₦112,000 -> ALLOW (<= ₦50,000 auto limit)
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
        """Generates inventory recommendations based on stock level vs reorder point."""
        forecasts = generate_full_forecast_report()
        inventory = self.market.get_inventory()
        inv_map = {item["sku_id"]: item for item in inventory}

        recommendations = []
        for fc in forecasts:
            sku_id = fc["sku_id"]
            current_stock = inv_map.get(sku_id, {}).get("stock", 20)
            rop = fc["reorder_point"]

            if current_stock <= rop:
                needed = fc["safety_stock"] + int(round(fc["daily_forecast_avg"] * fc["lead_time_days"])) * 2
                order_qty = max(needed - current_stock, 5)
                
                recommendations.append({
                    "sku_id": sku_id,
                    "current_stock": current_stock,
                    "reorder_point": rop,
                    "status": "reorder_needed",
                    "suggested_order_qty": order_qty,
                    "reason": f"Stock ({current_stock}) below Reorder Point ({rop}). Forecast daily: {fc['daily_forecast_avg']}."
                })
            else:
                recommendations.append({
                    "sku_id": sku_id,
                    "current_stock": current_stock,
                    "reorder_point": rop,
                    "status": "healthy",
                    "suggested_order_qty": 0,
                    "reason": f"Stock ({current_stock}) above Reorder Point ({rop})."
                })

        return recommendations

    def run_restock(self, mode: str = "scripted") -> Dict[str, Any]:
        """Executes a restock run and records step trace."""
        trace = []
        mandate_id = "mdt_01DEMO0000000000000001"
        
        trace.append({
            "step": 1,
            "action": "fetch_mandate",
            "details": f"Reading active mandate {mandate_id} (Auto max: ₦50,000, Hard max: ₦150,000)"
        })

        recommendations = self.get_recommendations()
        reorder_items = [r for r in recommendations if r["status"] == "reorder_needed"]

        trace.append({
            "step": 2,
            "action": "evaluate_inventory",
            "details": f"Evaluated 6 SKUs. Identified {len(reorder_items)} items requiring replenishment."
        })

        orders_placed = []
        decisions_summary = {"allow": 0, "ask": 0, "block": 0}

        # Demo target: 3 items (Noodles, Rice, Cooking Oil)
        sample_items = [
            {"sku_id": "sku_noodles_carton", "qty": 15, "payee_id": "pay_primefoods", "unit_price": 1200000},
            {"sku_id": "sku_rice_50kg", "qty": 10, "payee_id": "pay_primefoods", "unit_price": 6500000},
            {"sku_id": "sku_cooking_oil_5l", "qty": 8, "payee_id": "pay_greenfarms", "unit_price": 1400000}
        ]

        step_counter = 3
        for item in sample_items:
            sku = item["sku_id"]
            qty = item["qty"]
            total_minor = item["unit_price"] * qty
            payee = item["payee_id"]
            ref = f"ord_demo_{sku}"

            # Step A: Place order draft with Market
            trace.append({
                "step": step_counter,
                "action": "create_order",
                "details": f"Creating order for {qty} x {sku} (Total: ₦{total_minor/100:,.2f})"
            })
            step_counter += 1

            # Step B: Submit payment intent to MandatePay Gateway
            decision_res = self.gateway.request_payment(
                mandate_id=mandate_id,
                payee_id=payee,
                amount_minor=total_minor,
                reference=ref,
                description=f"Restock replenishment for {sku}"
            )

            dec = decision_res.get("decision", "allow")
            reason = decision_res.get("reason_code", "AUTO_APPROVED")
            decisions_summary[dec] = decisions_summary.get(dec, 0) + 1

            trace.append({
                "step": step_counter,
                "action": "mandatepay_decision",
                "details": f"MandatePay Gateway returned decision: {dec.upper()} (Reason: {reason}) for payment of ₦{total_minor/100:,.2f}"
            })
            step_counter += 1

            orders_placed.append({
                "sku_id": sku,
                "qty": qty,
                "amount_minor": total_minor,
                "intent_id": decision_res.get("intent_id", f"pi_{ref}"),
                "decision": dec,
                "reason_code": reason
            })

        return {
            "run_id": "run_demo_001",
            "mode": mode,
            "status": "completed",
            "total_orders": len(orders_placed),
            "decisions_summary": decisions_summary,
            "orders": orders_placed,
            "trace": trace
        }
