"""Initial gateway schema.

Revision ID: 001
Revises:
Create Date: 2026-10-08

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JsonType = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "principals",
        sa.Column("principal_id", sa.String(80), primary_key=True),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "agents",
        sa.Column("agent_id", sa.String(80), primary_key=True),
        sa.Column("principal_id", sa.String(80), sa.ForeignKey("principals.principal_id"), nullable=False),
        sa.Column("token", sa.String(120), unique=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "owner_keys",
        sa.Column("key_id", sa.String(80), primary_key=True),
        sa.Column("principal_id", sa.String(80), sa.ForeignKey("principals.principal_id"), nullable=False),
        sa.Column("public_key", sa.String(64), nullable=False),
        sa.Column("label", sa.String(60), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "payees",
        sa.Column("payee_id", sa.String(80), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("verified", sa.Boolean(), nullable=False),
        sa.Column("bank_code", sa.String(16), nullable=False),
        sa.Column("account_number", sa.String(20), nullable=False),
        sa.Column("account_name", sa.String(120), nullable=False),
    )
    op.create_table(
        "mandates",
        sa.Column("mandate_id", sa.String(80), primary_key=True),
        sa.Column("principal_id", sa.String(80), sa.ForeignKey("principals.principal_id"), nullable=False),
        sa.Column("agent_id", sa.String(80), sa.ForeignKey("agents.agent_id"), nullable=False),
        sa.Column("key_id", sa.String(80), nullable=False),
        sa.Column("body", JsonType, nullable=False),
        sa.Column("signature", JsonType, nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("quarantined", sa.Boolean(), nullable=False),
        sa.Column("quarantine_released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("superseded_by", sa.String(80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "payment_intents",
        sa.Column("intent_id", sa.String(80), primary_key=True),
        sa.Column("principal_id", sa.String(80), sa.ForeignKey("principals.principal_id"), nullable=False),
        sa.Column("agent_id", sa.String(80), nullable=False),
        sa.Column("mandate_id", sa.String(80), nullable=True),
        sa.Column("payee_id", sa.String(80), nullable=True),
        sa.Column("destination", JsonType, nullable=True),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("reference", sa.String(64), nullable=False),
        sa.Column("description", sa.String(280), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("intent_hash", sa.String(64), nullable=False),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("reasons", JsonType, nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("approval_id", sa.String(80), nullable=True),
        sa.Column("ledger_entry_id", sa.String(80), nullable=True),
        sa.Column("hold_id", sa.String(80), nullable=True),
        sa.Column("failure", JsonType, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("counts_toward_caps", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.create_table(
        "approvals",
        sa.Column("approval_id", sa.String(80), primary_key=True),
        sa.Column("intent_id", sa.String(80), sa.ForeignKey("payment_intents.intent_id"), nullable=False),
        sa.Column("principal_id", sa.String(80), sa.ForeignKey("principals.principal_id"), nullable=False),
        sa.Column("intent_hash", sa.String(64), nullable=False),
        sa.Column("bound", JsonType, nullable=False),
        sa.Column("summary", JsonType, nullable=False),
        sa.Column("agent_description", sa.String(280), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "accounts",
        sa.Column("account_id", sa.String(80), primary_key=True),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("owner_id", sa.String(80), nullable=False),
        sa.Column("balance_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
    )
    op.create_table(
        "ledger_entries",
        sa.Column("entry_id", sa.String(80), primary_key=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("from_account", sa.String(80), nullable=False),
        sa.Column("to_account", sa.String(80), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("intent_id", sa.String(80), nullable=True),
        sa.Column("hold_id", sa.String(80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "holds",
        sa.Column("hold_id", sa.String(80), primary_key=True),
        sa.Column("intent_id", sa.String(80), sa.ForeignKey("payment_intents.intent_id"), nullable=False),
        sa.Column("principal_id", sa.String(80), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("escrow_account_id", sa.String(80), nullable=False),
        sa.Column("wallet_account_id", sa.String(80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "audit_log",
        sa.Column("seq", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("type", sa.String(64), nullable=False),
        sa.Column("principal_id", sa.String(80), nullable=False),
        sa.Column("actor", JsonType, nullable=False),
        sa.Column("subject", JsonType, nullable=False),
        sa.Column("data", JsonType, nullable=False),
        sa.Column("prev_hash", sa.String(64), nullable=False),
        sa.Column("hash", sa.String(64), nullable=False, unique=True),
    )
    op.create_table(
        "idempotency_keys",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("agent_id", sa.String(80), nullable=False),
        sa.Column("key", sa.String(64), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("intent_id", sa.String(80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("agent_id", "key", name="uq_idem_agent_key"),
    )
    op.create_table(
        "kill_switches",
        sa.Column("principal_id", sa.String(80), sa.ForeignKey("principals.principal_id"), primary_key=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.String(200), nullable=True),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    for t in [
        "kill_switches",
        "idempotency_keys",
        "audit_log",
        "holds",
        "ledger_entries",
        "accounts",
        "approvals",
        "payment_intents",
        "mandates",
        "payees",
        "owner_keys",
        "agents",
        "principals",
    ]:
        op.drop_table(t)
