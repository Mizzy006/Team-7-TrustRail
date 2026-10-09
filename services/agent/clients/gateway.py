"""
M3: Gateway API Client.

Typed client wrapper for calling MandatePay Gateway endpoints:
- GET /v1/agent/mandate
- POST /v1/payment-intents
- GET /v1/payment-intents/{intent_id}
"""

import requests
import uuid
from typing import Dict, Any, Optional
from config import GATEWAY_URL, AGENT_KEY, OWNER_TOKEN, DEMO_MODE

class GatewayClient:
    def __init__(self, base_url: str = GATEWAY_URL, agent_key: str = AGENT_KEY, owner_token: str = OWNER_TOKEN):
        self.base_url = base_url.rstrip("/")
        self.agent_key = agent_key
        self.owner_token = owner_token

    def _headers(self, prefer_example: Optional[str] = None, idempotency_key: Optional[str] = None) -> Dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.agent_key}",
            "Content-Type": "application/json"
        }
        if prefer_example:
            headers["Prefer"] = f"example={prefer_example}"
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        return headers

    def get_agent_mandate(self) -> Dict[str, Any]:
        url = f"{self.base_url}/v1/agent/mandate"
        try:
            res = requests.get(url, headers=self._headers(), timeout=10)
            if res.status_code == 200:
                return res.json()
            if DEMO_MODE:
                return {"error": f"HTTP {res.status_code}", "body": res.text}
            res.raise_for_status()
            raise RuntimeError(f"Gateway returned HTTP {res.status_code}")
        except requests.RequestException:
            if not DEMO_MODE:
                raise
            return {"mandate_id": "mdt_01DEMO0000000000000001", "status": "active", "simulated": True}

    def request_payment(
        self,
        mandate_id: str,
        payee_id: str,
        amount_minor: int,
        currency: str = "NGN",
        reference: str = "ord_001",
        description: str = "Restock payment",
        destination: Optional[Dict[str, str]] = None,
        prefer_example: Optional[str] = None
    ) -> Dict[str, Any]:
        """Proposes a payment intent to MandatePay Gateway."""
        url = f"{self.base_url}/v1/payment-intents"
        payload = {
            "payee_id": payee_id,
            "amount": {
                "amount_minor": amount_minor,
                "currency": currency
            },
            "reference": reference,
            "description": description
        }
        if destination:
            payload["destination"] = destination

        try:
            idempotency_key = f"demo_{uuid.uuid4().hex}"
            res = requests.post(
                url,
                json=payload,
                headers=self._headers(prefer_example, idempotency_key),
                timeout=10,
            )
            if res.status_code in [200, 201]:
                result = res.json()
                if not result.get("reason_code") and result.get("reasons"):
                    result["reason_code"] = ", ".join(
                        reason.get("code", "") for reason in result["reasons"] if reason.get("code")
                    )
                return result
            if not DEMO_MODE:
                raise requests.HTTPError(
                    f"Gateway returned HTTP {res.status_code}: {res.text}", response=res
                )
        except requests.RequestException:
            if not DEMO_MODE:
                raise

        if not DEMO_MODE:
            raise RuntimeError("Gateway request failed; simulation is disabled")

        # Policy decision simulation (matches seed.json default mandate)
        # auto_max_minor = 5,000,000 (₦50,000), hard_max_minor = 15,000,000 (₦150,000)
        # Payee check: pay_primefoods, pay_sunbev, pay_market_escrow allowed; pay_fake_unregistered blocked
        if payee_id not in ["pay_primefoods", "pay_sunbev", "pay_market_escrow", "pay_greenfarms"]:
            return {
                "intent_id": f"pi_sim_{reference}",
                "status": "decided",
                "decision": "block",
                "reason_code": "PAYEE_NOT_IN_MANDATE",
                "simulated": True
            }

        if destination and destination.get("account_number") == "1001999999":
            return {
                "intent_id": f"pi_sim_{reference}",
                "status": "decided",
                "decision": "block",
                "reason_code": "DESTINATION_MISMATCH",
                "simulated": True
            }

        if "s5" in reference.lower() or "approval" in reference.lower():
            return {
                "intent_id": f"pi_sim_{reference}",
                "status": "decided",
                "decision": "block",
                "reason_code": "APPROVAL_MISMATCH",
                "simulated": True
            }

        if "s6" in reference.lower() or "kill_switch" in reference.lower():
            return {
                "intent_id": f"pi_sim_{reference}",
                "status": "decided",
                "decision": "block",
                "reason_code": "KILL_SWITCH_ACTIVE",
                "simulated": True
            }

        if amount_minor > 15000000:
            return {
                "intent_id": f"pi_sim_{reference}",
                "status": "decided",
                "decision": "block",
                "reason_code": "EXCEEDS_HARD_MAX",
                "simulated": True
            }
        elif amount_minor > 5000000:
            return {
                "intent_id": f"pi_sim_{reference}",
                "status": "decided",
                "decision": "ask",
                "reason_code": "EXCEEDS_AUTO_MAX",
                "simulated": True
            }
        else:
            return {
                "intent_id": f"pi_sim_{reference}",
                "status": "decided",
                "decision": "allow",
                "reason_code": "AUTO_APPROVED",
                "simulated": True
            }

    def get_payment_intent(self, intent_id: str) -> Dict[str, Any]:
        url = f"{self.base_url}/v1/payment-intents/{intent_id}"
        try:
            res = requests.get(url, headers=self._headers(), timeout=10)
            res.raise_for_status()
            return res.json()
        except requests.RequestException:
            if not DEMO_MODE:
                raise
            return {"intent_id": intent_id, "status": "executed", "simulated": True}

    def get_kill_switch(self) -> Dict[str, Any]:
        res = requests.get(
            f"{self.base_url}/v1/kill-switch",
            headers={"Authorization": f"Bearer {self.owner_token}"},
            timeout=10,
        )
        res.raise_for_status()
        return res.json()

    def set_kill_switch(self, active: bool, reason: Optional[str] = None) -> Dict[str, Any]:
        res = requests.put(
            f"{self.base_url}/v1/kill-switch",
            json={"active": active, "reason": reason},
            headers={"Authorization": f"Bearer {self.owner_token}", "Content-Type": "application/json"},
            timeout=10,
        )
        res.raise_for_status()
        return res.json()
