"""TrustRail Market Service — catalog, inventory, pools, orders.
Spec: contracts/market.openapi.yaml (S3)
Owner: Software Developer
Port: 8002
"""
import json
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException

app = FastAPI(title="TrustRail Market API", version="1.0.0")

DATA_DIR = Path(__file__).parent.parent.parent / "data"


def _load_catalog() -> dict:
    """Load catalog.json from repo data dir. Returns {} if missing."""
    path = DATA_DIR / "catalog.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text())


# ─── Health ────────────────────────────────────────────────
@app.get("/healthz")
def health_check():
    return {"status": "ok", "service": "market", "version": "1.0.0"}


# ─── Catalog ───────────────────────────────────────────────
@app.get("/v1/catalog")
def list_catalog():
    catalog = _load_catalog()
    return {"products": catalog.get("products", [])}


@app.get("/v1/catalog/{sku_id}")
def get_sku(sku_id: str):
    catalog = _load_catalog()
    for sku in catalog.get("products", []):
        if sku.get("sku_id") == sku_id:
            return sku
    raise HTTPException(404, f"SKU {sku_id} not found")


# ─── Inventory ─────────────────────────────────────────────
@app.get("/v1/inventory")
def get_inventory():
    # TODO: read from DB, currently returns empty
    return {"items": []}


@app.post("/v1/inventory/movements")
def record_movement(payload: dict):
    raise HTTPException(501, "not implemented yet — S6")


# ─── Pools ─────────────────────────────────────────────────
@app.get("/v1/pools")
def list_pools():
    # TODO: read from DB
    return {"pools": []}


@app.get("/v1/pools/{pool_id}")
def get_pool(pool_id: str):
    raise HTTPException(404, f"Pool {pool_id} not found")


@app.post("/v1/pools/{pool_id}/commit")
def commit_to_pool(pool_id: str, payload: dict):
    raise HTTPException(501, "not implemented yet — S6")


@app.post("/v1/pools/{pool_id}/close")
def close_pool(pool_id: str):
    raise HTTPException(501, "not implemented yet — S7")


# ─── Orders ────────────────────────────────────────────────
@app.get("/v1/orders")
def list_orders():
    return {"orders": []}


@app.post("/v1/orders")
def create_order(payload: dict):
    raise HTTPException(501, "not implemented yet — S6")


@app.get("/v1/orders/{order_id}")
def get_order(order_id: str):
    raise HTTPException(404, f"Order {order_id} not found")


@app.post("/v1/orders/{order_id}/payment")
def record_payment(order_id: str, payload: dict):
    raise HTTPException(501, "not implemented yet — S6")


# ─── Internal (Agent + Gateway) ───────────────────────────
@app.get("/internal/v1/pools/{pool_id}")
def internal_get_pool(pool_id: str):
    raise HTTPException(404, f"Pool {pool_id} not found")


# ─── Demo ──────────────────────────────────────────────────
@app.post("/demo/v1/reset")
def reset_demo():
    return {"ok": True, "note": "reset not implemented yet — S6"}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8002, reload=True)