from __future__ import annotations

import secrets
import string

_ALPHABET = string.ascii_letters + string.digits


def _opaque(length: int = 22) -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(length))


def new_id(prefix: str, length: int = 22) -> str:
    return f"{prefix}_{_opaque(length)}"


def new_intent_id() -> str:
    return new_id("pi", 20)


def new_approval_id() -> str:
    return new_id("apr", 20)


def new_hold_id() -> str:
    return new_id("hld", 20)


def new_ledger_id() -> str:
    return new_id("led", 20)


def new_request_id() -> str:
    return new_id("req", 16)
