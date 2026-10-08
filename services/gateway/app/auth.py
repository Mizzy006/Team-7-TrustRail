from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.errors import Forbidden, Unauthenticated
from app.models import Agent

TokenKind = Literal["owner", "agent", "service"]


@dataclass
class AuthContext:
    kind: TokenKind
    token: str
    principal_id: Optional[str] = None
    agent_id: Optional[str] = None
    service_name: Optional[str] = None
    display_name: Optional[str] = None


# Populated from seed.json at startup / reset
_OWNER_TOKENS: dict[str, dict] = {}
_SERVICE_TOKENS: dict[str, str] = {}


def load_auth_from_seed(seed: dict) -> None:
    global _OWNER_TOKENS, _SERVICE_TOKENS
    owners: dict[str, dict] = {}
    for p in seed.get("personas", []):
        if p.get("role") == "retailer_owner" and p.get("token") and p.get("principal_id"):
            owners[p["token"]] = {
                "principal_id": p["principal_id"],
                "display_name": p.get("display_name", p["principal_id"]),
            }
    _OWNER_TOKENS = owners
    services: dict[str, str] = {}
    for name, token in (seed.get("service_keys") or {}).items():
        services[token] = name
    _SERVICE_TOKENS = services


def _extract_bearer(request: Request) -> str:
    header = request.headers.get("Authorization")
    if not header or not header.startswith("Bearer "):
        raise Unauthenticated()
    token = header[7:].strip()
    if not token:
        raise Unauthenticated()
    return token


def resolve_token(token: str, db: Session) -> AuthContext:
    if token in _OWNER_TOKENS:
        info = _OWNER_TOKENS[token]
        return AuthContext(
            kind="owner",
            token=token,
            principal_id=info["principal_id"],
            display_name=info["display_name"],
        )
    if token in _SERVICE_TOKENS:
        return AuthContext(
            kind="service",
            token=token,
            service_name=_SERVICE_TOKENS[token],
        )
    agent = db.query(Agent).filter(Agent.token == token).one_or_none()
    if agent:
        return AuthContext(
            kind="agent",
            token=token,
            principal_id=agent.principal_id,
            agent_id=agent.agent_id,
        )
    raise Unauthenticated("Unknown token")


def require_kinds(*kinds: TokenKind):
    def dependency(request: Request, db: Session = Depends(get_db)) -> AuthContext:
        token = _extract_bearer(request)
        ctx = resolve_token(token, db)
        if ctx.kind not in kinds:
            raise Forbidden(f"{ctx.kind} token cannot access this endpoint")
        request.state.auth = ctx
        return ctx

    return dependency


require_owner = require_kinds("owner")
require_agent = require_kinds("agent")
require_service = require_kinds("service")
require_owner_or_agent = require_kinds("owner", "agent")
