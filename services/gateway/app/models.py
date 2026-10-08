from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db import Base

JsonType = JSON().with_variant(JSONB(), "postgresql")


class Principal(Base):
    __tablename__ = "principals"

    principal_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Agent(Base):
    __tablename__ = "agents"

    agent_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    principal_id: Mapped[str] = mapped_column(String(80), ForeignKey("principals.principal_id"), nullable=False)
    token: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class OwnerKey(Base):
    __tablename__ = "owner_keys"

    key_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    principal_id: Mapped[str] = mapped_column(String(80), ForeignKey("principals.principal_id"), nullable=False)
    public_key: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Payee(Base):
    __tablename__ = "payees"

    payee_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    bank_code: Mapped[str] = mapped_column(String(16), nullable=False)
    account_number: Mapped[str] = mapped_column(String(20), nullable=False)
    account_name: Mapped[str] = mapped_column(String(120), nullable=False)


class Mandate(Base):
    __tablename__ = "mandates"

    mandate_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    principal_id: Mapped[str] = mapped_column(String(80), ForeignKey("principals.principal_id"), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(80), ForeignKey("agents.agent_id"), nullable=False)
    key_id: Mapped[str] = mapped_column(String(80), nullable=False)
    body: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)
    signature: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    quarantined: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    quarantine_released_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    superseded_by: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PaymentIntent(Base):
    __tablename__ = "payment_intents"

    intent_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    principal_id: Mapped[str] = mapped_column(String(80), ForeignKey("principals.principal_id"), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(80), nullable=False)
    mandate_id: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    payee_id: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    destination: Mapped[Optional[dict[str, Any]]] = mapped_column(JsonType, nullable=True)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    reference: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(280), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    intent_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    reasons: Mapped[list[Any]] = mapped_column(JsonType, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    approval_id: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    ledger_entry_id: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    hold_id: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    failure: Mapped[Optional[dict[str, Any]]] = mapped_column(JsonType, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    executed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    counts_toward_caps: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Approval(Base):
    __tablename__ = "approvals"

    approval_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    intent_id: Mapped[str] = mapped_column(String(80), ForeignKey("payment_intents.intent_id"), nullable=False)
    principal_id: Mapped[str] = mapped_column(String(80), ForeignKey("principals.principal_id"), nullable=False)
    intent_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    bound: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)
    summary: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)
    agent_description: Mapped[Optional[str]] = mapped_column(String(280), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class Account(Base):
    __tablename__ = "accounts"

    account_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    owner_id: Mapped[str] = mapped_column(String(80), nullable=False)
    balance_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="NGN")


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"

    entry_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    from_account: Mapped[str] = mapped_column(String(80), nullable=False)
    to_account: Mapped[str] = mapped_column(String(80), nullable=False)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="NGN")
    intent_id: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    hold_id: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Hold(Base):
    __tablename__ = "holds"

    hold_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    intent_id: Mapped[str] = mapped_column(String(80), ForeignKey("payment_intents.intent_id"), nullable=False)
    principal_id: Mapped[str] = mapped_column(String(80), nullable=False)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="NGN")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open")
    escrow_account_id: Mapped[str] = mapped_column(String(80), nullable=False)
    wallet_account_id: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    settled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_log"

    seq: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    principal_id: Mapped[str] = mapped_column(String(80), nullable=False)
    actor: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)
    subject: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)
    data: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)
    prev_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"
    __table_args__ = (UniqueConstraint("agent_id", "key", name="uq_idem_agent_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id: Mapped[str] = mapped_column(String(80), nullable=False)
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    intent_id: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class KillSwitch(Base):
    __tablename__ = "kill_switches"

    principal_id: Mapped[str] = mapped_column(String(80), ForeignKey("principals.principal_id"), primary_key=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reason: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    changed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

