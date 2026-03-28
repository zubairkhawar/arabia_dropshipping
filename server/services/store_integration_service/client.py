from typing import Optional, List, Dict, Any

import httpx

from config import settings


class StoreIntegrationClient:
    """
    Thin HTTP client that talks to the merchant's API instead of their database.

    All methods here should be safe, read-only lookups that our AI and routing
    layer can call for live store/customer data.
    """

    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None):
        # These defaults can be overridden per-tenant / per-store later
        raw = base_url if base_url is not None else settings.client_api_base_url
        self.base_url = (raw or "").strip() or None
        self.api_key = api_key if api_key is not None else settings.client_api_key
        bt = settings.client_api_bearer_token
        self.bearer_token = (bt.strip() if isinstance(bt, str) and bt.strip() else None)

    def _headers(self) -> Dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"
        elif self.api_key:
            headers["X-API-Key"] = self.api_key
        return headers

    async def get_customer_by_phone(self, phone: str) -> Optional[Dict[str, Any]]:
        """
        GET /customers?phone={phone}
        Returns the first matching customer or None.
        """
        if not self.base_url:
            return None
        async with httpx.AsyncClient(base_url=self.base_url, headers=self._headers(), timeout=10.0) as client:
            resp = await client.get("/customers", params={"phone": phone})
            resp.raise_for_status()
            data = resp.json()
            items: List[Dict[str, Any]] = data.get("data") or []
            return items[0] if items else None

    async def get_recent_orders_for_customer(self, customer_id: str, limit: int = 3) -> List[Dict[str, Any]]:
        """
        GET /customers/{customer_id}/orders?limit={limit}
        """
        if not self.base_url:
            return []
        async with httpx.AsyncClient(base_url=self.base_url, headers=self._headers(), timeout=10.0) as client:
            resp = await client.get(f"/customers/{customer_id}/orders", params={"limit": limit})
            resp.raise_for_status()
            data = resp.json()
            return data.get("data") or []

    async def get_order_by_number(self, order_number: str) -> Optional[Dict[str, Any]]:
        """
        GET /orders/by-number/{order_number}
        """
        if not self.base_url:
            return None
        async with httpx.AsyncClient(base_url=self.base_url, headers=self._headers(), timeout=10.0) as client:
            resp = await client.get(f"/orders/by-number/{order_number}")
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()

    async def get_order_by_id(self, order_id: str) -> Optional[Dict[str, Any]]:
        """
        GET /orders/{order_id} (e.g. Arabia backend /v1/orders/123432).
        """
        if not self.base_url:
            return None
        oid = (order_id or "").strip()
        if not oid:
            return None
        try:
            async with httpx.AsyncClient(base_url=self.base_url, headers=self._headers(), timeout=10.0) as client:
                resp = await client.get(f"/orders/{oid}")
                if resp.status_code == 404:
                    return None
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPError:
            return None

