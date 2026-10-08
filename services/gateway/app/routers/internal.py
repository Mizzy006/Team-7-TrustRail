from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.audit import write_audit
from app.auth import AuthContext, require_service
from app.db import get_db
from app.errors import NotFound
from app.helpers import intent_to_out, ledger_to_out, lock_principal
from app.models import Hold, PaymentIntent
from app.rail import settle_hold
from app.schemas import SettleHoldRequest, SettleHoldResponse
from app.timeutil import utc_now

router = APIRouter(prefix="/internal/v1", tags=["Internal"])


@router.get("/intents/{intent_id}")
def get_intent_internal(
    intent_id: str,
    auth: AuthContext = Depends(require_service),
    db: Session = Depends(get_db),
):
    pi = db.query(PaymentIntent).filter(PaymentIntent.intent_id == intent_id).one_or_none()
    if pi is None:
        raise NotFound("Intent not found")
    return intent_to_out(pi)


@router.post("/holds/{hold_id}/settle", response_model=SettleHoldResponse)
def settle_hold_endpoint(
    hold_id: str,
    body: SettleHoldRequest,
    auth: AuthContext = Depends(require_service),
    db: Session = Depends(get_db),
):
    now = utc_now()
    hold = db.query(Hold).filter(Hold.hold_id == hold_id).one_or_none()
    if hold is None:
        raise NotFound("Hold not found")
    lock_principal(db, hold.principal_id)

    entries = settle_hold(
        db,
        hold_id=hold_id,
        release_to_payee_id=body.release_to_payee_id,
        release_minor=body.release_minor,
        refund_minor=body.refund_minor,
        ts=now,
    )
    write_audit(
        db,
        event_type="hold.settled",
        principal_id=hold.principal_id,
        actor={"type": "service", "id": auth.service_name or "market"},
        subject={"type": "hold", "id": hold_id},
        data={
            "hold_id": hold_id,
            "released_minor": body.release_minor,
            "refunded_minor": body.refund_minor,
            "payee_id": body.release_to_payee_id,
        },
        ts=now,
    )
    db.commit()
    return SettleHoldResponse(
        hold_id=hold_id,
        entries=[ledger_to_out(e) for e in entries],
    )
