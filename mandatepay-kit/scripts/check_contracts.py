#!/usr/bin/env python3
"""Validate everything in /contracts. Run from the repo root: python scripts/check_contracts.py
Needs: pip install pyyaml jsonschema openapi-spec-validator cryptography rfc8785
Wire this into CI as `make contracts-check`."""
import base64, hashlib, json, pathlib, sys
import jsonschema, rfc8785, yaml
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from openapi_spec_validator import validate
from openapi_spec_validator.readers import read_from_filename

C = pathlib.Path(__file__).resolve().parent.parent / "contracts"
results = []
def check(name, fn):
    try:
        fn(); results.append((True, name))
    except Exception as e:  # noqa: BLE001
        results.append((False, f"{name}: {type(e).__name__}: {e}"))

b64d = lambda s: base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))
sha = lambda b: hashlib.sha256(b).hexdigest()
schema = json.loads((C / "mandate.schema.json").read_text(encoding="utf-8"))
seed = json.loads((C / "seed.json").read_text(encoding="utf-8"))
vec = json.loads((C / "test-vectors" / "signing.json").read_text(encoding="utf-8"))

check("mandate.schema.json is a valid JSON Schema", lambda: jsonschema.Draft202012Validator.check_schema(schema))

def seed_ok():
    d = seed["default_demo_mandate"]
    pt = d["limits"]["per_txn"]
    assert pt["auto_max_minor"] <= pt["hard_max_minor"]
    known = {p["payee_id"] for p in seed["payees"]}
    assert set(d["payees"]) <= known, "default mandate names an unknown payee"
check("seed.json default mandate is consistent", seed_ok)

for f in ("gateway.openapi.yaml", "market.openapi.yaml"):
    if (C / f).exists():
        def v(f=f):
            spec, base = read_from_filename(str(C / f)); validate(spec, base_uri=base)
        check(f"{f} is valid OpenAPI", v)

def vectors_ok():
    pub = b64d(vec["key"]["public_key_b64url"])
    assert "key_" + sha(pub)[:16] == vec["key"]["key_id"], "key_id derivation"
    pk = Ed25519PublicKey.from_public_bytes(pub)
    m = vec["mandate_vector"]
    jsonschema.Draft202012Validator(schema).validate(m["mandate"])
    for name, obj, canon, sig in (
        ("mandate", m["mandate"], m["canonical_json"], m["signature_b64url"]),
        ("approval", vec["approval_vector"]["statement"], vec["approval_vector"]["canonical_json"], vec["approval_vector"]["signature_b64url"]),
    ):
        assert rfc8785.dumps(obj).decode("utf-8") == canon, f"{name} canonical json"
        pk.verify(b64d(sig), canon.encode("utf-8"))
    assert sha(m["canonical_json"].encode()) == m["content_hash"], "content_hash"
    iv = vec["intent_hash_vector"]
    assert rfc8785.dumps(iv["bound"]).decode() == iv["canonical_json"]
    assert sha(iv["canonical_json"].encode()) == iv["intent_hash"], "intent_hash"
check("signing.json: key_id, canonical JSON, hashes and signatures reproduce", vectors_ok)

for ok, name in results:
    print(("PASS  " if ok else "FAIL  ") + name)
sys.exit(0 if all(ok for ok, _ in results) else 1)
