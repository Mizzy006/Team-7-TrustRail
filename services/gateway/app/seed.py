from __future__ import annotations

import json
import random
from datetime import timedelta
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app import auth
from app.config import get_settings
from app.crypto import intent_hash
from app.db import Base, engine
from app.ids import new_intent_id, new_ledger_id
from app.models import (
    Account,
    Agent,
    Approval,
    AuditLog,
    Hold,
    IdempotencyKey,
    KillSwitch,
    LedgerEntry,
    Mandate,
    OwnerKey,
    Payee,
    PaymentIntent,
    Principal,
)
from app.timeutil import format_ts, utc_now


def load_seed_file(path: Path | None = None) -> dict[str, Any]:
    settings = get_settings()
    p = path or settings.seed_path
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def wipe_all(db: Session) -> None:
    from sqlalchemy import text

    for table in reversed(Base.metadata.sorted_tables):
        db.execute(table.delete())
    # Reset serial sequences used by audit_log / idempotency_keys
    for seq in ("audit_log_seq_seq", "idempotency_keys_id_seq"):
        try:
            db.execute(text(f"ALTER SEQUENCE IF EXISTS {seq} RESTART WITH 1"))
        except Exception:
            pass
    db.commit()


def reseed(db: Session, seed: dict[str, Any] | None = None) -> None:
    seed = seed or load_seed_file()
    wipe_all(db)
    auth.load_auth_from_seed(seed)
    now = utc_now()
    currency = seed.get("currency", "NGN")

    # Principals from retailer owners
    for persona in seed.get("personas", []):
        if persona.get("role") != "retailer_owner":
            continue
        db.add(
            Principal(
                principal_id=persona["principal_id"],
                display_name=persona.get("display_name", persona["principal_id"]),
                created_at=now,
            )
        )

    for agent in seed.get("agents", []):
        db.add(
            Agent(
                agent_id=agent["agent_id"],
                principal_id=agent["principal_id"],
                token=agent["key"],
                created_at=now,
            )
        )

    for payee in seed.get("payees", []):
        dest = payee["destination"]
        db.add(
            Payee(
                payee_id=payee["payee_id"],
                name=payee["name"],
                kind=payee["kind"],
                verified=bool(payee.get("verified", True)),
                bank_code=dest["bank_code"],
                account_number=dest["account_number"],
                account_name=dest["account_name"],
            )
        )
        acct_type = "escrow" if payee["kind"] == "escrow" else "payee"
        db.add(
            Account(
                account_id=f"acct_{payee['payee_id']}",
                type=acct_type,
                owner_id=payee["payee_id"],
                balance_minor=0,
                currency=currency,
            )
        )

    for acct in seed.get("accounts", []):
        db.add(
            Account(
                account_id=acct["account_id"],
                type=acct["type"],
                owner_id=acct["owner_id"],
                balance_minor=int(acct["balance_minor"]),
                currency=currency,
            )
        )

    for persona in seed.get("personas", []):
        if persona.get("role") != "retailer_owner":
            continue
        db.add(
            KillSwitch(
                principal_id=persona["principal_id"],
                active=False,
                reason=None,
                changed_at=None,
            )
        )

    db.flush()

    # History payments (do NOT count toward caps)
    rng = random.Random(42)
    for hist in seed.get("payee_history", []):
        lo, hi = hist["executed_days_ago_between"]
        principal_id = hist["principal_id"]
        agent_id = seed["agents"][0]["agent_id"]
        payee_id = hist["payee_id"]
        amount = int(hist["amount_minor"])
        for i in range(int(hist["count"])):
            days_ago = rng.randint(int(lo), int(hi))
            executed_at = now - timedelta(days=days_ago, hours=rng.randint(0, 23))
            intent_id = f"pi_hist_{payee_id[-6:]}_{i+1:02d}"
            expires_at = executed_at + timedelta(seconds=900)
            bound = {
                "mandate_id": None,
                "payee_id": payee_id,
                "amount_minor": amount,
                "currency": currency,
                "reference": f"hist_{i+1}",
                "expires_at": format_ts(expires_at),
            }
            ih = intent_hash(bound)
            ledger_id = f"led_hist_{i+1:02d}"
            # Debit wallet / credit payee without changing demo wallet start —
            # history is already "spent"; leave wallet at seeded balance.
            # Record ledger as transfer but do not adjust balances (historical).
            db.add(
                PaymentIntent(
                    intent_id=intent_id,
                    principal_id=principal_id,
                    agent_id=agent_id,
                    mandate_id=None,
                    payee_id=payee_id,
                    destination=None,
                    amount_minor=amount,
                    currency=currency,
                    reference=f"hist_{i+1}",
                    description="seed history",
                    expires_at=expires_at,
                    intent_hash=ih,
                    decision="allow",
                    reasons=[],
                    status="executed",
                    approval_id=None,
                    ledger_entry_id=ledger_id,
                    hold_id=None,
                    failure=None,
                    created_at=executed_at,
                    decided_at=executed_at,
                    executed_at=executed_at,
                    counts_toward_caps=False,
                )
            )
            wallet = (
                db.query(Account)
                .filter(Account.owner_id == principal_id, Account.type == "wallet")
                .one()
            )
            payee_acct = (
                db.query(Account)
                .filter(Account.owner_id == payee_id)
                .one()
            )
            db.add(
                LedgerEntry(
                    entry_id=ledger_id,
                    kind="transfer",
                    from_account=wallet.account_id,
                    to_account=payee_acct.account_id,
                    amount_minor=amount,
                    currency=currency,
                    intent_id=intent_id,
                    hold_id=None,
                    created_at=executed_at,
                )
            )

    db.commit()


def ensure_schema_and_seed() -> None:
    """create_all + seed if empty (hackathon reliability)."""
    Base.metadata.create_all(bind=engine)
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        count = db.query(Principal).count()
        if count == 0:
            reseed(db)
        else:
            # Still refresh in-memory auth tokens
            auth.load_auth_from_seed(load_seed_file())
    finally:
        db.close()
