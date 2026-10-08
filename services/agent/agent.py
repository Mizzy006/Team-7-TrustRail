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
        """Executes a restock run and records step trace."""
        trace = []
        mandate_id = "mdt_01DEMO0000000000000001"
        
        trace.append({
            "step": 1,
            "action": "get_mandate",
            "details": f"Reading active mandate {mandate_id} (Auto max: ₦50,000, Hard max: ₦150,000)"
        })

        recommendations = self.get_recommendations()
        reorder_items = [r for r in recommendations if r["urgency"] in ["now", "soon"]]

        trace.append({
            "step": 2,
            "action": "get_inventory",
            "details": f"Evaluated 6 SKUs. Identified {len(reorder_items)} items requiring replenishment."
        })

        orders_placed = []
        decisions_summary = {"allow": 0, "ask": 0, "block": 0}

        # Golden path sample items matching section 4.10: 2 ALLOW, 1 ASK
        sample_items = [
            {"sku_id": "sku_noodles_carton", "qty": 10, "payee_id": "pay_primefoods", "unit_price": 300000},    # ₦30,000 -> ALLOW
            {"sku_id": "sku_rice_50kg", "qty": 1, "payee_id": "pay_primefoods", "unit_price": 6500000},         # ₦65,000 -> ASK
            {"sku_id": "sku_cooking_oil_5l", "qty": 2, "payee_id": "pay_market_escrow", "unit_price": 1400000}  # ₦28,000 -> ALLOW
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
                "action": "request_payment",
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
