from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# services/gateway/app/config.py -> repo root is parents[3]
REPO_ROOT = Path(__file__).resolve().parents[3]
GATEWAY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SEED_PATH = REPO_ROOT / "contracts" / "seed.json"
MANDATE_SCHEMA_PATH = REPO_ROOT / "contracts" / "mandate.schema.json"


@lru_cache
def get_settings() -> "Settings":
    return Settings()


class Settings:
    def __init__(self) -> None:
        self.database_url: str = (
            os.getenv("GATEWAY_DATABASE_URL")
            or os.getenv("DATABASE_URL")
            or "postgresql://trustrail:trustrail@localhost:5432/gateway_db"
        )
        self.demo_mode: bool = os.getenv("DEMO_MODE", "true").lower() in ("1", "true", "yes")
        seed_env = os.getenv("SEED_PATH")
        self.seed_path: Path = Path(seed_env) if seed_env else DEFAULT_SEED_PATH
        self.mandate_schema_path: Path = MANDATE_SCHEMA_PATH
        self.escrow_payee_id: str = "pay_market_escrow"
        self.host: str = "0.0.0.0"
        self.port: int = 8001
