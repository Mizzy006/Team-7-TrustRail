from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.audit import verify_chain, write_audit
from app.auth import AuthContext, require_owner, require_owner_or_agent
from app.crypto import content_hash, key_id_from_public_key_b64url, verify_signature_over_obj
from app.db import get_db
from app.errors import Conflict, NotFound, ValidationFailed
from app.helpers import (
    active_mandate_for_agent,
    approval_to_out,
    build_mandate_view,
    compute_usage,
    intent_to_out,
    key_to_out,
    kill_to_out,
    ledger_to_out,
    lock_principal,
    mandate_to_out,
    payee_history_amounts,
    payee_registry,
    validate_and_check_mandate_semantics,
    verify_mandate_signature,
)
from app.ids import new_hold_id  # noqa: F401 — kept for symmetry
from app.models import (
    Account,
    Approval,
    AuditLog,
    KillSwitch,
    LedgerEntry,
    Mandate,
    OwnerKey,
    Payee,
    PaymentIntent,
    Principal,
)
from app.policy import DestinationView, PolicyInput, decide
from app.rail import get_payee_account, get_wallet, hold_funds, transfer
from app.config import get_settings
from app.schemas import (
    ApprovalDecisionRequest,
    ApprovalOut,
    KillSwitchOut,
    KillSwitchSet,
    MandateRecordOut,
    MeOut,
    OwnerKeyOut,
    PayeeOut,
    Destination,
    RegisterKeyRequest,
    SignedMandateIn,
    UsageOut,
)
from app.timeutil import format_ts, parse_ts, utc_now

router = APIRouter(prefix="/v1", tags=["Owner"])


@router.get("/me", response_model=MeOut)
def get_me(auth: AuthContext = Depends(require_owner), db: Session = Depends(get_db)):
    principal = db.query(Principal).filter(Principal.principal_id == auth.principal_id).one()
    keys = (
        db.query(OwnerKey)
        .filter(OwnerKey.principal_id == auth.principal_id)
        .order_by(OwnerKey.created_at.asc())
        .all()
    )
    ks = db.query(KillSwitch).filter(KillSwitch.principal_id == auth.principal_id).one_or_none()
    return MeOut(
        principal_id=principal.principal_id,
        display_name=principal.display_name,
        server_time=format_ts(utc_now()),
        keys=[key_to_out(k) for k in keys],
        kill_switch=kill_to_out(ks),
    )


@router.post("/keys", response_model=OwnerKeyOut)
def register_key(
    body: RegisterKeyRequest,
    auth: AuthContext = Depends(require_owner),
    db: Session = Depends(get_db),
):
    now = utc_now()
    key_id = key_id_from_public_key_b64url(body.public_key)
    existing = db.query(OwnerKey).filter(OwnerKey.key_id == key_id).one_or_none()
    if existing:
        if existing.principal_id != auth.principal_id:
            raise Conflict("key_id already registered to another principal")
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=200, content=key_to_out(existing).model_dump())

    row = OwnerKey(
        key_id=key_id,
        principal_id=auth.principal_id,  # type: ignore[arg-type]
        public_key=body.public_key,
        label=body.label,
        created_at=now,
    )
    db.add(row)
    write_audit(
        db,
        event_type="key.registered",
        principal_id=auth.principal_id,  # type: ignore[arg-type]
        actor={"type": "owner", "id": auth.principal_id},
        subject={"type": "key", "id": key_id},
        data={"key_id": key_id},
        ts=now,
    )
    db.commit()
    db.refresh(row)
    from fastapi.responses import JSONResponse

    return JSONResponse(status_code=201, content=key_to_out(row).model_dump())


@router.get("/payees")
def list_payees(auth: AuthContext = Depends(require_owner), db: Session = Depends(get_db)):
    items = []
    for p in db.query(Payee).order_by(Payee.payee_id.asc()).all():
        items.append(
            PayeeOut(
                payee_id=p.payee_id,
                name=p.name,
                kind=p.kind,
                verified=p.verified,
                destination=Destination(
                    bank_code=p.bank_code,
                    account_number=p.account_number,
                    account_name=p.account_name,
                ),
            ).model_dump()
        )
    return {"items": items}


@router.get("/mandates")
def list_mandates(auth: AuthContext = Depends(require_owner), db: Session = Depends(get_db)):
    rows = (
        db.query(Mandate)
        .filter(Mandate.principal_id == auth.principal_id)
        .order_by(Mandate.created_at.desc())
        .all()
    )
    return {"items": [mandate_to_out(m).model_dump() for m in rows]}


@router.post("/mandates", response_model=MandateRecordOut, status_code=201)
def create_mandate(
    body: SignedMandateIn,
    auth: AuthContext = Depends(require_owner),
    db: Session = Depends(get_db),
):
    now = utc_now()
    lock_principal(db, auth.principal_id)  # type: ignore[arg-type]
    mandate = body.mandate
    validate_and_check_mandate_semantics(
        db, mandate=mandate, principal_id=auth.principal_id, now=now  # type: ignore[arg-type]
    )
    verify_mandate_signature(db, mandate, body.signature.model_dump())

    ch = content_hash(mandate)
    active = active_mandate_for_agent(db, auth.principal_id, mandate["agent_id"])  # type: ignore[arg-type]

    row = Mandate(
        mandate_id=mandate["mandate_id"],
        principal_id=mandate["principal_id"],
        agent_id=mandate["agent_id"],
        key_id=mandate["key_id"],
        body=mandate,
        signature=body.signature.model_dump(),
        content_hash=ch,
        status="active",
        quarantined=False,
        quarantine_released_at=None,
        superseded_by=None,
        created_at=now,
        valid_from=parse_ts(mandate["valid_from"]),
        valid_until=parse_ts(mandate["valid_until"]),
    )
    if active is not None:
        active.status = "superseded"
        active.superseded_by = mandate["mandate_id"]
        write_audit(
            db,
            event_type="mandate.superseded",
            principal_id=auth.principal_id,  # type: ignore[arg-type]
            actor={"type": "owner", "id": auth.principal_id},
            subject={"type": "mandate", "id": active.mandate_id},
            data={"mandate_id": active.mandate_id, "superseded_by": mandate["mandate_id"]},
            ts=now,
        )
    db.add(row)
    write_audit(
        db,
        event_type="mandate.created",
        principal_id=auth.principal_id,  # type: ignore[arg-type]
        actor={"type": "owner", "id": auth.principal_id},
        subject={"type": "mandate", "id": mandate["mandate_id"]},
        data={
            "mandate_id": mandate["mandate_id"],
            "content_hash": ch,
            "supersedes": mandate.get("supersedes"),
        },
        ts=now,
    )
    db.commit()
    db.refresh(row)
    return mandate_to_out(row)


@router.get("/mandates/{mandate_id}", response_model=MandateRecordOut)
def get_mandate(
    mandate_id: str,
    auth: AuthContext = Depends(require_owner),
    db: Session = Depends(get_db),
):
    m = (
        db.query(Mandate)
        .filter(Mandate.mandate_id == mandate_id, Mandate.principal_id == auth.principal_id)
        .one_or_none()
    )
    if m is None:
        raise NotFound("Mandate not found")
    return mandate_to_out(m)


@router.post("/mandates/{mandate_id}/revoke", response_model=MandateRecordOut)
def revoke_mandate(
    mandate_id: str,
    auth: AuthContext = Depends(require_owner),
    db: Session = Depends(get_db),
):
    now = utc_now()
    lock_principal(db, auth.principal_id)  # type: ignore[arg-type]
    m = (
        db.query(Mandate)
        .filter(Mandate.mandate_id == mandate_id, Mandate.principal_id == auth.principal_id)
        .one_or_none()
    )
    if m is None:
        raise NotFound("Mandate not found")
    if m.status != "active":
        raise Conflict(f"Mandate is {m.status}")
    m.status = "revoked"
    write_audit(
        db,
        event_type="mandate.revoked",
        principal_id=auth.principal_id,  # type: ignore[arg-type]
        actor={"type": "owner", "id": auth.principal_id},
        subject={"type": "mandate", "id": mandate_id},
        data={"mandate_id": mandate_id},
        ts=now,
    )
    db.commit()
    return mandate_to_out(m)


@router.get("/mandates/{mandate_id}/usage", response_model=UsageOut)
def get_mandate_usage(
    mandate_id: str,
    auth: AuthContext = Depends(require_owner),
    db: Session = Depends(get_db),
):
    m = (
        db.query(Mandate)
        .filter(Mandate.mandate_id == mandate_id, Mandate.principal_id == auth.principal_id)
        .one_or_none()
    )
    if m is None:
        raise NotFound("Mandate not found")
    return compute_usage(db, m)


@router.post("/mandates/{mandate_id}/release-quarantine", response_model=MandateRecordOut)
def release_quarantine(
    mandate_id: str,
    auth: AuthContext = Depends(require_owner),
    db: Session = Depends(get_db),
):
    now = utc_now()
    lock_principal(db, auth.principal_id)  # type: ignore[arg-type]
    m = (
        db.query(Mandate)
        .filter(Mandate.mandate_id == mandate_id, Mandate.principal_id == auth.principal_id)
        .one_or_none()
    )
    if m is None:
        raise NotFound("Mandate not found")
    m.quarantined = False
    m.quarantine_released_at = now
    write_audit(
        db,
        event_type="quarantine.released",
        principal_id=auth.principal_id,  # type: ignore[arg-type]
        actor={"type": "owner", "id": auth.principal_id},
        subject={"type": "mandate", "id": mandate_id},
        data={"mandate_id": mandate_id},
        ts=now,
    )
    db.commit()
    return mandate_to_out(m)


@router.get("/payment-intents")
def list_payment_intents(
    status: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    auth: AuthContext = Depends(require_owner),
    db: Session = Depends(get_db),
):
    q = db.query(PaymentIntent).filter(PaymentIntent.principal_id == auth.principal_id)
    if status:
        q = q.filter(PaymentIntent.status == status)
    rows = q.order_by(PaymentIntent.created_at.desc()).limit(limit).all()
    return {"items": [intent_to_out(r).model_dump() for r in rows]}


@router.get("/payment-intents/{intent_id}")
def get_payment_intent_owner(
    intent_id: str,
    auth: AuthContext = Depends(require_owner_or_agent),
    db: Session = Depends(get_db),
):
    pi = db.query(PaymentIntent).filter(PaymentIntent.intent_id == intent_id).one_or_none()
    if pi is None:
        raise NotFound("Intent not found")
    if auth.kind == "owner":
        if pi.principal_id != auth.principal_id:
            raise NotFound("Intent not found")
    else:
        if pi.agent_id != auth.agent_id:
            raise NotFound("Intent not found")
    return intent_to_out(pi)


@router.get("/approvals")
def list_approvals(
    status: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    auth: AuthContext = Depends(require_owner),
    db: Session = Depends(get_db),
):
    now = utc_now()
    # Expire pending approvals past TTL
    pending = (
        db.query(Approval)
        .filter(Approval.principal_id == auth.principal_id, Approval.status == "pending")
        .all()
    )
    for a in pending:
        if a.expires_at < now:
            a.status = "expired"
            intent = db.query(PaymentIntent).filter(PaymentIntent.intent_id == a.intent_id).one_or_none()
            if intent and intent.status == "pending_approval":
                intent.status = "expired"
    db.commit()

    q = db.query(Approval).filter(Approval.principal_id == auth.principal_id)
    if status:
        q = q.filter(Approval.status == status)
    rows = q.order_by(Approval.created_at.desc()).limit(limit).all()
    return {"items": [approval_to_out(a).model_dump() for a in rows]}


@router.get("/approvals/{approval_id}", response_model=ApprovalOut)
def get_approval(
    approval_id: str,
    auth: AuthContext = Depends(require_owner),
    db: Session = Depends(get_db),
):
    a = (
        db.query(Approval)
        .filter(Approval.approval_id == approval_id, Approval.principal_id == auth.principal_id)
        .one_or_none()
    )
    if a is None:
        raise NotFound("Approval not found")
    now = utc_now()
    if a.status == "pending" and a.expires_at < now:
        a.status = "expired"
        intent = db.query(PaymentIntent).filter(PaymentIntent.intent_id == a.intent_id).one_or_none()
        if intent and intent.status == "pending_approval":
            intent.status = "expired"
        db.commit()
    return approval_to_out(a)


def _execute_payment(
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
        write_audit(
            db,
            event_type="payment.executed",
            principal_id=intent.principal_id,
            actor={"type": "system", "id": "gateway"},
            subject={"type": "intent", "id": intent.intent_id},
            data={
                "intent_id": intent.intent_id,
                "ledger_entry_id": entry.entry_id,
                "hold_id": hold.hold_id,
            },
            ts=now,
        )
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
        write_audit(
            db,
            event_type="payment.executed",
            principal_id=intent.principal_id,
            actor={"type": "system", "id": "gateway"},
            subject={"type": "intent", "id": intent.intent_id},
            data={
                "intent_id": intent.intent_id,
                "ledger_entry_id": entry.entry_id,
                "hold_id": None,
            },
            ts=now,
        )
    intent.status = "executed"
    intent.executed_at = now


@router.post("/approvals/{approval_id}/decision")
def decide_approval(
    approval_id: str,
    body: ApprovalDecisionRequest,
    auth: AuthContext = Depends(require_owner),
    db: Session = Depends(get_db),
):
    now = utc_now()
    lock_principal(db, auth.principal_id)  # type: ignore[arg-type]
    approval = (
        db.query(Approval)
        .filter(Approval.approval_id == approval_id, Approval.principal_id == auth.principal_id)
        .with_for_update()
        .one_or_none()
    )
    if approval is None:
        raise NotFound("Approval not found")
    if approval.status != "pending" or approval.expires_at < now:
        if approval.status == "pending" and approval.expires_at < now:
            approval.status = "expired"
            intent = db.query(PaymentIntent).filter(PaymentIntent.intent_id == approval.intent_id).one()
            intent.status = "expired"
            db.commit()
        raise Conflict("Approval is not pending", code="APPROVAL_NOT_PENDING")

    stmt = body.statement
    if stmt.approval_id != approval.approval_id or stmt.intent_id != approval.intent_id:
        raise ValidationFailed("Statement does not match approval", code="APPROVAL_MISMATCH")
    if stmt.intent_hash != approval.intent_hash:
        raise ValidationFailed("intent_hash mismatch", code="APPROVAL_MISMATCH")

    intent = (
        db.query(PaymentIntent)
        .filter(PaymentIntent.intent_id == approval.intent_id)
        .with_for_update()
        .one()
    )

    if stmt.decision == "deny":
        approval.status = "denied"
        approval.decided_at = now
        intent.status = "denied"
        write_audit(
            db,
            event_type="approval.resolved",
            principal_id=auth.principal_id,  # type: ignore[arg-type]
            actor={"type": "owner", "id": auth.principal_id},
            subject={"type": "approval", "id": approval_id},
            data={
                "approval_id": approval_id,
                "intent_id": intent.intent_id,
                "outcome": "denied",
                "intent_status": "denied",
            },
            ts=now,
        )
        db.commit()
        return {"approval": approval_to_out(approval).model_dump(), "intent": intent_to_out(intent).model_dump()}

    # approve
    if body.signature is None:
        raise ValidationFailed("signature required for approve")
    if stmt.decision != "approve":
        raise ValidationFailed("Invalid decision")

    key = (
        db.query(OwnerKey)
        .filter(
            OwnerKey.key_id == body.signature.key_id,
            OwnerKey.principal_id == auth.principal_id,
        )
        .one_or_none()
    )
    if key is None:
        raise ValidationFailed("Unknown signing key", code="SIGNATURE_INVALID")
    if not verify_signature_over_obj(key.public_key, stmt.model_dump(), body.signature.value):
        raise ValidationFailed("Approval signature invalid", code="SIGNATURE_INVALID")

    # Consume approval (single-use) even if recheck fails
    approval.status = "approved"
    approval.decided_at = now

    # Re-run BLOCK rules 1-8 only
    ks = db.query(KillSwitch).filter(KillSwitch.principal_id == auth.principal_id).one_or_none()
    m = None
    mv = None
    if intent.mandate_id:
        m = db.query(Mandate).filter(Mandate.mandate_id == intent.mandate_id).one_or_none()
        if m and m.status == "active":
            mv = build_mandate_view(db, m, now)

    claimed_dest = None
    if intent.destination:
        claimed_dest = DestinationView(**intent.destination)

    result = decide(
        PolicyInput(
            now=now,
            kill_switch_active=bool(ks and ks.active),
            mandate=mv,
            amount_minor=intent.amount_minor,
            currency=intent.currency,
            claimed_payee_id=intent.payee_id,
            claimed_destination=claimed_dest,
            payees=payee_registry(db),
            intent_expires_at=intent.expires_at,
            wallet_balance_minor=get_wallet(db, intent.principal_id).balance_minor,
            payee_history_amounts=[],
            block_rules_only=True,
        )
    )

    if result.decision == "block":
        fail = result.reasons[0].to_dict()
        intent.status = "failed"
        intent.failure = fail
        write_audit(
            db,
            event_type="payment.failed",
            principal_id=intent.principal_id,
            actor={"type": "system", "id": "gateway"},
            subject={"type": "intent", "id": intent.intent_id},
            data={"intent_id": intent.intent_id, "code": fail["code"]},
            ts=now,
        )
        write_audit(
            db,
            event_type="approval.resolved",
            principal_id=auth.principal_id,  # type: ignore[arg-type]
            actor={"type": "owner", "id": auth.principal_id},
            subject={"type": "approval", "id": approval_id},
            data={
                "approval_id": approval_id,
                "intent_id": intent.intent_id,
                "outcome": "approved",
                "intent_status": "failed",
            },
            ts=now,
        )
        db.commit()
        return {"approval": approval_to_out(approval).model_dump(), "intent": intent_to_out(intent).model_dump()}

    _execute_payment(db, intent=intent, now=now)
    write_audit(
        db,
        event_type="approval.resolved",
        principal_id=auth.principal_id,  # type: ignore[arg-type]
        actor={"type": "owner", "id": auth.principal_id},
        subject={"type": "approval", "id": approval_id},
        data={
            "approval_id": approval_id,
            "intent_id": intent.intent_id,
            "outcome": "approved",
            "intent_status": "executed",
        },
        ts=now,
    )
    db.commit()
    return {"approval": approval_to_out(approval).model_dump(), "intent": intent_to_out(intent).model_dump()}


@router.get("/kill-switch", response_model=KillSwitchOut)
def get_kill_switch(auth: AuthContext = Depends(require_owner), db: Session = Depends(get_db)):
    ks = db.query(KillSwitch).filter(KillSwitch.principal_id == auth.principal_id).one_or_none()
    return kill_to_out(ks)


@router.put("/kill-switch", response_model=KillSwitchOut)
def set_kill_switch(
    body: KillSwitchSet,
    auth: AuthContext = Depends(require_owner),
    db: Session = Depends(get_db),
):
    now = utc_now()
    lock_principal(db, auth.principal_id)  # type: ignore[arg-type]
    ks = db.query(KillSwitch).filter(KillSwitch.principal_id == auth.principal_id).one_or_none()
    if ks is None:
        ks = KillSwitch(principal_id=auth.principal_id, active=False)  # type: ignore[arg-type]
        db.add(ks)
    ks.active = body.active
    ks.reason = body.reason
    ks.changed_at = now
    write_audit(
        db,
        event_type="kill_switch.changed",
        principal_id=auth.principal_id,  # type: ignore[arg-type]
        actor={"type": "owner", "id": auth.principal_id},
        subject={"type": "kill_switch", "id": auth.principal_id},
        data={"active": body.active, "reason": body.reason},
        ts=now,
    )
    db.commit()
    return kill_to_out(ks)


@router.get("/audit")
def list_audit(
    after_seq: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    newest: bool = Query(False),
    auth: AuthContext = Depends(require_owner),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(AuditLog)
        .filter(AuditLog.principal_id == auth.principal_id, AuditLog.seq > after_seq)
        .order_by(AuditLog.seq.desc() if newest else AuditLog.seq.asc())
        .limit(limit)
        .all()
    )
    items = []
    next_after = after_seq
    for r in rows:
        items.append(
            {
                "seq": r.seq,
                "ts": format_ts(r.ts),
                "type": r.type,
                "principal_id": r.principal_id,
                "actor": r.actor,
                "subject": r.subject,
                "data": r.data,
                "prev_hash": r.prev_hash,
                "hash": r.hash,
            }
        )
        next_after = r.seq
    return {"items": items, "next_after_seq": next_after}


@router.get("/audit/verify")
def verify_audit(auth: AuthContext = Depends(require_owner), db: Session = Depends(get_db)):
    return verify_chain(db)


@router.get("/accounts")
def list_accounts(auth: AuthContext = Depends(require_owner), db: Session = Depends(get_db)):
    rows = db.query(Account).order_by(Account.account_id.asc()).all()
    items = [
        {
            "account_id": a.account_id,
            "type": a.type,
            "owner_id": a.owner_id,
            "balance": {"amount_minor": a.balance_minor, "currency": a.currency},
        }
        for a in rows
    ]
    return {"items": items}


@router.get("/ledger")
def list_ledger(
    limit: int = Query(50, ge=1, le=200),
    auth: AuthContext = Depends(require_owner),
    db: Session = Depends(get_db),
):
    rows = db.query(LedgerEntry).order_by(LedgerEntry.created_at.desc()).limit(limit).all()
    return {"items": [ledger_to_out(e).model_dump() for e in rows]}
