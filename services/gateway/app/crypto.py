from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

try:
    import rfc8785

    def canonical_json(obj: Any) -> str:
        raw = rfc8785.dumps(obj)
        if isinstance(raw, bytes):
            return raw.decode("utf-8")
        return str(raw)

except ImportError:

    def canonical_json(obj: Any) -> str:
        return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def canonical_bytes(obj: Any) -> bytes:
    return canonical_json(obj).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def content_hash(obj: Any) -> str:
    return sha256_hex(canonical_bytes(obj))


def intent_hash(bound: dict[str, Any]) -> str:
    """Hash only the bound fields for a payment intent."""
    fields = {
        "mandate_id": bound.get("mandate_id"),
        "payee_id": bound.get("payee_id"),
        "amount_minor": bound["amount_minor"],
        "currency": bound["currency"],
        "reference": bound["reference"],
        "expires_at": bound["expires_at"],
    }
    return content_hash(fields)


def b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def b64url_decode(value: str) -> bytes:
    pad = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + pad)


def key_id_from_public_key_bytes(raw_pubkey: bytes) -> str:
    return "key_" + sha256_hex(raw_pubkey)[:16]


def key_id_from_public_key_b64url(public_key_b64url: str) -> str:
    return key_id_from_public_key_bytes(b64url_decode(public_key_b64url))


def verify_ed25519(public_key_b64url: str, message: bytes, signature_b64url: str) -> bool:
    try:
        pub = Ed25519PublicKey.from_public_bytes(b64url_decode(public_key_b64url))
        pub.verify(b64url_decode(signature_b64url), message)
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False


def verify_signature_over_obj(public_key_b64url: str, obj: Any, signature_b64url: str) -> bool:
    return verify_ed25519(public_key_b64url, canonical_bytes(obj), signature_b64url)
