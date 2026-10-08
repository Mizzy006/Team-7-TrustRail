import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional

app = FastAPI(title="Market Service", version="1.0.0")

class OrderRequest(BaseModel):
    sku_id: str
    qty: int
    kind: str = "direct_purchase"
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
            {"sku_id": "sku_noodles_carton", "name": "Instant Noodles (Carton)", "price_minor": 800000},
            {"sku_id": "sku_rice_50kg", "name": "Parboiled Rice 50kg", "price_minor": 4500000},
            {"sku_id": "sku_cooking_oil_5l", "name": "Vegetable Cooking Oil 5L", "price_minor": 850000},
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
    # Determine mock price
    price = 4500000
    if req.sku_id == "sku_noodles_carton": price = 800000
    elif req.sku_id == "sku_cooking_oil_5l": price = 850000
    elif req.sku_id == "sku_malt_crate": price = 900000
    
    amount = price * req.qty
    payee = "pay_primefoods" if req.kind == "direct_purchase" else "pay_market_escrow"
    
    return {
        "order_id": f"ord_mock_{req.sku_id}_{req.qty}",
        "kind": req.kind,
        "sku_id": req.sku_id,
        "qty": req.qty,
        "status": "awaiting_payment",
        "payment_request": {
            "payee_id": payee,
            "amount": {"amount_minor": amount, "currency": "NGN"},
            "reference": f"ord_mock_{req.sku_id}_{req.qty}",
            "description": f"Order for {req.qty} x {req.sku_id}"
        },
        "simulated": False
    }

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8002, reload=True)

