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
from config import MARKET_URL, OWNER_TOKEN, DEMO_MODE

class MarketClient:
    def __init__(self, base_url: str = MARKET_URL, token: str = OWNER_TOKEN):
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
            res = requests.get(url, headers=self._headers(), timeout=10)
            res.raise_for_status()
            if res.status_code == 200:
                return res.json().get("products", [])
            return []
        except requests.RequestException:
            if not DEMO_MODE:
                raise
            return []

    def get_inventory(self) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/v1/inventory"
        try:
            res = requests.get(url, headers=self._headers(), timeout=10)
            res.raise_for_status()
            if res.status_code == 200:
                return res.json().get("inventory", [])
            return []
        except requests.RequestException:
            if not DEMO_MODE:
                raise
            return [
                {"sku_id": "sku_noodles_carton", "sku_name": "Instant Noodles", "stock": 12, "days_cover": 2.4, "reorder_point": 25},
                {"sku_id": "sku_rice_50kg", "sku_name": "Parboiled Rice 50kg", "stock": 4, "days_cover": 1.8, "reorder_point": 10},
                {"sku_id": "sku_cooking_oil_5l", "sku_name": "Vegetable Cooking Oil 5L", "stock": 18, "days_cover": 4.7, "reorder_point": 20}
            ]

    def get_pools(self) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/v1/pools"
        try:
            res = requests.get(url, headers=self._headers(), timeout=10)
            res.raise_for_status()
            if res.status_code == 200:
                return res.json().get("pools", [])
            return []
        except requests.RequestException:
            if not DEMO_MODE:
                raise
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

    def create_order(self, sku_id: str, qty: int, kind: str = "direct", pool_id: Optional[str] = None) -> Dict[str, Any]:
        payload = {"sku_id": sku_id, "qty": qty, "kind": kind}
        if pool_id:
            payload["pool_id"] = pool_id
        res = requests.post(f"{self.base_url}/v1/orders", json=payload, headers=self._headers(), timeout=10)
        res.raise_for_status()
        return res.json()

    def update_order_payment(self, order_id: str, intent_id: Optional[str]) -> Dict[str, Any]:
        payload = {"intent_id": intent_id}
        res = requests.post(f"{self.base_url}/v1/orders/{order_id}/payment", json=payload, headers=self._headers(), timeout=10)
        res.raise_for_status()
        return res.json()

    def reset_demo_orders(self) -> None:
        res = requests.post(f"{self.base_url}/demo/v1/reset", headers=self._headers(), timeout=10)
        res.raise_for_status()
