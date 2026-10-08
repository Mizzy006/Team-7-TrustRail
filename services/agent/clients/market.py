"""
M3: Market API Client.

Typed client wrapper for calling Market service endpoints:
- GET /v1/products
- GET /v1/inventory
- GET /v1/pools
- POST /v1/orders
- POST /v1/orders/{order_id}/payment
"""

import requests
from typing import Dict, Any, List, Optional

class MarketClient:
    def __init__(self, base_url: str = "http://localhost:8002", token: str = "tok_owner_ada"):
        self.base_url = base_url.rstrip("/")
        self.token = token

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }

    def get_products(self) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/v1/products"
        try:
            res = requests.get(url, headers=self._headers(), timeout=0.2)
            if res.status_code == 200:
                return res.json().get("products", [])
            return []
        except Exception:
            return []

    def get_inventory(self) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/v1/inventory"
        try:
            res = requests.get(url, headers=self._headers(), timeout=0.2)
            if res.status_code == 200:
                return res.json().get("inventory", [])
            return []
        except Exception:
            return [
                {"sku_id": "sku_noodles_carton", "sku_name": "Instant Noodles", "stock": 12, "days_cover": 2.4, "reorder_point": 25},
                {"sku_id": "sku_rice_50kg", "sku_name": "Parboiled Rice 50kg", "stock": 4, "days_cover": 1.8, "reorder_point": 10},
                {"sku_id": "sku_cooking_oil_5l", "sku_name": "Vegetable Cooking Oil 5L", "stock": 18, "days_cover": 4.7, "reorder_point": 20}
            ]

    def get_pools(self) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/v1/pools"
        try:
            res = requests.get(url, headers=self._headers(), timeout=0.2)
            if res.status_code == 200:
                return res.json().get("pools", [])
            return []
        except Exception:
            return [
                {
                    "pool_id": "pool_noodles_1",
                    "sku_id": "sku_noodles_carton",
                    "sku_name": "Instant Noodles (Carton)",
                    "payee_id": "pay_market_escrow",
                    "committed_qty": 32,
                    "moq": 50,
                    "current_unit_price_minor": 1200000,
                    "status": "open"
                }
            ]

    def create_order(self, sku_id: str, qty: int, kind: str = "direct_purchase", pool_id: Optional[str] = None) -> Dict[str, Any]:
        url = f"{self.base_url}/v1/orders"
        payload = {
            "sku_id": sku_id,
            "qty": qty,
            "kind": kind
        }
        if pool_id:
            payload["pool_id"] = pool_id

        try:
            res = requests.post(url, json=payload, headers=self._headers(), timeout=5)
            if res.status_code in [200, 201]:
                return res.json()
            return {"error": f"HTTP {res.status_code}"}
        except Exception as e:
            # Fallback mock for testing
            amount = 1200000 * qty
            return {
                "order_id": f"ord_mock_{sku_id}",
                "kind": kind,
                "sku_id": sku_id,
                "qty": qty,
                "status": "awaiting_payment",
                "payment_request": {
                    "payee_id": "pay_primefoods" if kind == "direct_purchase" else "pay_market_escrow",
                    "amount": {"amount_minor": amount, "currency": "NGN"},
                    "reference": f"ord_mock_{sku_id}",
                    "description": f"Order for {qty} x {sku_id}"
                },
                "simulated": True
            }
