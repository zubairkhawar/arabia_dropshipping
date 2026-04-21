import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple

import httpx

from config import settings
from services.phone_lookup_variants import mobile_lookup_variants
from services.verification_service import send_verification_code_local, verify_code_local

logger = logging.getLogger(__name__)


def _orders_list_date_window(days: int = 120) -> Tuple[str, str]:
    """UTC date_from / date_to for /orders/all when the API requires a window."""
    end = datetime.utcnow().date()
    start = end - timedelta(days=max(30, min(int(days), 730)))
    return start.isoformat(), end.isoformat()


class StoreIntegrationClient:
    """
    Thin HTTP client that talks to the merchant's API instead of their database.

    All methods here should be safe, read-only lookups that our AI and routing
    layer can call for live store/customer data.

    Common Arabia backend routes used here:
    - ``GET /customers?email=&mobile=`` — resolve customer + ``seller_id``
    - ``GET /customers/invoice?seller_id=&date_from=&date_to=&all=1`` — invoice rows + ``order_ids``
    - ``GET /orders/all?seller_id=&date_from=&date_to=`` — list orders in a date window
    - ``GET /orders/{order_id}?seller_id=`` — single order
    - ``GET /orders/{order_id}/tracking`` / ``GET /orders/{order_id}/invoice`` — scoped extras
    - :meth:`fetch_orders_for_order_ids` — multiple singles in parallel (batch hydration)
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
        Falls back to local SMTP when no external API is configured.
        """
        e = (email or "").strip().lower()
        if not e:
            logger.warning("send_verification_code called with empty email")
            return False
        if not self.base_url:
            logger.info("No CLIENT_API_BASE_URL; sending verification code via SMTP for %s", e)
            return send_verification_code_local(e)
        try:
            async with httpx.AsyncClient(base_url=self.base_url, headers=self._headers(), timeout=10.0) as client:
                resp = await client.post("/customers/send-verification-code", json={"email": e})
                if resp.status_code >= 400:
                    logger.warning(
                        "send_verification_code API failed for %s: status=%s body=%s",
                        e,
                        resp.status_code,
                        (resp.text or "")[:300],
                    )
                    logger.info(
                        "Falling back to local SMTP verification code for %s after API failure",
                        e,
                    )
                    return send_verification_code_local(e)
                payload = resp.json() if resp.content else {}
                if isinstance(payload, dict) and payload.get("success") is False:
                    logger.warning("send_verification_code API returned success=false for %s", e)
                    logger.info(
                        "Falling back to local SMTP verification code for %s after API success=false",
                        e,
                    )
                    return send_verification_code_local(e)
                logger.info("send_verification_code API success for %s", e)
                return True
        except httpx.HTTPError as exc:
            logger.error("send_verification_code API error for %s: %s", e, exc)
            logger.info("Falling back to local SMTP verification code for %s after API exception", e)
            return send_verification_code_local(e)

    async def verify_code(self, email: str, code: str) -> bool:
        """
        POST /customers/verify-code
        Body: {"email": "...", "code": "..."}
        Falls back to local in-memory store when no external API is configured.
        """
        e = (email or "").strip().lower()
        c = (code or "").strip()
        if not e or not c:
            logger.warning("verify_code called with missing email/code")
            return False
        if not self.base_url:
            return verify_code_local(e, c)
        try:
            async with httpx.AsyncClient(base_url=self.base_url, headers=self._headers(), timeout=10.0) as client:
                resp = await client.post("/customers/verify-code", json={"email": e, "code": c})
                if resp.status_code >= 400:
                    logger.warning(
                        "verify_code API failed for %s: status=%s body=%s",
                        e,
                        resp.status_code,
                        (resp.text or "")[:300],
                    )
                    logger.info("Falling back to local verify_code for %s after API failure", e)
                    return verify_code_local(e, c)
                payload = resp.json() if resp.content else {}
                if not isinstance(payload, dict):
                    logger.warning("verify_code API returned non-dict payload for %s", e)
                    logger.info("Falling back to local verify_code for %s after invalid API payload", e)
                    return verify_code_local(e, c)
                # Contract can be {"verified": true} or {"success": true, ...}
                if payload.get("verified") is True:
                    logger.info("verify_code API verified=true for %s", e)
                    return True
                if payload.get("success") is True and payload.get("verified") is not False:
                    logger.info("verify_code API success=true accepted for %s", e)
                    return True
                logger.info(
                    "verify_code API did not verify for %s; trying local fallback before reject",
                    e,
                )
                return verify_code_local(e, c)
        except httpx.HTTPError as exc:
            logger.error("verify_code API error for %s: %s", e, exc)
            logger.info("Falling back to local verify_code for %s after API exception", e)
            return verify_code_local(e, c)

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

    async def get_customer_by_email_mobile_first_hit(
        self, email: str, mobile_raw: str
    ) -> Optional[Dict[str, Any]]:
        """
        Try GET /customers with each common mobile format (local, +92…, 0092…, etc.)
        until one returns a customer.
        """
        for m in mobile_lookup_variants(mobile_raw):
            row = await self.get_customer_by_email_mobile(email, m)
            if row:
                return row
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

    async def get_order_tracking(
        self, order_id: str, seller_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        GET /orders/{order_id}/tracking
        Returns the live tracking status payload for an order, or None.
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
            async with httpx.AsyncClient(
                base_url=self.base_url, headers=self._headers(), timeout=10.0
            ) as client:
                resp = await client.get(f"/orders/{oid}/tracking", params=params or None)
                if resp.status_code == 404:
                    return None
                resp.raise_for_status()
                payload = resp.json()
                if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
                    return payload.get("data")
                return payload if isinstance(payload, dict) else None
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

    async def get_invoice_by_seller_id(
        self,
        seller_id: str,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        all_invoices: bool = False,
        invoice_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        GET /customers/invoice?seller_id={seller_id}
            [&date_from=YYYY-MM-DD&date_to=YYYY-MM-DD]
            [&all=1]
            [&invoice_id={id}]

        Returns the raw invoice payload. When `all_invoices` is True the
        response typically carries `invoices: [...]` with `total` count;
        otherwise it's a single latest-invoice object under `invoice`.
        """
        if not self.base_url:
            return {}
        sid = (seller_id or "").strip()
        if not sid and not (invoice_id or "").strip():
            return {}
        params: Dict[str, Any] = {}
        if sid:
            params["seller_id"] = sid
        if (date_from or "").strip():
            params["date_from"] = date_from.strip()
        if (date_to or "").strip():
            params["date_to"] = date_to.strip()
        if all_invoices:
            params["all"] = 1
        iid = (invoice_id or "").strip()
        if iid:
            params["invoice_id"] = iid
        try:
            async with httpx.AsyncClient(base_url=self.base_url, headers=self._headers(), timeout=10.0) as client:
                resp = await client.get("/customers/invoice", params=params)
                if resp.status_code >= 400:
                    return {}
                payload = resp.json()
                if isinstance(payload, dict) and payload.get("success") is False:
                    return {}
                if isinstance(payload, dict):
                    data = payload.get("data")
                    if isinstance(data, dict):
                        return data
                    return payload
                return {}
        except httpx.HTTPError:
            return {}

    async def get_order_invoice_mapping(
        self, order_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        GET /orders/{order_id}/invoice

        Returns the invoice that contains the given order, or None.
        The payload mirrors a single invoice object: typically
        `{"invoice": {date, payable, pay_status, order_ids, ...}}`.
        """
        if not self.base_url:
            return None
        oid = (order_id or "").strip()
        if not oid:
            return None
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url, headers=self._headers(), timeout=10.0
            ) as client:
                resp = await client.get(f"/orders/{oid}/invoice")
                if resp.status_code == 404:
                    return None
                resp.raise_for_status()
                payload = resp.json()
                if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
                    return payload.get("data")
                return payload if isinstance(payload, dict) else None
        except httpx.HTTPError:
            return None

    @staticmethod
    def _order_dict_identity_values(o: Dict[str, Any]) -> List[str]:
        """All string forms of id / order_number that might match user input."""
        out: List[str] = []
        for k in (
            "id",
            "_id",
            "order_id",
            "order_number",
            "number",
            "orderNo",
            "order_no",
        ):
            v = o.get(k)
            if v is None or v == "":
                continue
            s = str(v).strip()
            if s:
                out.append(s)
        return out

    async def resolve_order_by_reference(
        self, ref: str, seller_id: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        """
        When GET /orders/{ref} fails, the store may still key orders by an internal
        id while shoppers see a numeric ``order_number``. Scan GET /orders/all for
        this seller and return the row whose id / order_number matches ``ref``.
        """
        r = (ref or "").strip().lstrip("#")
        sid = (seller_id or "").strip()
        if not r or not sid:
            return None
        try:
            df, dt = _orders_list_date_window()
            orders = await self.get_orders_all(sid, date_from=df, date_to=dt)
            if not orders:
                orders = await self.get_orders_all(sid)
        except Exception:  # noqa: BLE001
            logger.exception("resolve_order_by_reference: get_orders_all failed for seller_id=%s", sid)
            return None
        for o in orders:
            if not isinstance(o, dict):
                continue
            for cand in self._order_dict_identity_values(o):
                if cand == r or cand.lstrip("#") == r:
                    return o
        return None

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
                if isinstance(payload, dict) and payload.get("success") is False:
                    return []
                if isinstance(payload, dict) and isinstance(payload.get("data"), list):
                    return [x for x in payload.get("data") if isinstance(x, dict)]
                if isinstance(payload, list):
                    return [x for x in payload if isinstance(x, dict)]
                return []
        except httpx.HTTPError:
            return []

    async def fetch_orders_for_order_ids(
        self,
        seller_id: str,
        order_ids: List[Any],
        *,
        max_orders: int = 15,
        max_concurrent: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Hydrate order rows by calling GET /orders/{order_id}?seller_id=... for each id.

        Use when /orders/all returns empty but invoice rows list ``order_ids``.
        """
        if not self.base_url:
            return []
        sid = (seller_id or "").strip()
        if not sid:
            return []
        unique: List[str] = []
        for raw in order_ids or []:
            s = str(raw).strip()
            if s and s not in unique:
                unique.append(s)
            if len(unique) >= max_orders:
                break
        if not unique:
            return []

        sem = asyncio.Semaphore(max(1, int(max_concurrent)))

        async def _one(oid: str) -> Optional[Dict[str, Any]]:
            async with sem:
                try:
                    return await self.get_order_by_id(oid, seller_id=sid)
                except Exception:  # noqa: BLE001
                    logger.exception("fetch_orders_for_order_ids failed for order_id=%s", oid)
                    return None

        results = await asyncio.gather(*[_one(o) for o in unique])
        return [r for r in results if isinstance(r, dict)]

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

