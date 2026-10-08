from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class Money(BaseModel):
    model_config = ConfigDict(extra="forbid")
    amount_minor: int = Field(ge=0)
    currency: str


class Destination(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bank_code: str
    account_number: str
    account_name: str


class Signature(BaseModel):
    model_config = ConfigDict(extra="forbid")
    alg: Literal["Ed25519"]
    key_id: str
    value: str


class ReasonOut(BaseModel):
    code: str
    detail: str


class RegisterKeyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    public_key: str
    label: Optional[str] = None


class OwnerKeyOut(BaseModel):
    key_id: str
    principal_id: str
    public_key: str
    label: Optional[str] = None
    created_at: str


class KillSwitchOut(BaseModel):
    active: bool
    reason: Optional[str] = None
    changed_at: Optional[str] = None


class MeOut(BaseModel):
    principal_id: str
    display_name: str
    server_time: str
    keys: list[OwnerKeyOut]
    kill_switch: KillSwitchOut


class PayeeOut(BaseModel):
    payee_id: str
    name: str
    kind: str
    verified: bool
    destination: Destination


class SignedMandateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mandate: dict[str, Any]
    signature: Signature


class MandateRecordOut(BaseModel):
    mandate: dict[str, Any]
    signature: dict[str, Any]
    content_hash: str
    status: str
    quarantined: bool
    superseded_by: Optional[str] = None
    created_at: str


class UsageWindowOut(BaseModel):
    name: str
    seconds: int
    cap_minor: int
    spent_minor: int
    remaining_minor: int


class UsageOut(BaseModel):
    mandate_id: str
    windows: list[UsageWindowOut]
    wallet_balance: Money
    exposure_minor: int
    quarantined: bool


class PaymentIntentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    payee_id: Optional[str] = None
    destination: Optional[Destination] = None
    amount: Money
    reference: str = Field(min_length=1, max_length=64)
    description: Optional[str] = Field(default=None, max_length=280)
    expires_at: Optional[str] = None


class PaymentIntentOut(BaseModel):
    intent_id: str
    mandate_id: Optional[str]
    agent_id: str
    payee_id: Optional[str]
    destination: Optional[Destination]
    amount: Money
    reference: str
    description: Optional[str]
    expires_at: str
    intent_hash: str
    decision: str
    reasons: list[ReasonOut]
    status: str
    approval_id: Optional[str]
    ledger_entry_id: Optional[str]
    hold_id: Optional[str]
    failure: Optional[ReasonOut]
    created_at: str
    decided_at: str
    executed_at: Optional[str]


class ApprovalBound(BaseModel):
    mandate_id: Optional[str]
    payee_id: Optional[str]
    amount_minor: int
    currency: str
    reference: str
    expires_at: str


class ApprovalSummary(BaseModel):
    payee_name: Optional[str]
    payee_verified: bool
    reasons: list[ReasonOut]
    windows: list[UsageWindowOut]


class ApprovalOut(BaseModel):
    approval_id: str
    intent_id: str
    status: str
    intent_hash: str
    bound: ApprovalBound
    summary: ApprovalSummary
    agent_description: Optional[str]
    expires_at: str
    created_at: str
    decided_at: Optional[str]


class ApprovalStatement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["mandatepay/approval/v1"]
    approval_id: str
    intent_id: str
    intent_hash: str
    decision: Literal["approve", "deny"]


class ApprovalDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    statement: ApprovalStatement
    signature: Optional[Signature] = None


class KillSwitchSet(BaseModel):
    model_config = ConfigDict(extra="forbid")
    active: bool
    reason: Optional[str] = Field(default=None, max_length=200)


class AuditActor(BaseModel):
    type: str
    id: str


class AuditEntryOut(BaseModel):
    seq: int
    ts: str
    type: str
    principal_id: str
    actor: AuditActor
    subject: AuditActor
    data: dict[str, Any]
    prev_hash: str
    hash: str


class AuditVerificationOut(BaseModel):
    ok: bool
    entries_checked: int
    head_hash: str
    first_bad_seq: Optional[int]


class AccountOut(BaseModel):
    account_id: str
    type: str
    owner_id: str
    balance: Money


class LedgerEntryOut(BaseModel):
    entry_id: str
    kind: str
    from_account: str
    to_account: str
    amount: Money
    intent_id: Optional[str]
    hold_id: Optional[str]
    created_at: str


class SettleHoldRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    release_to_payee_id: Optional[str] = None
    release_minor: int = Field(ge=0)
    refund_minor: int = Field(ge=0)


class SettleHoldResponse(BaseModel):
    hold_id: str
    entries: list[LedgerEntryOut]


class TamperAuditRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    seq: int = Field(ge=1)
