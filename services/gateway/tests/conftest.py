from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Ensure gateway package root is on sys.path
GATEWAY_ROOT = Path(__file__).resolve().parents[1]
if str(GATEWAY_ROOT) not in sys.path:
    sys.path.insert(0, str(GATEWAY_ROOT))

REPO_ROOT = GATEWAY_ROOT.parents[1]
SIGNING_PATH = REPO_ROOT / "contracts" / "test-vectors" / "signing.json"
SEED_PATH = REPO_ROOT / "contracts" / "seed.json"


@pytest.fixture(scope="session")
def signing_vectors():
    import json

    with open(SIGNING_PATH, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="session")
def seed_data():
    import json

    with open(SEED_PATH, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="session")
def postgres_available() -> bool:
    url = (
        os.getenv("GATEWAY_DATABASE_URL")
        or os.getenv("DATABASE_URL")
        or "postgresql://trustrail:trustrail@localhost:5432/gateway_db"
    )
    try:
        from sqlalchemy import create_engine, text

        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+psycopg://", 1)
        eng = create_engine(url, pool_pre_ping=True)
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
