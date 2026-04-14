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
        Legacy method retained for compatibility.
        Arabia endpoint requires email+mobile, so phone-only lookup is not supported.
        """
        return None

    async def send_verification_code(self, email: str) -> bool:
        """
        POST /customers/send-verification-code
        Body: {"email": "..."}
        """
        if not self.base_url:
            return False
        e = (email or "").strip().lower()
        if not e:
            return False
        try:
            async with httpx.AsyncClient(base_url=self.base_url, headers=self._headers(), timeout=10.0) as client:
                resp = await client.post("/customers/send-verification-code", json={"email": e})
                if resp.status_code >= 400:
                    return False
                payload = resp.json() if resp.content else {}
                if isinstance(payload, dict) and payload.get("success") is False:
                    return False
                return True
        except httpx.HTTPError:
            return False

    async def verify_code(self, email: str, code: str) -> bool:
        """
        POST /customers/verify-code
        Body: {"email": "...", "code": "..."}
        """
        if not self.base_url:
            return False
        e = (email or "").strip().lower()
        c = (code or "").strip()
        if not e or not c:
            return False
        try:
            async with httpx.AsyncClient(base_url=self.base_url, headers=self._headers(), timeout=10.0) as client:
                resp = await client.post("/customers/verify-code", json={"email": e, "code": c})
                if resp.status_code >= 400:
                    return False
                payload = resp.json() if resp.content else {}
                if not isinstance(payload, dict):
                    return False
                # Contract can be {"verified": true} or {"success": true, ...}
                if payload.get("verified") is True:
                    return True
                if payload.get("success") is True and payload.get("verified") is not False:
                    return True
                return False
        except httpx.HTTPError:
            return False

    async def get_customer_by_email_mobile(self, email: str, mobile: str) -> Optional[Dict[str, Any]]:
        """
        GET /customers?email={email}&mobile={mobile}
        Returns customer payload or None.
        """
        if not self.base_url:
            return None
        e = (email or "").strip().lower()
        m = (mobile or "").strip()
        if not e or not m:
            return None
        try:
            async with httpx.AsyncClient(base_url=self.base_url, headers=self._headers(), timeout=10.0) as client:
                resp = await client.get("/customers", params={"email": e, "mobile": m})
                if resp.status_code == 404:
                    return None
                if resp.status_code >= 400:
                    return None
                payload = resp.json()
                if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
                    return payload.get("data")
                if isinstance(payload, dict):
                    return payload
                return None
        except httpx.HTTPError:
            return None

    async def get_recent_orders_for_customer(self, customer_id: str, limit: int = 3) -> List[Dict[str, Any]]:
        """
        Legacy method retained for compatibility with previous orchestrator flow.
        """
        return []

    async def get_order_by_number(self, order_number: str) -> Optional[Dict[str, Any]]:
        """
        Arabia API exposes GET /orders/{order_id}; order_number delegates to same route.
        """
        return await self.get_order_by_id(order_number)

    async def get_order_by_id(self, order_id: str, seller_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        GET /orders/{order_id}
        """
        if not self.base_url:
            return None
        oid = (order_id or "").strip()
        if not oid:
            return None
        try:
            params: Dict[str, Any] = {}
            sid = (seller_id or "").strip()
            if sid:
                params["seller_id"] = sid
            async with httpx.AsyncClient(base_url=self.base_url, headers=self._headers(), timeout=10.0) as client:
                resp = await client.get(f"/orders/{oid}", params=params or None)
                if resp.status_code == 404:
                    return None
                resp.raise_for_status()
                payload = resp.json()
                if isinstance(payload, dict) and "data" in payload:
                    return payload.get("data")
                return payload
        except httpx.HTTPError:
            return None

    async def get_tracking_status(self, tracking_id: str, seller_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        GET /tracking/{tracking_id}
        """
        if not self.base_url:
            return None
        tid = (tracking_id or "").strip()
        if not tid:
            return None
        try:
            params: Dict[str, Any] = {}
            sid = (seller_id or "").strip()
            if sid:
                params["seller_id"] = sid
            async with httpx.AsyncClient(base_url=self.base_url, headers=self._headers(), timeout=10.0) as client:
                resp = await client.get(f"/tracking/{tid}", params=params or None)
                if resp.status_code == 404:
                    return None
                resp.raise_for_status()
                payload = resp.json()
                if isinstance(payload, dict) and "data" in payload:
                    return payload.get("data")
                return payload if isinstance(payload, dict) else None
        except httpx.HTTPError:
            return None

    async def get_faq(self) -> List[Dict[str, Any]]:
        """
        GET /faq
        """
        if not self.base_url:
            return []
        try:
            async with httpx.AsyncClient(base_url=self.base_url, headers=self._headers(), timeout=10.0) as client:
                resp = await client.get("/faq")
                if resp.status_code >= 400:
                    return []
                payload = resp.json()
                if isinstance(payload, dict) and isinstance(payload.get("data"), list):
                    return [x for x in payload.get("data") if isinstance(x, dict)]
                if isinstance(payload, list):
                    return [x for x in payload if isinstance(x, dict)]
                return []
        except httpx.HTTPError:
            return []

    async def get_invoice_by_seller_id(self, seller_id: str) -> Dict[str, Any]:
        """
        GET /customers/invoice?seller_id={seller_id}
        """
        if not self.base_url:
            return {}
        sid = (seller_id or "").strip()
        if not sid:
            return {}
        try:
            async with httpx.AsyncClient(base_url=self.base_url, headers=self._headers(), timeout=10.0) as client:
                resp = await client.get("/customers/invoice", params={"seller_id": sid})
                if resp.status_code >= 400:
                    return {}
                payload = resp.json()
                if isinstance(payload, dict):
                    data = payload.get("data")
                    if isinstance(data, dict):
                        return data
                    return payload
                return {}
        except httpx.HTTPError:
            return {}

    async def get_orders_all(
        self,
        seller_id: str,
        month: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        GET /orders/all?seller_id=...
        """
        if not self.base_url:
            return []
        sid = (seller_id or "").strip()
        if not sid:
            return []
        params: Dict[str, Any] = {"seller_id": sid}
        if (month or "").strip():
            params["month"] = month.strip()
        if (date_from or "").strip():
            params["date_from"] = date_from.strip()
        if (date_to or "").strip():
            params["date_to"] = date_to.strip()
        try:
            async with httpx.AsyncClient(base_url=self.base_url, headers=self._headers(), timeout=10.0) as client:
                resp = await client.get("/orders/all", params=params)
                if resp.status_code >= 400:
                    return []
                payload = resp.json()
                if isinstance(payload, dict) and isinstance(payload.get("data"), list):
                    return [x for x in payload.get("data") if isinstance(x, dict)]
                if isinstance(payload, list):
                    return [x for x in payload if isinstance(x, dict)]
                return []
        except httpx.HTTPError:
            return []

    async def get_invoices(self, seller_id: str) -> List[Dict[str, Any]]:
        """
        GET /invoices?seller_id=...
        Falls back to /customers/invoice if /invoices is not provided.
        """
        if not self.base_url:
            return []
        sid = (seller_id or "").strip()
        if not sid:
            return []
        try:
            async with httpx.AsyncClient(base_url=self.base_url, headers=self._headers(), timeout=10.0) as client:
                resp = await client.get("/invoices", params={"seller_id": sid})
                if resp.status_code < 400:
                    payload = resp.json()
                    if isinstance(payload, dict) and isinstance(payload.get("data"), list):
                        return [x for x in payload.get("data") if isinstance(x, dict)]
                    if isinstance(payload, list):
                        return [x for x in payload if isinstance(x, dict)]
        except httpx.HTTPError:
            pass
        invoice_payload = await self.get_invoice_by_seller_id(sid)
        if isinstance(invoice_payload.get("invoices"), list):
            return [x for x in invoice_payload.get("invoices") if isinstance(x, dict)]
        return []

