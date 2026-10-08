from __future__ import annotations

import hashlib

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.crypto import (
    b64url_decode,
    b64url_encode,
    canonical_json,
    content_hash,
    intent_hash,
    key_id_from_public_key_b64url,
    key_id_from_public_key_bytes,
    verify_ed25519,
    verify_signature_over_obj,
)


def test_key_id(signing_vectors):
    key = signing_vectors["key"]
    raw = b64url_decode(key["public_key_b64url"])
    assert key_id_from_public_key_bytes(raw) == key["key_id"]
    assert key_id_from_public_key_b64url(key["public_key_b64url"]) == key["key_id"]
    # public key derived from seed matches vector
    seed = bytes.fromhex(key["private_key_seed_hex"])
    priv = Ed25519PrivateKey.from_private_bytes(seed)
    pub = priv.public_key().public_bytes_raw()
    assert b64url_encode(pub) == key["public_key_b64url"]


def test_mandate_canonical_and_hash(signing_vectors):
    mv = signing_vectors["mandate_vector"]
    canon = canonical_json(mv["mandate"])
    assert canon == mv["canonical_json"]
    assert content_hash(mv["mandate"]) == mv["content_hash"]


def test_mandate_signature(signing_vectors):
    mv = signing_vectors["mandate_vector"]
    key = signing_vectors["key"]
    assert verify_signature_over_obj(
        key["public_key_b64url"], mv["mandate"], mv["signature_b64url"]
    )
    # one-byte change rejects
    bad = dict(mv["mandate"])
    bad["purpose"] = bad["purpose"] + "x"
    assert not verify_signature_over_obj(key["public_key_b64url"], bad, mv["signature_b64url"])


def test_intent_hash(signing_vectors):
    iv = signing_vectors["intent_hash_vector"]
    assert canonical_json(iv["bound"]) == iv["canonical_json"]
    assert intent_hash(iv["bound"]) == iv["intent_hash"]


def test_approval_signature(signing_vectors):
    av = signing_vectors["approval_vector"]
    key = signing_vectors["key"]
    assert canonical_json(av["statement"]) == av["canonical_json"]
    assert verify_signature_over_obj(
        key["public_key_b64url"], av["statement"], av["signature_b64url"]
    )
    # wrong message
    assert not verify_ed25519(
        key["public_key_b64url"],
        b"tampered",
        av["signature_b64url"],
    )


def test_re_sign_matches_vector(signing_vectors):
    """Sign with demo seed and match published signatures."""
    key = signing_vectors["key"]
    seed = bytes.fromhex(key["private_key_seed_hex"])
    priv = Ed25519PrivateKey.from_private_bytes(seed)

    mv = signing_vectors["mandate_vector"]
    sig = priv.sign(canonical_json(mv["mandate"]).encode("utf-8"))
    assert b64url_encode(sig) == mv["signature_b64url"]

    av = signing_vectors["approval_vector"]
    sig2 = priv.sign(canonical_json(av["statement"]).encode("utf-8"))
    assert b64url_encode(sig2) == av["signature_b64url"]
