from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest

from app.policy import (
    DestinationView,
    MandateView,
    PayeeView,
    PolicyInput,
    WindowView,
    decide,
)
from app.timeutil import utc_now

CASES_PATH = Path(__file__).parent / "policy_cases.json"

PAYEES = {
    "pay_primefoods": PayeeView(
        payee_id="pay_primefoods",
        name="Prime Foods Ltd",
        verified=True,
        destination=DestinationView("MOCK", "1001000001", "Prime Foods Ltd"),
    ),
    "pay_sunbev": PayeeView(
        payee_id="pay_sunbev",
        name="Sunrise Beverages",
        verified=True,
        destination=DestinationView("MOCK", "1001000002", "Sunrise Beverages"),
    ),
    "pay_market_escrow": PayeeView(
        payee_id="pay_market_escrow",
        name="Marketplace Escrow",
        verified=True,
        kind="escrow",
        destination=DestinationView("MOCK", "1001000003", "Marketplace Escrow"),
    ),
    "pay_greenfarms": PayeeView(
        payee_id="pay_greenfarms",
        name="Green Farms Co-op",
        verified=True,
        destination=DestinationView("MOCK", "1001000004", "Green Farms Co-op"),
    ),
}


def _default_mandate(now, inp: dict) -> MandateView:
    from_off = inp.get("mandate_valid_from_offset_s", -3600)
    until_off = inp.get("mandate_valid_until_offset_s", 7 * 86400)
    spend = inp.get("window_spend", {"daily": 0, "weekly": 0})
    return MandateView(
        mandate_id="mdt_test",
        currency="NGN",
        valid_from=now + timedelta(seconds=from_off),
        valid_until=now + timedelta(seconds=until_off),
        payees=["pay_primefoods", "pay_sunbev", "pay_market_escrow"],
        auto_max_minor=5000000,
        hard_max_minor=15000000,
        windows=[
            WindowView("daily", 86400, 20000000, spend.get("daily", 0)),
            WindowView("weekly", 604800, 60000000, spend.get("weekly", 0)),
        ],
        quarantined=bool(inp.get("quarantined", False)),
        anomaly_enabled=True,
        anomaly_history_count=5,
        anomaly_percent=300,
    )


def _build_input(case: dict) -> PolicyInput:
    inp = case["input"]
    now = utc_now()
    mandate = _default_mandate(now, inp) if inp.get("has_mandate") else None
    dest = None
    if "destination" in inp:
        d = inp["destination"]
        dest = DestinationView(d["bank_code"], d["account_number"], d["account_name"])
    expires_off = inp.get("intent_expires_offset_s", 900)
    return PolicyInput(
        now=now,
        kill_switch_active=bool(inp.get("kill_switch_active", False)),
        mandate=mandate,
        amount_minor=int(inp["amount_minor"]),
        currency=inp["currency"],
        claimed_payee_id=inp.get("payee_id"),
        claimed_destination=dest,
        payees=PAYEES,
        intent_expires_at=now + timedelta(seconds=expires_off),
        wallet_balance_minor=int(inp["wallet_balance_minor"]),
        payee_history_amounts=list(inp.get("anomaly_history", [])),
        block_rules_only=False,
    )


def _load_cases():
    with open(CASES_PATH, encoding="utf-8") as f:
        return json.load(f)


@pytest.mark.parametrize("case", _load_cases(), ids=lambda c: c["name"])
def test_policy_case(case):
    result = decide(_build_input(case))
    assert result.decision == case["expect_decision"], case["name"]
    codes = [r.code for r in result.reasons]
    assert codes == case["expect_codes"], f"{case['name']}: {codes}"


def test_all_reason_codes_covered():
    from app.policy import REASON_CODES

    cases = _load_cases()
    seen = set()
    for c in cases:
        seen.update(c["expect_codes"])
    missing = set(REASON_CODES) - seen
    assert not missing, f"Missing reason codes in policy_cases.json: {missing}"
