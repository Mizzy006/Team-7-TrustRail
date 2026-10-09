import uvicorn
import asyncio
import os
import requests
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
from uuid import uuid4
from threading import Lock

app = FastAPI(title="Market Service", version="1.0.0")
orders: dict[str, dict] = {}
orders_lock = Lock()
reconcile_task = None

class OrderRequest(BaseModel):
    sku_id: str
    qty: int
    kind: str = "direct"
    pool_id: Optional[str] = None

@app.get("/healthz")
def health_check():
    return {"status": "ok", "service": "market", "version": "1.0.0"}

@app.get("/v1/inventory")
def get_inventory():
    return {
        "inventory": [
            {"sku_id": "sku_noodles_carton", "sku_name": "Instant Noodles", "stock": 12, "days_cover": 2.4, "reorder_point": 25},
            {"sku_id": "sku_rice_50kg", "sku_name": "Parboiled Rice 50kg", "stock": 4, "days_cover": 1.8, "reorder_point": 10},
            {"sku_id": "sku_cooking_oil_5l", "sku_name": "Vegetable Cooking Oil 5L", "stock": 18, "days_cover": 4.7, "reorder_point": 20},
            {"sku_id": "sku_malt_crate", "sku_name": "Malt Drink (Crate)", "stock": 50, "days_cover": 10.0, "reorder_point": 30},
            {"sku_id": "sku_sugar_50kg", "sku_name": "Granulated Sugar 50kg", "stock": 5, "days_cover": 2.5, "reorder_point": 15},
            {"sku_id": "sku_evap_milk_case", "sku_name": "Evaporated Milk (Case)", "stock": 8, "days_cover": 2.8, "reorder_point": 20}
        ]
    }

@app.get("/v1/products")
def get_products():
    return {
        "products": [
            {"sku_id": "sku_noodles_carton", "name": "Instant Noodles (Carton)", "price_minor": 300000},
            {"sku_id": "sku_rice_50kg", "name": "Parboiled Rice 50kg", "price_minor": 6500000},
            {"sku_id": "sku_cooking_oil_5l", "name": "Vegetable Cooking Oil 5L", "price_minor": 1400000},
            {"sku_id": "sku_malt_crate", "name": "Malt Drink (Crate)", "price_minor": 900000},
            {"sku_id": "sku_sugar_50kg", "name": "Granulated Sugar 50kg", "price_minor": 5500000},
            {"sku_id": "sku_evap_milk_case", "name": "Evaporated Milk (Case)", "price_minor": 1500000}
        ]
    }

@app.get("/v1/pools")
def get_pools():
    return {
        "pools": [
            {
                "pool_id": "pool_noodles_1",
                "sku_id": "sku_noodles_carton",
                "sku_name": "Instant Noodles (Carton)",
                "payee_id": "pay_market_escrow",
                "committed_qty": 32,
                "moq": 50,
                "current_unit_price_minor": 750000,
                "status": "open"
            },
            {
                "pool_id": "pool_rice_1",
                "sku_id": "sku_rice_50kg",
                "sku_name": "Parboiled Rice 50kg",
                "payee_id": "pay_market_escrow",
                "committed_qty": 74,
                "moq": 100,
                "current_unit_price_minor": 4500000,
                "status": "open"
            }
        ]
    }

@app.post("/v1/orders")
def create_order(req: OrderRequest):
    prices = {"sku_noodles_carton": 300000, "sku_rice_50kg": 6500000, "sku_cooking_oil_5l": 1400000,
              "sku_malt_crate": 900000, "sku_sugar_50kg": 5500000, "sku_evap_milk_case": 1500000}
    if req.qty < 1 or req.qty > 1000:
        raise HTTPException(422, "qty must be between 1 and 1000")
    if req.sku_id not in prices:
        raise HTTPException(404, "Unknown SKU")
    if req.kind not in {"direct", "pool_commitment"}:
        raise HTTPException(422, "kind must be direct or pool_commitment")
    if req.kind == "pool_commitment" and not req.pool_id:
        raise HTTPException(422, "pool_id is required for pool orders")
    
    amount = prices[req.sku_id] * req.qty
    payee = "pay_primefoods" if req.kind == "direct" else "pay_market_escrow"
    
    order_id = f"ord_{uuid4().hex[:20]}"
    order = {
        "order_id": order_id,
        "kind": req.kind,
        "sku_id": req.sku_id,
        "qty": req.qty,
        "pool_id": req.pool_id,
        "status": "awaiting_payment",
        "amount": {"amount_minor": amount, "currency": "NGN"},
        "payment_request": {
            "payee_id": payee,
            "amount": {"amount_minor": amount, "currency": "NGN"},
            "reference": order_id,
            "description": f"Order for {req.qty} x {req.sku_id}"
        },
        "intent_id": None,
        "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "simulated": False
    }
    with orders_lock:
        orders[order_id] = order
    return order

@app.get("/v1/orders")
def list_orders():
    with orders_lock:
        order_ids = list(orders)
    for order_id in order_ids:
        _reconcile_order(order_id)
    with orders_lock:
        return {"items": list(reversed(list(orders.values())))}

@app.get("/v1/orders/{order_id}")
def get_order(order_id: str):
    _reconcile_order(order_id)
    with orders_lock:
        order = orders.get(order_id)
        if order is None:
            raise HTTPException(404, "Order not found")
        return order

@app.post("/v1/orders/{order_id}/payment")
def update_order_payment(order_id: str, body: dict):
    intent_id = body.get("intent_id")
    if not intent_id:
        raise HTTPException(422, "intent_id is required")
    with orders_lock:
        order = orders.get(order_id)
        if order is None:
            raise HTTPException(404, "Order not found")
        if order.get("intent_id") and order["intent_id"] != intent_id:
            raise HTTPException(409, "Order already has a different payment intent")
        order["intent_id"] = intent_id
    return _reconcile_order(order_id)

def _reconcile_order(order_id: str):
    with orders_lock:
        order = orders.get(order_id)
        if order is None or not order.get("intent_id"):
            return order
        intent_id = order["intent_id"]
        expected = dict(order["payment_request"])
    gateway = os.getenv("GATEWAY_URL", "http://localhost:8001").rstrip("/")
    token = os.getenv("MARKET_SERVICE_TOKEN", "key_service_market")
    try:
        response = requests.get(f"{gateway}/internal/v1/intents/{intent_id}", headers={"Authorization": f"Bearer {token}"}, timeout=10)
        response.raise_for_status()
        intent = response.json()
    except requests.RequestException as exc:
        raise HTTPException(502, "Could not verify payment intent with gateway") from exc
    if (intent.get("payee_id") != expected["payee_id"] or intent.get("amount", {}).get("amount_minor") != expected["amount"]["amount_minor"]
            or intent.get("amount", {}).get("currency") != expected["amount"]["currency"] or intent.get("reference") != expected["reference"]):
        raise HTTPException(409, "Payment intent does not match the order payment request")
    status = intent.get("status")
    if status == "executed":
        order_status = "paid"
    elif status == "pending_approval":
        order_status = "awaiting_approval"
    elif status in {"blocked", "denied", "expired", "failed"}:
        order_status = "blocked"
    else:
        raise HTTPException(409, f"Payment intent is not in a reconciliable state: {status}")
    with orders_lock:
        order = orders.get(order_id)
        if order is None:
            return None
        order["status"] = order_status
        return order

async def _reconcile_worker():
    while True:
        with orders_lock:
            ids = [oid for oid, order in orders.items() if order.get("intent_id")]
        for order_id in ids:
            try:
                await asyncio.to_thread(_reconcile_order, order_id)
            except Exception:
                # Keep polling other orders; gateway outages must not stop reconciliation.
                continue
        await asyncio.sleep(2)

@app.on_event("startup")
async def start_reconciler():
    global reconcile_task
    reconcile_task = asyncio.create_task(_reconcile_worker())

@app.on_event("shutdown")
async def stop_reconciler():
    if reconcile_task:
        reconcile_task.cancel()

@app.post("/demo/v1/reset", status_code=204)
def reset_orders():
    with orders_lock:
        orders.clear()

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8002, reload=True)

