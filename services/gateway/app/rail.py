from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.errors import Conflict, NotFound, ValidationFailed
from app.ids import new_hold_id, new_ledger_id
from app.models import Account, Hold, LedgerEntry


def get_wallet(db: Session, principal_id: str) -> Account:
    acct = (
        db.query(Account)
        .filter(Account.owner_id == principal_id, Account.type == "wallet")
        .with_for_update()
        .one_or_none()
    )
    if acct is None:
        raise NotFound(f"Wallet for {principal_id} not found")
    return acct


def get_payee_account(db: Session, payee_id: str) -> Account:
    acct = (
        db.query(Account)
        .filter(Account.owner_id == payee_id, Account.type.in_(["payee", "escrow"]))
        .with_for_update()
        .one_or_none()
    )
    if acct is None:
        raise NotFound(f"Account for payee {payee_id} not found")
    return acct


def transfer(
    db: Session,
    *,
    from_account: Account,
    to_account: Account,
    amount_minor: int,
    currency: str,
    intent_id: str,
    ts: datetime,
) -> LedgerEntry:
    if amount_minor <= 0:
        raise ValidationFailed("Transfer amount must be positive")
    if from_account.balance_minor < amount_minor:
        raise ValidationFailed("Insufficient funds", code="INSUFFICIENT_FUNDS")
    from_account.balance_minor -= amount_minor
    to_account.balance_minor += amount_minor
    entry = LedgerEntry(
        entry_id=new_ledger_id(),
        kind="transfer",
        from_account=from_account.account_id,
        to_account=to_account.account_id,
        amount_minor=amount_minor,
        currency=currency,
        intent_id=intent_id,
        hold_id=None,
        created_at=ts,
    )
    db.add(entry)
    db.flush()
    return entry


def hold_funds(
    db: Session,
    *,
    wallet: Account,
    escrow: Account,
    amount_minor: int,
    currency: str,
    intent_id: str,
    principal_id: str,
    ts: datetime,
) -> tuple[LedgerEntry, Hold]:
    if amount_minor <= 0:
        raise ValidationFailed("Hold amount must be positive")
    if wallet.balance_minor < amount_minor:
        raise ValidationFailed("Insufficient funds", code="INSUFFICIENT_FUNDS")
    hold_id = new_hold_id()
    wallet.balance_minor -= amount_minor
    escrow.balance_minor += amount_minor
    entry = LedgerEntry(
        entry_id=new_ledger_id(),
        kind="hold",
        from_account=wallet.account_id,
        to_account=escrow.account_id,
        amount_minor=amount_minor,
        currency=currency,
        intent_id=intent_id,
        hold_id=hold_id,
        created_at=ts,
    )
    hold = Hold(
        hold_id=hold_id,
        intent_id=intent_id,
        principal_id=principal_id,
        amount_minor=amount_minor,
        currency=currency,
        status="open",
        escrow_account_id=escrow.account_id,
        wallet_account_id=wallet.account_id,
        created_at=ts,
        settled_at=None,
    )
    db.add(entry)
    db.add(hold)
    db.flush()
    return entry, hold


def settle_hold(
    db: Session,
    *,
    hold_id: str,
    release_to_payee_id: Optional[str],
    release_minor: int,
    refund_minor: int,
    ts: datetime,
) -> list[LedgerEntry]:
    hold = db.query(Hold).filter(Hold.hold_id == hold_id).with_for_update().one_or_none()
    if hold is None:
        raise NotFound(f"Hold {hold_id} not found")
    if hold.status != "open":
        raise Conflict("Hold already settled")
    if release_minor + refund_minor != hold.amount_minor:
        raise ValidationFailed(
            f"release_minor + refund_minor must equal hold amount {hold.amount_minor}"
        )
    if release_minor > 0 and not release_to_payee_id:
        raise ValidationFailed("release_to_payee_id required when release_minor > 0")

    escrow = db.query(Account).filter(Account.account_id == hold.escrow_account_id).with_for_update().one()
    wallet = db.query(Account).filter(Account.account_id == hold.wallet_account_id).with_for_update().one()
    entries: list[LedgerEntry] = []

    if release_minor > 0:
        payee_acct = get_payee_account(db, release_to_payee_id)  # type: ignore[arg-type]
        if escrow.balance_minor < release_minor:
            raise ValidationFailed("Escrow balance too low for release")
        escrow.balance_minor -= release_minor
        payee_acct.balance_minor += release_minor
        e = LedgerEntry(
            entry_id=new_ledger_id(),
            kind="settle_release",
            from_account=escrow.account_id,
            to_account=payee_acct.account_id,
            amount_minor=release_minor,
            currency=hold.currency,
            intent_id=hold.intent_id,
            hold_id=hold.hold_id,
            created_at=ts,
        )
        db.add(e)
        entries.append(e)

    if refund_minor > 0:
        if escrow.balance_minor < refund_minor:
            raise ValidationFailed("Escrow balance too low for refund")
        escrow.balance_minor -= refund_minor
        wallet.balance_minor += refund_minor
        e = LedgerEntry(
            entry_id=new_ledger_id(),
            kind="settle_refund",
            from_account=escrow.account_id,
            to_account=wallet.account_id,
            amount_minor=refund_minor,
            currency=hold.currency,
            intent_id=hold.intent_id,
            hold_id=hold.hold_id,
            created_at=ts,
        )
        db.add(e)
        entries.append(e)

    hold.status = "settled"
    hold.settled_at = ts
    db.flush()
    return entries
