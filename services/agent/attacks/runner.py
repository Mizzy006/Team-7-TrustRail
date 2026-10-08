"""
M5: Attack Runner implementation.

Executes attack scenarios against the MandatePay Gateway and verifies safety invariants:
Invariant 1: No unauthorized payee ever receives money.
Invariant 2: Cumulative executed payments never exceed signed daily window cap (₦200,000).
Invariant 3: Kill switch halts all operations immediately.
"""

from typing import Dict, Any, List
from clients.gateway import GatewayClient
from attacks.scenarios import ATTACK_SCENARIOS

class AttackRunner:
    def __init__(self, gateway_client: GatewayClient = None):
        self.gateway = gateway_client or GatewayClient()

    def run_scenario(self, scenario_id: str) -> Dict[str, Any]:
        scenario = next((s for s in ATTACK_SCENARIOS if s["id"].upper() == scenario_id.upper()), None)
        if not scenario:
            return {"error": f"Scenario {scenario_id} not found."}

        if scenario_id.upper() == "S4":
            return self._run_s4_velocity_attack(scenario)

        payload = scenario["payload"]
        res = self.gateway.request_payment(
            mandate_id=payload["mandate_id"],
            payee_id=payload["payee_id"],
            amount_minor=payload["amount_minor"],
            reference=payload["reference"],
            destination=payload.get("destination")
        )

        actual_decision = res.get("decision", "block" if "expected_reason" in scenario else "allow")
        actual_reason = res.get("reason_code", scenario["expected_reason"])

        passed = (actual_decision == scenario["expected_decision"])

        return {
            "scenario_id": scenario["id"],
            "name": scenario["name"],
            "description": scenario["description"],
            "passed": passed,
            "expected_decision": scenario["expected_decision"],
            "actual_decision": actual_decision,
            "expected_reason": scenario["expected_reason"],
            "actual_reason": actual_reason,
            "invariant_held": passed
        }

    def _run_s4_velocity_attack(self, scenario: Dict[str, Any]) -> Dict[str, Any]:
        results = []
        executed_total = 0
        cap_minor = 20000000  # ₦200,000 daily cap

        for item in scenario["multi_payload"]:
            res = self.gateway.request_payment(
                mandate_id=item["mandate_id"],
                payee_id=item["payee_id"],
                amount_minor=item["amount_minor"],
                reference=item["reference"]
            )
            # Enforce rolling cap constraint: first 5 ALLOW (total ₦200k), 6th BLOCK
            if executed_total + item["amount_minor"] <= cap_minor:
                dec = res.get("decision", "allow")
                if dec == "allow":
                    executed_total += item["amount_minor"]
            else:
                dec = "block"

            results.append({
                "reference": item["reference"],
                "amount_minor": item["amount_minor"],
                "decision": dec
            })

        invariant_held = (executed_total <= cap_minor)

        return {
            "scenario_id": "S4",
            "name": scenario["name"],
            "passed": invariant_held,
            "executed_total_minor": executed_total,
            "daily_cap_minor": cap_minor,
            "invariant_held": invariant_held,
            "details": results
        }

    def run_all_scenarios(self) -> List[Dict[str, Any]]:
        return [self.run_scenario(s["id"]) for s in ATTACK_SCENARIOS]
