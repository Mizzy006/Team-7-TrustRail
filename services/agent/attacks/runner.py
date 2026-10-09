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

        if scenario_id.upper() == "S6":
            return self._run_s6_kill_switch_attack(scenario)

        payload = scenario["payload"]
        res = self.gateway.request_payment(
            mandate_id=payload["mandate_id"],
            payee_id=payload["payee_id"],
            amount_minor=payload["amount_minor"],
            reference=payload["reference"],
            destination=payload.get("destination"),
            description=payload.get("description", "Security demo attack scenario"),
        )

        actual_decision = res.get("decision", "unknown")
        actual_reason = res.get("reason_code", "NO_REASON_RETURNED")

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

    def _run_s6_kill_switch_attack(self, scenario: Dict[str, Any]) -> Dict[str, Any]:
        """Temporarily engage the real gateway kill switch, test a payment, then restore it."""
        was_active = bool(self.gateway.get_kill_switch().get("active"))
        if not was_active:
            self.gateway.set_kill_switch(True, "Security demo: testing kill-switch enforcement")
        try:
            payload = scenario["payload"]
            res = self.gateway.request_payment(
                mandate_id=payload["mandate_id"],
                payee_id=payload["payee_id"],
                amount_minor=payload["amount_minor"],
                reference=payload["reference"],
                destination=payload.get("destination"),
            )
        finally:
            if not was_active:
                self.gateway.set_kill_switch(False, None)

        actual_decision = res.get("decision", "unknown")
        actual_reason = res.get("reason_code", "NO_REASON_RETURNED")
        passed = actual_decision == scenario["expected_decision"]
        return {
            "scenario_id": scenario["id"],
            "name": scenario["name"],
            "passed": passed,
            "expected_decision": scenario["expected_decision"],
            "actual_decision": actual_decision,
            "expected_reason": scenario["expected_reason"],
            "actual_reason": actual_reason,
            "invariant_held": passed,
        }

    def _run_s4_velocity_attack(self, scenario: Dict[str, Any]) -> Dict[str, Any]:
        results = []
        executed_total = 0
        mandate_response = self.gateway.get_agent_mandate()
        mandate_record = mandate_response.get("mandate", {})
        mandate = mandate_record.get("mandate", mandate_record)
        usage_windows = mandate_response.get("usage", {}).get("windows", [])
        window_headrooms = [int(w.get("remaining_minor", 0)) for w in usage_windows]
        available_headroom = min(window_headrooms) if window_headrooms else 0
        amount_minor = int(scenario["multi_payload"][0]["amount_minor"])
        expected_allow_count = min(len(scenario["multi_payload"]), available_headroom // amount_minor)
        cap_minor = min((int(w["cap_minor"]) for w in mandate.get("limits", {}).get("windows", [])), default=20000000)

        for item in scenario["multi_payload"]:
            res = self.gateway.request_payment(
                mandate_id=item["mandate_id"],
                payee_id=item["payee_id"],
                amount_minor=item["amount_minor"],
                reference=item["reference"]
            )
            dec = res.get("decision", "unknown")
            if dec == "allow":
                executed_total += item["amount_minor"]

            results.append({
                "reference": item["reference"],
                "amount_minor": item["amount_minor"],
                "decision": dec,
                "reason_code": res.get("reason_code", "NO_REASON_RETURNED"),
            })

        expected_decisions = ["allow"] * expected_allow_count + ["block"] * (len(results) - expected_allow_count)
        decisions = [item["decision"] for item in results]
        invariant_held = (
            decisions == expected_decisions
            and all(item["reason_code"] == "WINDOW_CAP_EXCEEDED" for item in results[expected_allow_count:])
            and executed_total <= available_headroom
        )

        return {
            "scenario_id": "S4",
            "name": scenario["name"],
            "passed": invariant_held,
            "actual_decision": "block" if any(item["decision"] == "block" for item in results) else "allow",
            "executed_total_minor": executed_total,
            "daily_cap_minor": cap_minor,
            "expected_allow_count": expected_allow_count,
            "actual_allow_count": sum(item["decision"] == "allow" for item in results),
            "invariant_held": invariant_held,
            "details": results
        }

    def run_all_scenarios(self) -> List[Dict[str, Any]]:
        # Exercise the rolling cap before other scenarios can trigger quarantine.
        scenario_ids = ["S4", "S1", "S2", "S3", "S5", "S6"]
        return [self.run_scenario(scenario_id) for scenario_id in scenario_ids]
