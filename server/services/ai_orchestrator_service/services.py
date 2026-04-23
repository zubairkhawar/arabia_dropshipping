import logging
import re
from datetime import date, datetime, timedelta
from typing import Optional, Dict, Any, Set, List, Tuple

from services.human_handoff_intent import wants_human_agent
from services.order_date_range import (
    message_suggests_store_date_window,
    parse_date_range_from_message,
)
from services.store_integration_service.client import (
    StoreIntegrationClient,
    merchant_seller_scope_from_row,
    merge_tracking_payload_into_order,
    order_row_primary_id,
    synthetic_order_stub_from_invoices,
)

logger = logging.getLogger(__name__)

_MAX_STORE_ORDERS_IN_CONTEXT = 5000
_MAX_CONTEXT_DATE_SPAN_DAYS = 731


def _store_context_date_window(days: int = 120) -> Tuple[str, str]:
    """Default date_from / date_to for invoice + orders/list calls (UTC calendar days)."""
    end = datetime.utcnow().date()
    start = end - timedelta(days=max(30, min(int(days), 730)))
    return start.isoformat(), end.isoformat()


def _invoices_from_merchant_payload(inv_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not isinstance(inv_payload, dict) or not inv_payload:
        return []
    invs = inv_payload.get("invoices")
    if isinstance(invs, list):
        return [x for x in invs if isinstance(x, dict)]
    one = inv_payload.get("invoice")
    if isinstance(one, dict):
        return [one]
    return []


def _order_ids_from_invoices(invoices: List[Dict[str, Any]], max_ids: int = 40) -> List[str]:
    out: List[str] = []
    for inv in invoices:
        raw = inv.get("order_ids")
        if not isinstance(raw, list):
            continue
        for x in raw:
            s = str(x).strip()
            if s and s not in out:
                out.append(s)
            if len(out) >= max_ids:
                return out
    return out


def _message_requests_full_invoice_history(message_text: str) -> bool:
    t = (message_text or "").strip().lower()
    if not t:
        return False
    keys = (
        "all invoices",
        "all my invoices",
        "all invoice",
        "saari invoice",
        "saari invoices",
        "sari invoice",
        "sari invoices",
        "invoice history",
        "total payment",
        "total payments",
        "total paid",
        "payment sum",
        "invoice sum",
        "kitni pay ho chuki",
        "pay hochuki",
        "ab tak pay",
    )
    return any(k in t for k in keys)


def _message_requests_total_order_count(message_text: str) -> bool:
    t = (message_text or "").strip().lower()
    if not t:
        return False
    keys = (
        "total order",
        "total orders",
        "order count",
        "orders in total",
        "kitne order",
        "kitnay order",
    )
    return any(k in t for k in keys)


def _safe_amount_float(v: Any) -> float:
    if v is None:
        return 0.0
    s = str(v).strip()
    if not s:
        return 0.0
    cleaned = re.sub(r"[^0-9.\-]", "", s)
    if not cleaned:
        return 0.0
    try:
        return float(cleaned)
    except (TypeError, ValueError):
        return 0.0


def _is_paid_invoice_status(v: Any) -> bool:
    s = str(v or "").strip().lower()
    return s in {"yes", "paid", "true", "1", "y"}


def _resolve_merchant_seller_id(
    flow: Optional[Dict[str, Any]],
    customer: Optional[Dict[str, Any]],
) -> Optional[str]:
    f = flow if isinstance(flow, dict) else {}
    raw = f.get("seller_id")
    if raw is not None and str(raw).strip():
        return str(raw).strip()
    return merchant_seller_scope_from_row(customer if isinstance(customer, dict) else None)


def _attach_invoice_dates_to_orders(
    orders: List[Dict[str, Any]],
    invoices: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Map each order id to the invoice row ``date`` string when that id appears in order_ids."""
    date_by_oid: Dict[str, str] = {}
    for inv in invoices or []:
        if not isinstance(inv, dict):
            continue
        d = str(inv.get("date") or "").strip()
        oids = inv.get("order_ids")
        if not d or not isinstance(oids, list):
            continue
        for x in oids:
            oid = str(x).strip().lstrip("#")
            if oid:
                date_by_oid[oid] = d
    out: List[Dict[str, Any]] = []
    for o in orders:
        if not isinstance(o, dict):
            out.append(o)
            continue
        oid = order_row_primary_id(o)
        inv_d = date_by_oid.get(oid)
        if inv_d:
            no = dict(o)
            no["seller_invoice_row_date"] = inv_d
            out.append(no)
        else:
            out.append(o)
    return out


def _customer_record_is_linked(customer: Optional[Dict[str, Any]]) -> bool:
    """True if the store payload clearly identifies a customer row.

    Some merchant APIs return ``_id`` or ``customer_id`` but not ``id``;
    the old ``customer.get("id")`` check alone made ``is_store_customer`` false
    and the LLM thought no account was linked even after script verification.
    """
    if not isinstance(customer, dict) or not customer:
        return False
    for k in ("id", "_id", "customer_id", "user_id"):
        v = customer.get(k)
        if v is not None and str(v).strip():
            return True
    return False


def _extract_order_id_from_message(message: str, phone: Optional[str]) -> Optional[str]:
    """
    Best-effort order reference from free text (e.g. "order 123432", "#123432").
    Avoids treating the full WhatsApp phone number as an order id when possible.
    """
    if not (message or "").strip():
        return None
    phone_digits = re.sub(r"\D", "", phone or "")
    for pattern in (
        r"(?i)\b(?:order|ord)\s+id\s*[#:\-]?\s*(\d{4,14})\b",
        r"(?i)\b(?:order|ord)\s*[#:\-]?\s*(\d{4,14})\b",
        r"#\s*(\d{4,14})\b",
    ):
        m = re.search(pattern, message)
        if m:
            return m.group(1)
    for m in re.finditer(r"\b(\d{5,12})\b", message):
        cand = m.group(1)
        if phone_digits and cand == phone_digits:
            continue
        if len(phone_digits) >= 10 and cand in phone_digits and len(cand) >= 8:
            continue
        return cand
    return None


def _extract_tracking_id_from_message(message: str) -> Optional[str]:
    text = (message or "").strip()
    if not text:
        return None
    m = re.search(r"\b([A-Z]{2}\d{6,20})\b", text.upper())
    if m:
        return m.group(1)
    return None


def _parse_flexible_date_string(s: str) -> Optional[date]:
    """Best-effort parse for Arabia order/invoice date strings."""
    raw = (s or "").strip()
    if not raw:
        return None
    head = raw.split("T")[0].split()[0] if raw else ""
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", head):
        try:
            return datetime.strptime(head, "%Y-%m-%d").date()
        except ValueError:
            pass
    for candidate in (raw, raw[:22].strip()):
        for fmt in ("%d-%b-%Y", "%d-%B-%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(candidate, fmt).date()
            except ValueError:
                continue
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    try:
        norm = raw.replace("Z", "+00:00").replace(" ", "T")
        return datetime.fromisoformat(norm[:19]).date()
    except (TypeError, ValueError):
        pass
    return None


def _parse_order_activity_date(order: Dict[str, Any]) -> Optional[date]:
    if not isinstance(order, dict):
        return None
    for k in (
        "seller_invoice_row_date",
        "invoice_row_date",
        "createdon",
        "created_at",
        "order_date",
        "placed_at",
        "date",
        "booking_date",
    ):
        v = order.get(k)
        if v is None:
            continue
        parsed = _parse_flexible_date_string(str(v))
        if parsed:
            return parsed
    return None


def _sort_orders_by_activity_desc(orders: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Newest first; orders without a parseable date sort last."""

    def _key(o: Dict[str, Any]) -> Tuple[int, int]:
        dt = _parse_order_activity_date(o)
        if dt is None:
            return (1, 0)
        return (0, -dt.toordinal())

    return sorted(
        [o for o in orders if isinstance(o, dict)],
        key=_key,
    )


def _partition_orders_by_recency(
    orders: List[Dict[str, Any]],
    *,
    today: Optional[date] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Rolling UTC calendar windows: 30 / 90 / 365 days.
    Rows with no parseable date appear only in the 365-day bucket.
    """
    day = today or datetime.utcnow().date()
    d30 = day - timedelta(days=30)
    d90 = day - timedelta(days=90)
    d365 = day - timedelta(days=365)
    sorted_rows = _sort_orders_by_activity_desc(orders)

    def _in_window(o: Dict[str, Any], start: date) -> bool:
        dt = _parse_order_activity_date(o)
        if dt is None:
            return False
        return dt >= start

    o30 = [o for o in sorted_rows if _in_window(o, d30)]
    o90 = [o for o in sorted_rows if _in_window(o, d90)]
    o365 = [
        o
        for o in sorted_rows
        if _in_window(o, d365) or _parse_order_activity_date(o) is None
    ]
    return o30, o90, o365


class AIOrchestrator:
    """
    Central place where we orchestrate:
    - language detection
    - customer/store lookups via the client's API
    - escalation heuristics

    LLM calls use langchain_bot.ArabiaLangChainBot (not this class).
    """

    def __init__(self):
        self.store_client = StoreIntegrationClient()

    async def detect_language(self, text: str) -> str:
        """
        Detect language for customer chat routing.
        Returns one of: arabic | english | roman_urdu
        """
        source = (text or "").strip()
        if not source:
            return "english"

        # Arabic script block (Arabic + supplemental ranges)
        if any(
            ("\u0600" <= ch <= "\u06FF")
            or ("\u0750" <= ch <= "\u077F")
            or ("\u08A0" <= ch <= "\u08FF")
            for ch in source
        ):
            return "arabic"

        lowered = source.lower()
        # Normalize punctuation so we can score words reliably.
        normalized = re.sub(r"[^a-z0-9\s]", " ", lowered)
        tokens = [t for t in normalized.split() if t]
        token_set = set(tokens)

        # Common Roman Urdu / Roman Hindi words and variants.
        roman_ur_words: Set[str] = {
            "kya",
            "kahan",
            "kahaan",
            "mujhay",
            "mujhe",
            "salam",
            "salaam",
            "sallam",
            "assalam",
            "assalamu",
            "alaikum",
            "alikum",
            "walaikum",
            "walaykum",
            "aoa",
            "kaisa",
            "kaise",
            "haal",
            "hain",
            "hai",
            "han",
            "hun",
            "ho",
            "rhy",
            "rahy",
            "rahe",
            "rha",
            "raha",
            "kr",
            "kar",
            "krna",
            "karna",
            "karo",
            "kerna",
            "ap",
            "aap",
            "tum",
            "mera",
            "meri",
            "mjy",
            "please",
            "plz",
            "bhai",
            "yar",
            "yaar",
            "acha",
            "achha",
            "theek",
            "thik",
            "thk",
            "nahi",
            "nhi",
            "nahin",
            "hanji",
            "ji",
            "shukriya",
            "jazakallah",
            "kab",
            "kis",
            "kyun",
            "q",
            "qa",
            # Common short Roman Urdu words / connectors
            "k",
            "ka",
            "ki",
            "ke",
            "kay",
            "ko",
            "se",
            "pe",
            "par",
            "ya",
            "aur",
            "or",
            "bhi",
            "toh",
            "to",
            "na",
            "wo",
            "woh",
            "ye",
            "yeh",
            "jo",
            "ab",
            "abhi",
            # Verbs / question words
            "btao",
            "batao",
            "bataen",
            "batayen",
            "btaen",
            "batain",
            "btain",
            "hota",
            "hoti",
            "hoga",
            "hogi",
            "tha",
            "thi",
            "gaya",
            "gayi",
            "dena",
            "dedo",
            "lena",
            "lelo",
            "chahiye",
            "chaiye",
            "chahte",
            "sakta",
            "sakti",
            "sakte",
            "kitna",
            "kitne",
            "kitni",
            "kaise",
            "konsa",
            "konsi",
            "kaunsa",
            "kaunsi",
            # Domain-common
            "paisa",
            "paise",
            "wala",
            "wali",
            "wale",
            "kaam",
            "zaroorat",
            "zarurat",
            "madad",
            "masla",
            "maslay",
            "problem",
            "lagta",
            "lagti",
            "lagay",
            "lagaen",
            "milta",
            "milti",
            "mila",
            "mili",
            "ata",
            "ati",
            "aye",
            "ayega",
            "ayegi",
            "samajh",
            "samjh",
        }
        roman_ur_bigrams = {
            ("kya", "haal"),
            ("kya", "kar"),
            ("kya", "kr"),
            ("kr", "rhy"),
            ("kar", "rahe"),
            ("kaise", "ho"),
            ("ap", "ka"),
            ("aap", "ka"),
            ("k", "baare"),
            ("ke", "baare"),
            ("k", "charges"),
            ("k", "return"),
            ("return", "charges"),
            ("mujhe", "btao"),
            ("mujhe", "batao"),
            ("ye", "btao"),
            ("ye", "batao"),
        }

        # Short connectors only score when combined with other Roman Urdu tokens.
        _roman_ur_weak: Set[str] = {
            "k", "ka", "ki", "ke", "kay", "ko", "se", "pe", "par",
            "ya", "or", "to", "na", "ye", "jo", "ab", "ho",
        }

        roman_score = 0
        english_score = 0

        for token in tokens:
            if token in roman_ur_words:
                roman_score += 1 if token in _roman_ur_weak else 2
            # lightweight english hints
            if token in {
                "hello",
                "hi",
                "thanks",
                "thank",
                "please",
                "where",
                "when",
                "order",
                "delivery",
                "status",
                "update",
                "support",
                "agent",
                "help",
            }:
                english_score += 1

        for i in range(len(tokens) - 1):
            pair = (tokens[i], tokens[i + 1])
            if pair in roman_ur_bigrams:
                roman_score += 3

        # Strong pattern boosts
        if "kya" in token_set and ("haal" in token_set or "kr" in token_set or "kar" in token_set):
            roman_score += 3
        if {"rhy", "ho"} <= token_set or {"rahe", "ho"} <= token_set:
            roman_score += 2
        # "btao" / "batao" is a strong Roman Urdu signal
        if token_set & {"btao", "batao", "bataen", "batayen", "btaen"}:
            roman_score += 3
        # "k" / "ke" / "kay" adjacent to a noun is a Roman Urdu possessive pattern
        if token_set & {"k", "ke", "kay"} and token_set & {"charges", "return", "baare", "order", "tracking", "delivery", "price", "rate"}:
            roman_score += 3
        # "aur" combined with anything else Roman Urdu
        if "aur" in token_set and token_set & roman_ur_words - _roman_ur_weak - {"aur"}:
            roman_score += 2

        if roman_score >= max(2, english_score + 1):
            return "roman_urdu"

        return "english"

    async def fetch_customer_context(
        self,
        phone: Optional[str],
        message_text: Optional[str] = None,
        bot_flow: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Resolve customer and recent orders via the merchant API, plus a single order
        lookup when the user message mentions an order id (e.g. GET /v1/orders/{id}).

        For personalized answers (is_store_customer, orders), the merchant must implement
        e.g. GET /customers?phone=… and GET /customers/{id}/orders — see StoreIntegrationClient.
        If those are missing, the bot still runs but store-linked context stays empty.
        """
        customer: Optional[Dict[str, Any]] = None
        orders: list = []
        store_context_error: Optional[str] = None
        verification_method = "none"
        faq_entries: list = []
        tracking_detail: Optional[Dict[str, Any]] = None
        invoices: list = []
        seller_id: Optional[str] = None
        order_tracking: Optional[Dict[str, Any]] = None
        order_invoice: Optional[Dict[str, Any]] = None

        flow = bot_flow if isinstance(bot_flow, dict) else {}
        vc = flow.get("verified_customer")
        if isinstance(vc, dict):
            customer = vc
            verification_method = "email_code"

        seller_id = _resolve_merchant_seller_id(flow, customer)

        use_parsed_window = False
        parsed_msg_range: Optional[Dict[str, Any]] = None
        orders_truncated = False
        date_from = ""
        date_to = ""
        invoice_date_from = ""
        invoice_date_to = ""
        full_invoice_history_mode = False
        total_order_count_mode = False

        # Only use Arabia APIs: orders by id, tracking, faq, invoice by seller_id
        if seller_id:
            total_order_count_mode = _message_requests_total_order_count(message_text or "")
            parsed_msg_range = parse_date_range_from_message(message_text or "")
            use_parsed_window = bool(
                parsed_msg_range
                and message_suggests_store_date_window(message_text or "")
            )
            if use_parsed_window and parsed_msg_range:
                date_from = str(parsed_msg_range.get("date_from") or "").strip()[:10]
                date_to = str(parsed_msg_range.get("date_to") or "").strip()[:10]
                try:
                    d_from = date.fromisoformat(date_from)
                    d_to = date.fromisoformat(date_to)
                    if d_to < d_from:
                        d_from, d_to = d_to, d_from
                        date_from, date_to = d_from.isoformat(), d_to.isoformat()
                    if (d_to - d_from).days > _MAX_CONTEXT_DATE_SPAN_DAYS:
                        d_from = d_to - timedelta(days=_MAX_CONTEXT_DATE_SPAN_DAYS)
                        date_from = d_from.isoformat()
                except (TypeError, ValueError):
                    date_from, date_to = _store_context_date_window(365)
                    use_parsed_window = False
                    parsed_msg_range = None
            else:
                date_from, date_to = _store_context_date_window(365)
                parsed_msg_range = None
                use_parsed_window = False

            if _message_requests_full_invoice_history(message_text or ""):
                full_invoice_history_mode = True
                invoice_date_from = "2020-01-01"
                invoice_date_to = datetime.utcnow().date().isoformat()
            else:
                invoice_date_from, invoice_date_to = date_from, date_to

            orders_truncated = False
            try:
                inv_payload = await self.store_client.get_invoice_by_seller_id(
                    seller_id,
                    date_from=invoice_date_from,
                    date_to=invoice_date_to,
                    all_invoices=full_invoice_history_mode,
                )
                if not _invoices_from_merchant_payload(inv_payload):
                    inv_payload = await self.store_client.get_invoice_by_seller_id(
                        seller_id,
                        date_from=invoice_date_from,
                        date_to=invoice_date_to,
                        all_invoices=True,
                    )
                if isinstance(inv_payload.get("orders"), list):
                    orders = [x for x in inv_payload.get("orders") if isinstance(x, dict)]
                elif isinstance(inv_payload.get("data"), list):
                    orders = [x for x in inv_payload.get("data") if isinstance(x, dict)]
                invoices = _invoices_from_merchant_payload(inv_payload)
                if total_order_count_mode:
                    try:
                        orders = await self.store_client.get_orders_all(seller_id)
                    except Exception as exc:  # noqa: BLE001
                        logger.exception("Store API total-order-count unscoped fetch failed")
                        store_context_error = (store_context_error or "") + f" orders_all_total:{exc!s}"[:220]
                # Invoice payload often has no ``orders`` array — use /orders/all with a
                # sensible window (merchant APIs may return NOT_FOUND for ad-hoc single days).
                if not orders:
                    try:
                        if total_order_count_mode:
                            orders = await self.store_client.get_orders_all(seller_id)
                        else:
                            orders = await self.store_client.get_orders_all(
                                seller_id,
                                date_from=date_from,
                                date_to=date_to,
                            )
                    except Exception as exc:  # noqa: BLE001
                        logger.exception("Store API orders/all with window failed")
                        store_context_error = (store_context_error or "") + f" orders_all:{exc!s}"[:220]
                if orders and len(orders) > _MAX_STORE_ORDERS_IN_CONTEXT:
                    orders = orders[:_MAX_STORE_ORDERS_IN_CONTEXT]
                    orders_truncated = True
                if not orders:
                    try:
                        orders = await self.store_client.get_orders_all(seller_id)
                    except Exception as exc:  # noqa: BLE001
                        logger.exception("Store API orders/all unscoped fallback failed")
                        store_context_error = (store_context_error or "") + f" orders_all_u:{exc!s}"[:220]
                if not orders and invoices:
                    oid_list = _order_ids_from_invoices(invoices, max_ids=24)
                    if oid_list:
                        try:
                            orders = await self.store_client.fetch_orders_for_order_ids(
                                seller_id,
                                oid_list,
                                max_orders=15,
                            )
                        except Exception as exc:  # noqa: BLE001
                            logger.exception("Store API hydrate orders from invoice ids failed")
                            store_context_error = (
                                (store_context_error or "") + f" orders_hydrate:{exc!s}"
                            )[:220]
            except Exception as exc:  # noqa: BLE001
                logger.exception("Store API invoice by seller_id failed")
                store_context_error = f"invoice_fetch:{exc!s}"[:220]
                if not orders:
                    try:
                        orders = await self.store_client.get_orders_all(seller_id)
                    except Exception as exc2:  # noqa: BLE001
                        logger.exception("Store API orders/all after invoice failure")
                        store_context_error = (
                            (store_context_error or "") + f" orders_all:{exc2!s}"
                        )[:220]

        if not seller_id and phone:
            # Preserve compatibility for channels that still only provide phone.
            try:
                customer = await self.store_client.get_customer_by_phone(phone)
                if customer and customer.get("id"):
                    verification_method = "phone"
                    sid_phone = merchant_seller_scope_from_row(customer)
                    if sid_phone:
                        seller_id = sid_phone
            except Exception as exc:  # noqa: BLE001
                logger.exception("Store API customer by phone failed")
                store_context_error = (store_context_error or "") + f" customer_fetch:{exc!s}"[:220]

        order_id = _extract_order_id_from_message(message_text or "", phone)
        if order_id:
            try:
                detail = await self.store_client.get_order_by_id(order_id, seller_id=seller_id)
                if not detail:
                    detail = await self.store_client.get_order_by_number(
                        order_id, seller_id=seller_id
                    )
                if not detail and seller_id:
                    detail = await self.store_client.resolve_order_by_reference(
                        order_id, seller_id
                    )
                if not detail and invoices:
                    detail = synthetic_order_stub_from_invoices(invoices, order_id)
                if detail:
                    orders = [detail] + [
                        o for o in orders if str(o.get("id", o)) != str(detail.get("id", detail))
                    ]
                    try:
                        order_tracking = await self.store_client.get_order_tracking(
                            order_id, seller_id=seller_id
                        )
                    except Exception as exc:  # noqa: BLE001
                        logger.exception("Store API order tracking failed")
                        store_context_error = (
                            (store_context_error or "") + f" order_trk:{exc!s}"
                        )[:220]
                    try:
                        inv_raw = await self.store_client.get_order_invoice_mapping(order_id)
                        if isinstance(inv_raw, dict):
                            oinv = inv_raw.get("invoice")
                            order_invoice = (
                                oinv if isinstance(oinv, dict) else inv_raw
                            )
                    except Exception as exc:  # noqa: BLE001
                        logger.exception("Store API order invoice mapping failed")
                        store_context_error = (
                            (store_context_error or "") + f" order_inv:{exc!s}"
                        )[:220]
            except Exception as exc:  # noqa: BLE001
                logger.exception("Store API order by id failed")
                store_context_error = (store_context_error or "") + f" order_fetch:{exc!s}"[:220]

        tracking_id = _extract_tracking_id_from_message(message_text or "")
        if tracking_id:
            try:
                tracking_detail = await self.store_client.get_tracking_status(
                    tracking_id,
                    seller_id=seller_id,
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception("Store API tracking failed")
                store_context_error = (store_context_error or "") + f" tracking_fetch:{exc!s}"[:220]

        try:
            faq_entries = await self.store_client.get_faq()
        except Exception as exc:  # noqa: BLE001
            logger.exception("Store API faq failed")
            store_context_error = (store_context_error or "") + f" faq_fetch:{exc!s}"[:220]

        store_linked = _customer_record_is_linked(customer)
        if (
            not store_linked
            and isinstance(flow, dict)
            and flow.get("verified")
            and isinstance(customer, dict)
            and customer
            and seller_id
        ):
            # Script verified email+mobile and we have a non-empty store customer
            # payload + seller scope, but no canonical id field the API uses.
            store_linked = True

        if seller_id and orders and invoices:
            orders = _attach_invoice_dates_to_orders(orders, invoices)
        if seller_id and orders:
            try:
                orders = await self.store_client.enrich_orders_with_tracking(
                    seller_id,
                    orders,
                    max_orders=15,
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception("enrich_orders_with_tracking failed")
                store_context_error = (store_context_error or "") + f" tr_enrich:{exc!s}"[:120]

        if (
            order_id
            and isinstance(order_tracking, dict)
            and order_tracking
            and orders
        ):
            oid_key = str(order_id).strip().lstrip("#")
            for i, o in enumerate(orders):
                if not isinstance(o, dict):
                    continue
                if order_row_primary_id(o) == oid_key:
                    orders[i] = merge_tracking_payload_into_order(o, order_tracking)
                    break

        orders_last_30: List[Dict[str, Any]] = []
        orders_last_90: List[Dict[str, Any]] = []
        orders_last_365: List[Dict[str, Any]] = []
        if seller_id and store_linked and orders:
            orders_last_30, orders_last_90, orders_last_365 = _partition_orders_by_recency(
                orders
            )
        has_orders = bool(orders_last_365)
        invoice_order_ids: Set[str] = set()
        total_paid_amount = 0.0
        for inv in invoices:
            if not isinstance(inv, dict):
                continue
            raw_oids = inv.get("order_ids")
            if isinstance(raw_oids, list):
                for oid in raw_oids:
                    sid = str(oid or "").strip().lstrip("#")
                    if sid:
                        invoice_order_ids.add(sid)
            if _is_paid_invoice_status(inv.get("pay_status")):
                total_paid_amount += _safe_amount_float(
                    inv.get("payable") or inv.get("net_total") or inv.get("invoice_payable")
                )
        order_ids_from_orders: Set[str] = set()
        for row in orders:
            if not isinstance(row, dict):
                continue
            oid = order_row_primary_id(row)
            if oid:
                order_ids_from_orders.add(oid)
        total_order_count = max(len(order_ids_from_orders), len(invoice_order_ids))
        if total_order_count <= 0:
            total_order_count = len(orders or [])

        orders_requested_range: Optional[Dict[str, Any]] = None
        if (
            use_parsed_window
            and parsed_msg_range
            and seller_id
            and store_linked
        ):
            summary_slice = orders[:10] if isinstance(orders, list) else []
            orders_requested_range = {
                "label": parsed_msg_range.get("label"),
                "date_from": date_from,
                "date_to": date_to,
                "order_count": len(orders) if isinstance(orders, list) else 0,
                "summary_orders": summary_slice,
                "has_more": bool(isinstance(orders, list) and len(orders) > 10),
                "truncated": orders_truncated,
            }

        return {
            "customer": customer or {},
            "recent_orders": orders,
            "is_store_customer": store_linked,
            "verification_method": verification_method,
            "store_context_error": store_context_error,
            "seller_id": seller_id,
            "tracking_detail": tracking_detail or {},
            "faq_entries": faq_entries,
            "invoices": invoices,
            "order_tracking": order_tracking or {},
            "order_invoice": order_invoice or {},
            "orders_last_30_days": orders_last_30,
            "orders_last_90_days": orders_last_90,
            "orders_last_365_days": orders_last_365,
            "has_orders": has_orders,
            "context_store_date_from": (date_from or None) if seller_id else None,
            "context_store_date_to": (date_to or None) if seller_id else None,
            "orders_requested_range": orders_requested_range,
            "full_invoice_history_mode": full_invoice_history_mode,
            "total_paid_amount": round(total_paid_amount, 2),
            "total_order_count": total_order_count,
        }

    async def should_escalate(self, message: str) -> bool:
        """Determine if conversation should be escalated to agent."""
        return wants_human_agent(message)
