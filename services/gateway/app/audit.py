from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.crypto import canonical_json, sha256_hex
from app.models import AuditLog
from app.timeutil import format_ts

GENESIS_HASH = "0" * 64


def _payload_for_hash(
    seq: int,
    ts: datetime,
    event_type: str,
    principal_id: str,
    actor: dict[str, Any],
    subject: dict[str, Any],
    data: dict[str, Any],
) -> dict[str, Any]:
    return {
        "seq": seq,
        "ts": format_ts(ts),
        "type": event_type,
        "principal_id": principal_id,
        "actor": actor,
        "subject": subject,
        "data": data,
    }


def compute_hash(prev_hash: str, payload: dict[str, Any]) -> str:
    material = prev_hash + canonical_json(payload)
    return sha256_hex(material.encode("utf-8"))


def write_audit(
    db: Session,
    *,
    event_type: str,
    principal_id: str,
    actor: dict[str, Any],
    subject: dict[str, Any],
    data: dict[str, Any],
    ts: datetime,
) -> AuditLog:
    last = db.query(AuditLog).order_by(AuditLog.seq.desc()).first()
    if last is None:
        seq = 1
        prev_hash = GENESIS_HASH
    else:
        seq = last.seq + 1
        prev_hash = last.hash

    payload = _payload_for_hash(seq, ts, event_type, principal_id, actor, subject, data)
    entry_hash = compute_hash(prev_hash, payload)
    row = AuditLog(
        seq=seq,
        ts=ts,
        type=event_type,
        principal_id=principal_id,
        actor=actor,
        subject=subject,
        data=data,
        prev_hash=prev_hash,
        hash=entry_hash,
    )
    db.add(row)
    db.flush()
    return row


def verify_chain(db: Session) -> dict[str, Any]:
    rows = db.query(AuditLog).order_by(AuditLog.seq.asc()).all()
    if not rows:
        return {
            "ok": True,
            "entries_checked": 0,
            "head_hash": GENESIS_HASH,
            "first_bad_seq": None,
        }

    prev_hash = GENESIS_HASH
    expected_seq = 1
    for row in rows:
        if row.seq != expected_seq:
            return {
                "ok": False,
                "entries_checked": expected_seq - 1,
                "head_hash": prev_hash if expected_seq > 1 else GENESIS_HASH,
                "first_bad_seq": row.seq,
            }
        if row.prev_hash != prev_hash:
            return {
                "ok": False,
                "entries_checked": expected_seq - 1,
                "head_hash": prev_hash,
                "first_bad_seq": row.seq,
            }
        payload = _payload_for_hash(
            row.seq, row.ts, row.type, row.principal_id, row.actor, row.subject, row.data
        )
        expected = compute_hash(prev_hash, payload)
        if row.hash != expected:
            return {
                "ok": False,
                "entries_checked": expected_seq - 1,
                "head_hash": prev_hash,
                "first_bad_seq": row.seq,
            }
        prev_hash = row.hash
        expected_seq += 1

    return {
        "ok": True,
        "entries_checked": len(rows),
        "head_hash": rows[-1].hash,
        "first_bad_seq": None,
    }


def next_seq(db: Session) -> int:
    val = db.query(func.coalesce(func.max(AuditLog.seq), 0)).scalar()
    return int(val or 0) + 1
