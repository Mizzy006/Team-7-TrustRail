from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


REASON_CODES = [
    "KILL_SWITCH_ACTIVE",
    "NO_ACTIVE_MANDATE",
    "MANDATE_NOT_YET_VALID",
    "MANDATE_EXPIRED",
    "CURRENCY_MISMATCH",
    "PAYEE_UNKNOWN",
    "DESTINATION_MISMATCH",
    "PAYEE_NOT_ALLOWED",
    "INTENT_EXPIRED",
    "PER_TXN_HARD_MAX_EXCEEDED",
    "WINDOW_CAP_EXCEEDED",
    "INSUFFICIENT_FUNDS",
    "QUARANTINED",
    "OVER_AUTO_LIMIT",
    "ANOMALOUS_AMOUNT",
]


@dataclass
class Reason:
    code: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "detail": self.detail}


@dataclass
class DestinationView:
    bank_code: str
    account_number: str
    account_name: str


@dataclass
class PayeeView:
    payee_id: str
    name: str
    verified: bool
    destination: DestinationView
    kind: str = "producer"


@dataclass
class WindowView:
    name: str
    seconds: int
    cap_minor: int
    spent_minor: int = 0


@dataclass
class MandateView:
    mandate_id: str
    currency: str
    valid_from: datetime
    valid_until: datetime
    payees: list[str]
    auto_max_minor: int
    hard_max_minor: int
    windows: list[WindowView]
    quarantined: bool
    anomaly_enabled: bool
    anomaly_history_count: int
    anomaly_percent: int


@dataclass
class PolicyInput:
    now: datetime
    kill_switch_active: bool
    mandate: Optional[MandateView]
    amount_minor: int
    currency: str
    claimed_payee_id: Optional[str]
    claimed_destination: Optional[DestinationView]
    payees: dict[str, PayeeView]
    intent_expires_at: datetime
    wallet_balance_minor: int
    payee_history_amounts: list[int] = field(default_factory=list)
    block_rules_only: bool = False


@dataclass
class PolicyResult:
    decision: str  # allow | ask | block
    reasons: list[Reason]
    resolved_payee_id: Optional[str] = None

    @property
    def primary_code(self) -> Optional[str]:
        return self.reasons[0].code if self.reasons else None


def _fmt_ngn(minor: int) -> str:
    major = minor // 100
    frac = minor % 100
    return f"{major}.{frac:02d} NGN"


def resolve_payee(
    claimed_payee_id: Optional[str],
    claimed_destination: Optional[DestinationView],
    payees: dict[str, PayeeView],
) -> tuple[Optional[str], Optional[Reason]]:
    """Resolve payee; return (payee_id, block_reason_or_None)."""
    if claimed_payee_id and claimed_destination:
        payee = payees.get(claimed_payee_id)
        if payee is None:
            return None, Reason("PAYEE_UNKNOWN", f"Payee {claimed_payee_id} is not registered")
        dest = payee.destination
        if (
            dest.bank_code != claimed_destination.bank_code
            or dest.account_number != claimed_destination.account_number
        ):
            return claimed_payee_id, Reason(
                "DESTINATION_MISMATCH",
                "Destination does not match the registered payee",
            )
        return claimed_payee_id, None

    if claimed_payee_id:
        if claimed_payee_id not in payees:
            return None, Reason("PAYEE_UNKNOWN", f"Payee {claimed_payee_id} is not registered")
        return claimed_payee_id, None

    if claimed_destination:
        for pid, payee in payees.items():
            d = payee.destination
            if (
                d.bank_code == claimed_destination.bank_code
                and d.account_number == claimed_destination.account_number
            ):
                return pid, None
        return None, Reason("PAYEE_UNKNOWN", "No registered payee has this destination")

    return None, Reason("PAYEE_UNKNOWN", "No payee_id or destination provided")


def decide(inp: PolicyInput) -> PolicyResult:
    """Pure decision engine. First BLOCK wins; else collect all ASKs."""
    reasons: list[Reason] = []
    resolved: Optional[str] = None

    # 1 KILL_SWITCH
    if inp.kill_switch_active:
        return PolicyResult("block", [Reason("KILL_SWITCH_ACTIVE", "Kill switch is active")], None)

    # 2 MANDATE
    m = inp.mandate
    if m is None:
        return PolicyResult("block", [Reason("NO_ACTIVE_MANDATE", "No active mandate for this agent")], None)
    if inp.now < m.valid_from:
        return PolicyResult(
            "block",
            [Reason("MANDATE_NOT_YET_VALID", "Mandate valid_from is in the future")],
            None,
        )
    if inp.now > m.valid_until:
        return PolicyResult("block", [Reason("MANDATE_EXPIRED", "Mandate valid_until has passed")], None)

    # 3 CURRENCY
    if inp.currency != m.currency:
        return PolicyResult(
            "block",
            [Reason("CURRENCY_MISMATCH", f"Intent currency {inp.currency} != mandate {m.currency}")],
            None,
        )

    # 4 PAYEE
    resolved, payee_reason = resolve_payee(inp.claimed_payee_id, inp.claimed_destination, inp.payees)
    if payee_reason is not None:
        return PolicyResult("block", [payee_reason], resolved)
    assert resolved is not None
    if resolved not in m.payees:
        return PolicyResult(
            "block",
            [Reason("PAYEE_NOT_ALLOWED", f"Payee {resolved} is not on the mandate allowlist")],
            resolved,
        )

    # 5 INTENT_EXPIRED
    if inp.intent_expires_at < inp.now:
        return PolicyResult("block", [Reason("INTENT_EXPIRED", "Intent expires_at is in the past")], resolved)

    # 6 HARD MAX
    if inp.amount_minor > m.hard_max_minor:
        return PolicyResult(
            "block",
            [
                Reason(
                    "PER_TXN_HARD_MAX_EXCEEDED",
                    f"{_fmt_ngn(inp.amount_minor)} exceeds hard max {_fmt_ngn(m.hard_max_minor)}",
                )
            ],
            resolved,
        )

    # 7 WINDOW CAPS (equal-to-cap allowed: spend + amount > cap blocks)
    for w in m.windows:
        if w.spent_minor + inp.amount_minor > w.cap_minor:
            return PolicyResult(
                "block",
                [
                    Reason(
                        "WINDOW_CAP_EXCEEDED",
                        f"Window '{w.name}' would exceed cap {_fmt_ngn(w.cap_minor)}",
                    )
                ],
                resolved,
            )

    # 8 FUNDS
    if inp.wallet_balance_minor < inp.amount_minor:
        return PolicyResult(
            "block",
            [Reason("INSUFFICIENT_FUNDS", "Wallet balance is below the amount")],
            resolved,
        )

    if inp.block_rules_only:
        return PolicyResult("allow", [], resolved)

    # 9 QUARANTINED
    if m.quarantined:
        reasons.append(Reason("QUARANTINED", "Mandate is quarantined; owner approval required"))

    # 10 OVER_AUTO_LIMIT
    if inp.amount_minor > m.auto_max_minor:
        reasons.append(
            Reason(
                "OVER_AUTO_LIMIT",
                f"{_fmt_ngn(inp.amount_minor)} is above the {_fmt_ngn(m.auto_max_minor)} auto limit",
            )
        )

    # 11 ANOMALOUS_AMOUNT: amount * 100 * n > percent * sum
    if m.anomaly_enabled:
        n = m.anomaly_history_count
        hist = inp.payee_history_amounts[:n]
        if len(hist) >= n:
            total = sum(hist)
            if total > 0 and inp.amount_minor * 100 * n > m.anomaly_percent * total:
                avg = total // n
                mult = (inp.amount_minor * n) / total if total else 0
                reasons.append(
                    Reason(
                        "ANOMALOUS_AMOUNT",
                        f"{mult:.1f}x the average of the last {n} payments to this payee",
                    )
                )

    if reasons:
        return PolicyResult("ask", reasons, resolved)
    return PolicyResult("allow", [], resolved)


def mandate_view_from_body(
    body: dict[str, Any],
    *,
    quarantined: bool,
    window_spend: dict[str, int],
    valid_from: datetime,
    valid_until: datetime,
) -> MandateView:
    limits = body["limits"]
    anomaly = body["ask_rules"]["anomaly"]
    windows = [
        WindowView(
            name=w["name"],
            seconds=int(w["seconds"]),
            cap_minor=int(w["cap_minor"]),
            spent_minor=int(window_spend.get(w["name"], 0)),
        )
        for w in limits["windows"]
    ]
    return MandateView(
        mandate_id=body["mandate_id"],
        currency=body["currency"],
        valid_from=valid_from,
        valid_until=valid_until,
        payees=list(body["payees"]),
        auto_max_minor=int(limits["per_txn"]["auto_max_minor"]),
        hard_max_minor=int(limits["per_txn"]["hard_max_minor"]),
        windows=windows,
        quarantined=quarantined,
        anomaly_enabled=bool(anomaly["enabled"]),
        anomaly_history_count=int(anomaly["history_count"]),
        anomaly_percent=int(anomaly["percent_of_average"]),
    )
