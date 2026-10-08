"""Reconcile loop — verify payments with the Gateway, never trust the agent.
Spec: docs/PROJECT_SPEC.md Section 4.8
Owner: Software Developer

Runs every 2s. For every order with an intent_id:
  1. GET /internal/v1/intents/{id} from the Gateway
  2. Compare payee, amount, reference against the order's payment_request
  3. Update order status ONLY on a full match
     - executed        -> paid
     - pending_approval -> awaiting_approval
     - blocked/denied/expired/failed -> blocked
     - mismatch        -> NEVER paid (leave as awaiting_payment, log warning)
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class IntentSnapshot:
    """What the Gateway returned about an intent."""
    intent_id: str
    status: str
    payee_id: Optional[str] = None
    amount_minor: Optional[int] = None
    currency: Optional[str] = None
    reference: Optional[str] = None


@dataclass
class OrderPaymentRequest:
    """What we told the agent to pay."""
    payee_id: str
    amount_minor: int
    currency: str
    reference: str


def intent_matches(payment: OrderPaymentRequest, intent: IntentSnapshot) -> bool:
    """Strict match: payee, amount, currency and reference must all line up."""
    return (
        intent.payee_id == payment.payee_id
        and intent.amount_minor == payment.amount_minor
        and intent.currency == payment.currency
        and intent.reference == payment.reference
    )


def resolve_order_status(
    payment: OrderPaymentRequest,
    intent: IntentSnapshot,
) -> str:
    """Return the new order status based on the intent state.

    Possible values: paid | awaiting_approval | blocked | awaiting_payment (unchanged).
    """
    if intent.status == "executed":
        if intent_matches(payment, intent):
            return "paid"
        # Executed but mismatched payee/amount/reference -> never mark paid
        return "awaiting_payment"

    if intent.status == "pending_approval":
        return "awaiting_approval"

    if intent.status in ("blocked", "denied", "expired", "failed"):
        return "blocked"

    return "awaiting_payment"