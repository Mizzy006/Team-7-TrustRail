from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import jsonschema
from sqlalchemy.orm import Session

from app.config import get_settings
from app.crypto import content_hash, intent_hash, key_id_from_public_key_b64url, verify_signature_over_obj
from app.errors import Conflict, NotFound, ValidationFailed
from app.models import Account, KillSwitch, Mandate, OwnerKey, Payee, PaymentIntent, Principal
from app.policy import MandateView, PayeeView, WindowView, DestinationView, mandate_view_from_body
from app.schemas import (
    ApprovalOut,
    Destination,
    KillSwitchOut,
    LedgerEntryOut,
    MandateRecordOut,
    Money,
    OwnerKeyOut,
    PaymentIntentOut,
    ReasonOut,
    UsageOut,
    UsageWindowOut,
)
from app.timeutil import format_ts, parse_ts, utc_now

_mandate_schema: dict[str, Any] | None = None


def get_mandate_schema() -> dict[str, Any]:
    global _mandate_schema
    if _mandate_schema is None:
        path = get_settings().mandate_schema_path
        with open(path, encoding="utf-8") as f:
            _mandate_schema = json.load(f)
    return _mandate_schema


def lock_principal(db: Session, principal_id: str) -> Principal:
    row = (
        db.query(Principal)
        .filter(Principal.principal_id == principal_id)
        .with_for_update()
        .one_or_none()
    )
    if row is None:
        raise NotFound("Principal not found")
    return row


def mandate_effective_status(m: Mandate, now: datetime | None = None) -> str:
    now = now or utc_now()
    if m.status == "active" and now > m.valid_until:
        return "expired"
    return m.status


def mandate_to_out(m: Mandate, now: datetime | None = None) -> MandateRecordOut:
    return MandateRecordOut(
        mandate=m.body,
        signature=m.signature,
        content_hash=m.content_hash,
        status=mandate_effective_status(m, now),
        quarantined=m.quarantined,
        superseded_by=m.superseded_by,
        created_at=format_ts(m.created_at),
    )


def key_to_out(k: OwnerKey) -> OwnerKeyOut:
    return OwnerKeyOut(
        key_id=k.key_id,
        principal_id=k.principal_id,
        public_key=k.public_key,
        label=k.label,
        created_at=format_ts(k.created_at),
    )


def kill_to_out(ks: KillSwitch | None) -> KillSwitchOut:
    if ks is None:
        return KillSwitchOut(active=False, reason=None, changed_at=None)
    return KillSwitchOut(
        active=ks.active,
        reason=ks.reason,
        changed_at=format_ts(ks.changed_at) if ks.changed_at else None,
    )


def intent_to_out(pi: PaymentIntent) -> PaymentIntentOut:
    dest = None
    if pi.destination:
        dest = Destination(**pi.destination)
    failure = None
    if pi.failure:
        failure = ReasonOut(**pi.failure)
    return PaymentIntentOut(
        intent_id=pi.intent_id,
        mandate_id=pi.mandate_id,
        agent_id=pi.agent_id,
        payee_id=pi.payee_id,
        destination=dest,
        amount=Money(amount_minor=pi.amount_minor, currency=pi.currency),
        reference=pi.reference,
        description=pi.description,
        expires_at=format_ts(pi.expires_at),
        intent_hash=pi.intent_hash,
        decision=pi.decision,
        reasons=[ReasonOut(**r) for r in (pi.reasons or [])],
        status=pi.status,
        approval_id=pi.approval_id,
        ledger_entry_id=pi.ledger_entry_id,
        hold_id=pi.hold_id,
        failure=failure,
        created_at=format_ts(pi.created_at),
        decided_at=format_ts(pi.decided_at),
        executed_at=format_ts(pi.executed_at) if pi.executed_at else None,
    )


def ledger_to_out(e) -> LedgerEntryOut:
    return LedgerEntryOut(
        entry_id=e.entry_id,
        kind=e.kind,
        from_account=e.from_account,
        to_account=e.to_account,
        amount=Money(amount_minor=e.amount_minor, currency=e.currency),
        intent_id=e.intent_id,
        hold_id=e.hold_id,
        created_at=format_ts(e.created_at),
    )


def approval_to_out(a) -> ApprovalOut:
    return ApprovalOut(
        approval_id=a.approval_id,
        intent_id=a.intent_id,
        status=a.status,
        intent_hash=a.intent_hash,
        bound=a.bound,
        summary=a.summary,
        agent_description=a.agent_description,
        expires_at=format_ts(a.expires_at),
        created_at=format_ts(a.created_at),
        decided_at=format_ts(a.decided_at) if a.decided_at else None,
    )


def payee_registry(db: Session) -> dict[str, PayeeView]:
    out: dict[str, PayeeView] = {}
    for p in db.query(Payee).all():
        out[p.payee_id] = PayeeView(
            payee_id=p.payee_id,
            name=p.name,
            verified=p.verified,
            kind=p.kind,
            destination=DestinationView(
                bank_code=p.bank_code,
                account_number=p.account_number,
                account_name=p.account_name,
            ),
        )
    return out


def window_spend(
    db: Session,
    *,
    principal_id: str,
    agent_id: str,
    window_seconds: int,
    now: datetime,
) -> int:
    since = now - timedelta(seconds=window_seconds)
    rows = (
        db.query(PaymentIntent)
        .filter(
            PaymentIntent.principal_id == principal_id,
            PaymentIntent.agent_id == agent_id,
            PaymentIntent.status == "executed",
            PaymentIntent.counts_toward_caps.is_(True),
            PaymentIntent.executed_at >= since,
        )
        .all()
    )
    return sum(r.amount_minor for r in rows)


def build_window_spend_map(
    db: Session,
    mandate_body: dict[str, Any],
    *,
    principal_id: str,
    agent_id: str,
    now: datetime,
) -> dict[str, int]:
    result: dict[str, int] = {}
    for w in mandate_body["limits"]["windows"]:
        result[w["name"]] = window_spend(
            db,
            principal_id=principal_id,
            agent_id=agent_id,
            window_seconds=int(w["seconds"]),
            now=now,
        )
    return result


def compute_usage(db: Session, m: Mandate, now: datetime | None = None) -> UsageOut:
    now = now or utc_now()
    spend_map = build_window_spend_map(
        db, m.body, principal_id=m.principal_id, agent_id=m.agent_id, now=now
    )
    windows: list[UsageWindowOut] = []
    remaining_list: list[int] = []
    for w in m.body["limits"]["windows"]:
        spent = spend_map[w["name"]]
        rem = max(0, int(w["cap_minor"]) - spent)
        remaining_list.append(rem)
        windows.append(
            UsageWindowOut(
                name=w["name"],
                seconds=int(w["seconds"]),
                cap_minor=int(w["cap_minor"]),
                spent_minor=spent,
                remaining_minor=rem,
            )
        )
    wallet = (
        db.query(Account)
        .filter(Account.owner_id == m.principal_id, Account.type == "wallet")
        .one()
    )
    exposure = min(remaining_list) if remaining_list else 0
    # Exposure is without human: also limited by auto_max conceptually but spec says min(remaining)
    return UsageOut(
        mandate_id=m.mandate_id,
        windows=windows,
        wallet_balance=Money(amount_minor=wallet.balance_minor, currency=wallet.currency),
        exposure_minor=exposure,
        quarantined=m.quarantined,
    )


def payee_history_amounts(
    db: Session,
    *,
    principal_id: str,
    payee_id: str,
    limit: int,
) -> list[int]:
    rows = (
        db.query(PaymentIntent)
        .filter(
            PaymentIntent.principal_id == principal_id,
            PaymentIntent.payee_id == payee_id,
            PaymentIntent.status == "executed",
        )
        .order_by(PaymentIntent.executed_at.desc())
        .limit(limit)
        .all()
    )
    return [r.amount_minor for r in rows]


def active_mandate_for_agent(db: Session, principal_id: str, agent_id: str) -> Mandate | None:
    return (
        db.query(Mandate)
        .filter(
            Mandate.principal_id == principal_id,
            Mandate.agent_id == agent_id,
            Mandate.status == "active",
        )
        .one_or_none()
    )


def validate_and_check_mandate_semantics(
    db: Session,
    *,
    mandate: dict[str, Any],
    principal_id: str,
    now: datetime,
) -> None:
    schema = get_mandate_schema()
    try:
        jsonschema.validate(instance=mandate, schema=schema)
    except jsonschema.ValidationError as e:
        raise ValidationFailed(str(e.message))

    limits = mandate["limits"]["per_txn"]
    if limits["auto_max_minor"] > limits["hard_max_minor"]:
        raise ValidationFailed("auto_max_minor must be <= hard_max_minor")

    issued_at = parse_ts(mandate["issued_at"])
    valid_from = parse_ts(mandate["valid_from"])
    valid_until = parse_ts(mandate["valid_until"])

    if valid_until <= valid_from:
        raise ValidationFailed("valid_until must be > valid_from")
    if (valid_until - valid_from).total_seconds() > 30 * 86400:
        raise ValidationFailed("Mandate span must be at most 30 days")
    if valid_from < issued_at:
        raise ValidationFailed("valid_from must be >= issued_at")
    skew = abs((issued_at - now).total_seconds())
    if skew > 300:
        raise ValidationFailed("issued_at must be within 300s of server time")

    if mandate["principal_id"] != principal_id:
        raise ValidationFailed("principal_id must match authenticated owner")

    from app.models import Agent

    agent = db.query(Agent).filter(Agent.agent_id == mandate["agent_id"]).one_or_none()
    if agent is None or agent.principal_id != principal_id:
        raise ValidationFailed("agent_id does not belong to this principal")

    key = (
        db.query(OwnerKey)
        .filter(OwnerKey.key_id == mandate["key_id"], OwnerKey.principal_id == principal_id)
        .one_or_none()
    )
    if key is None:
        raise ValidationFailed("key_id is not registered to this principal")

    for pid in mandate["payees"]:
        if db.query(Payee).filter(Payee.payee_id == pid).one_or_none() is None:
            raise ValidationFailed(f"Unknown payee {pid}")

    names = [w["name"] for w in mandate["limits"]["windows"]]
    if len(names) != len(set(names)):
        raise ValidationFailed("Window names must be unique")

    if db.query(Mandate).filter(Mandate.mandate_id == mandate["mandate_id"]).one_or_none():
        raise Conflict("mandate_id already used")

    active = active_mandate_for_agent(db, principal_id, mandate["agent_id"])
    supersedes = mandate.get("supersedes")
    if active is not None:
        if supersedes != active.mandate_id:
            raise Conflict("supersedes must name the current active mandate")
    elif supersedes is not None:
        raise Conflict("supersedes set but no active mandate exists")


def verify_mandate_signature(db: Session, mandate: dict[str, Any], signature: dict[str, Any]) -> None:
    if signature.get("alg") != "Ed25519":
        raise ValidationFailed("Unsupported signature algorithm", code="SIGNATURE_INVALID")
    if signature.get("key_id") != mandate.get("key_id"):
        raise ValidationFailed("signature.key_id mismatch", code="SIGNATURE_INVALID")
    key = db.query(OwnerKey).filter(OwnerKey.key_id == mandate["key_id"]).one_or_none()
    if key is None:
        raise ValidationFailed("Unknown signing key", code="SIGNATURE_INVALID")
    if not verify_signature_over_obj(key.public_key, mandate, signature["value"]):
        raise ValidationFailed("Mandate signature invalid", code="SIGNATURE_INVALID")


def count_recent_blocks(
    db: Session,
    *,
    agent_id: str,
    principal_id: str,
    window_seconds: int,
    since_release: datetime | None,
    now: datetime,
) -> int:
    since = now - timedelta(seconds=window_seconds)
    if since_release and since_release > since:
        since = since_release
    return (
        db.query(PaymentIntent)
        .filter(
            PaymentIntent.principal_id == principal_id,
            PaymentIntent.agent_id == agent_id,
            PaymentIntent.decision == "block",
            PaymentIntent.decided_at >= since,
        )
        .count()
    )


def build_mandate_view(db: Session, m: Mandate, now: datetime) -> MandateView:
    spend = build_window_spend_map(
        db, m.body, principal_id=m.principal_id, agent_id=m.agent_id, now=now
    )
    return mandate_view_from_body(
        m.body,
        quarantined=m.quarantined,
        window_spend=spend,
        valid_from=m.valid_from,
        valid_until=m.valid_until,
    )
