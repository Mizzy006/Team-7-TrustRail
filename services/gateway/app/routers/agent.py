from __future__ import annotations

import hashlib
import json
from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, Response
from sqlalchemy.orm import Session

from app.audit import write_audit
from app.auth import AuthContext, require_agent
from app.config import get_settings
from app.crypto import intent_hash
from app.db import get_db
from app.errors import Conflict, NotFound, ValidationFailed
from app.helpers import (
    active_mandate_for_agent,
    build_mandate_view,
    compute_usage,
    count_recent_blocks,
    intent_to_out,
    lock_principal,
    mandate_to_out,
    payee_history_amounts,
    payee_registry,
)
from app.ids import new_approval_id, new_intent_id
from app.models import (
    Approval,
    IdempotencyKey,
    KillSwitch,
    Mandate,
    Payee,
    PaymentIntent,
)
from app.policy import DestinationView, PolicyInput, decide
from app.rail import get_payee_account, get_wallet, hold_funds, transfer
from app.schemas import PaymentIntentOut, PaymentIntentRequest
from app.timeutil import add_seconds, format_ts, parse_ts, utc_now

router = APIRouter(prefix="/v1", tags=["Agent"])


def _request_body_hash(body: PaymentIntentRequest) -> str:
    payload = body.model_dump(mode="json", exclude_none=False)
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _execute_allow(
    db: Session,
    *,
    intent: PaymentIntent,
    now,
) -> None:
    settings = get_settings()
    wallet = get_wallet(db, intent.principal_id)
    assert intent.payee_id is not None
    payee_acct = get_payee_account(db, intent.payee_id)
    if intent.payee_id == settings.escrow_payee_id:
        entry, hold = hold_funds(
            db,
            wallet=wallet,
            escrow=payee_acct,
            amount_minor=intent.amount_minor,
            currency=intent.currency,
            intent_id=intent.intent_id,
            principal_id=intent.principal_id,
            ts=now,
        )
        intent.ledger_entry_id = entry.entry_id
        intent.hold_id = hold.hold_id
        hold_id = hold.hold_id
    else:
        entry = transfer(
            db,
            from_account=wallet,
            to_account=payee_acct,
            amount_minor=intent.amount_minor,
            currency=intent.currency,
            intent_id=intent.intent_id,
            ts=now,
        )
        intent.ledger_entry_id = entry.entry_id
        intent.hold_id = None
        hold_id = None
    intent.status = "executed"
    intent.executed_at = now
    write_audit(
        db,
        event_type="payment.executed",
        principal_id=intent.principal_id,
        actor={"type": "agent", "id": intent.agent_id},
        subject={"type": "intent", "id": intent.intent_id},
        data={
            "intent_id": intent.intent_id,
            "ledger_entry_id": entry.entry_id,
            "hold_id": hold_id,
        },
        ts=now,
    )


@router.get("/agent/mandate")
def get_agent_mandate(auth: AuthContext = Depends(require_agent), db: Session = Depends(get_db)):
    m = active_mandate_for_agent(db, auth.principal_id, auth.agent_id)  # type: ignore[arg-type]
    if m is None:
        raise NotFound("No active mandate")
    return {
        "mandate": mandate_to_out(m).model_dump(),
        "usage": compute_usage(db, m).model_dump(),
    }


@router.post("/payment-intents", response_model=PaymentIntentOut)
def create_payment_intent(
    body: PaymentIntentRequest,
    response: Response,
    auth: AuthContext = Depends(require_agent),
    db: Session = Depends(get_db),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
):
    if not idempotency_key or not (8 <= len(idempotency_key) <= 64):
        raise ValidationFailed("Idempotency-Key header required (8-64 chars)")
    if not body.payee_id and not body.destination:
        raise ValidationFailed("payee_id or destination required")

    now = utc_now()
    body_hash = _request_body_hash(body)

    existing = (
        db.query(IdempotencyKey)
        .filter(IdempotencyKey.agent_id == auth.agent_id, IdempotencyKey.key == idempotency_key)
        .one_or_none()
    )
    if existing:
        if existing.request_hash != body_hash:
            raise Conflict("Idempotency key reused with different body", code="IDEMPOTENCY_CONFLICT")
        pi = db.query(PaymentIntent).filter(PaymentIntent.intent_id == existing.intent_id).one()
        response.status_code = 200
        return intent_to_out(pi)

    lock_principal(db, auth.principal_id)  # type: ignore[arg-type]

    expires_at = parse_ts(body.expires_at) if body.expires_at else add_seconds(now, 900)
    ks = db.query(KillSwitch).filter(KillSwitch.principal_id == auth.principal_id).one_or_none()
    m = active_mandate_for_agent(db, auth.principal_id, auth.agent_id)  # type: ignore[arg-type]
    mv = build_mandate_view(db, m, now) if m else None

    claimed_dest = None
    if body.destination:
        claimed_dest = DestinationView(
            bank_code=body.destination.bank_code,
            account_number=body.destination.account_number,
            account_name=body.destination.account_name,
        )

    wallet = get_wallet(db, auth.principal_id)  # type: ignore[arg-type]
    registry = payee_registry(db)

    # Resolve payee early for history (policy also resolves)
    from app.policy import resolve_payee

    resolved_guess, _ = resolve_payee(body.payee_id, claimed_dest, registry)
    hist: list[int] = []
    if resolved_guess and m:
        hist = payee_history_amounts(
            db,
            principal_id=auth.principal_id,  # type: ignore[arg-type]
            payee_id=resolved_guess,
            limit=m.body["ask_rules"]["anomaly"]["history_count"],
        )

    result = decide(
        PolicyInput(
            now=now,
            kill_switch_active=bool(ks and ks.active),
            mandate=mv,
            amount_minor=body.amount.amount_minor,
            currency=body.amount.currency,
            claimed_payee_id=body.payee_id,
            claimed_destination=claimed_dest,
            payees=registry,
            intent_expires_at=expires_at,
            wallet_balance_minor=wallet.balance_minor,
            payee_history_amounts=hist,
            block_rules_only=False,
        )
    )

    intent_id = new_intent_id()
    bound = {
        "mandate_id": m.mandate_id if m else None,
        "payee_id": result.resolved_payee_id,
        "amount_minor": body.amount.amount_minor,
        "currency": body.amount.currency,
        "reference": body.reference,
        "expires_at": format_ts(expires_at),
    }
    ih = intent_hash(bound)

    if result.decision == "allow":
        status = "executed"
    elif result.decision == "ask":
        status = "pending_approval"
    else:
        status = "blocked"

    dest_dict = body.destination.model_dump() if body.destination else None
    intent = PaymentIntent(
        intent_id=intent_id,
        principal_id=auth.principal_id,  # type: ignore[arg-type]
        agent_id=auth.agent_id,  # type: ignore[arg-type]
        mandate_id=m.mandate_id if m else None,
        payee_id=result.resolved_payee_id,
        destination=dest_dict,
        amount_minor=body.amount.amount_minor,
        currency=body.amount.currency,
        reference=body.reference,
        description=body.description,
        expires_at=expires_at,
        intent_hash=ih,
        decision=result.decision,
        reasons=[r.to_dict() for r in result.reasons],
        status=status,
        approval_id=None,
        ledger_entry_id=None,
        hold_id=None,
        failure=None,
        created_at=now,
        decided_at=now,
        executed_at=None,
        counts_toward_caps=True,
    )
    db.add(intent)
    db.flush()

    write_audit(
        db,
        event_type="intent.decided",
        principal_id=auth.principal_id,  # type: ignore[arg-type]
        actor={"type": "agent", "id": auth.agent_id},
        subject={"type": "intent", "id": intent_id},
        data={
            "intent_id": intent_id,
            "decision": result.decision,
            "status": status,
            "reason_codes": [r.code for r in result.reasons],
            "amount_minor": body.amount.amount_minor,
            "currency": body.amount.currency,
            "payee_id": result.resolved_payee_id,
            "reference": body.reference,
        },
        ts=now,
    )

    # Quarantine: count blocks after decision
    if result.decision == "block" and m is not None:
        qcfg = m.body["quarantine"]
        blocked_count = count_recent_blocks(
            db,
            agent_id=auth.agent_id,  # type: ignore[arg-type]
            principal_id=auth.principal_id,  # type: ignore[arg-type]
            window_seconds=int(qcfg["window_seconds"]),
            since_release=m.quarantine_released_at,
            now=now,
        )
        # inclusive of this intent (already flushed)
        if blocked_count >= int(qcfg["blocked_attempts"]) and not m.quarantined:
            m.quarantined = True
            write_audit(
                db,
                event_type="quarantine.entered",
                principal_id=auth.principal_id,  # type: ignore[arg-type]
                actor={"type": "system", "id": "gateway"},
                subject={"type": "mandate", "id": m.mandate_id},
                data={"mandate_id": m.mandate_id, "blocked_count": blocked_count},
                ts=now,
            )

    if result.decision == "allow":
        _execute_allow(db, intent=intent, now=now)
    elif result.decision == "ask":
        assert m is not None
        approval_id = new_approval_id()
        ttl = int(m.body["ask_rules"]["approval_ttl_seconds"])
        appr_expires = min(add_seconds(now, ttl), expires_at)
        usage = compute_usage(db, m, now)
        payee_name = None
        payee_verified = False
        if result.resolved_payee_id:
            p = db.query(Payee).filter(Payee.payee_id == result.resolved_payee_id).one_or_none()
            if p:
                payee_name = p.name
                payee_verified = p.verified
        summary = {
            "payee_name": payee_name,
            "payee_verified": payee_verified,
            "reasons": [r.to_dict() for r in result.reasons],
            "windows": [w.model_dump() for w in usage.windows],
        }
        approval = Approval(
            approval_id=approval_id,
            intent_id=intent_id,
            principal_id=auth.principal_id,  # type: ignore[arg-type]
            intent_hash=ih,
            bound=bound,
            summary=summary,
            agent_description=body.description,
            status="pending",
            expires_at=appr_expires,
            created_at=now,
            decided_at=None,
        )
        db.add(approval)
        intent.approval_id = approval_id
        write_audit(
            db,
            event_type="approval.requested",
            principal_id=auth.principal_id,  # type: ignore[arg-type]
            actor={"type": "agent", "id": auth.agent_id},
            subject={"type": "approval", "id": approval_id},
            data={
                "approval_id": approval_id,
                "intent_id": intent_id,
                "expires_at": format_ts(appr_expires),
            },
            ts=now,
        )

    db.add(
        IdempotencyKey(
            agent_id=auth.agent_id,  # type: ignore[arg-type]
            key=idempotency_key,
            request_hash=body_hash,
            intent_id=intent_id,
            created_at=now,
        )
    )
    db.commit()
    db.refresh(intent)
    response.status_code = 201
    return intent_to_out(intent)
