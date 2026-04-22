"""Format store / bot state into readable strings for the LLM system prompt."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from config import settings


_STATUS_PHRASES: Dict[str, str] = {
    "pending": "is being processed",
    "processing": "is being prepared",
    "paid": "is paid and being processed",
    "shipped": "has been shipped",
    "fulfilled": "has been fulfilled",
    "delivered": "has been delivered",
    "in_transit": "is currently in transit",
    "dispatched": "has been dispatched",
    "confirmed": "has been confirmed",
    "returned": "was returned",
    "cancelled": "was cancelled",
    "canceled": "was cancelled",
    "refunded": "was refunded",
    "completed": "is completed",
    "failed": "has failed",
}


def _pick_str(d: Dict[str, Any], *keys: str) -> str:
    for k in keys:
        v = d.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()
    return ""


def _order_row_id_for_hints(order: Dict[str, Any]) -> str:
    for k in ("id", "order_id", "order_number", "number"):
        v = order.get(k)
        if v is not None and str(v).strip():
            return str(v).strip().lstrip("#")
    return ""


def _currency_suffix(order: Dict[str, Any], default: str = "AED") -> str:
    c = _pick_str(order, "currency", "currency_code", "curr")
    return c if c else default


def _money(order: Dict[str, Any], *amount_keys: str) -> str:
    raw = _pick_str(order, *amount_keys)
    if not raw:
        return ""
    u = raw.upper()
    if any(x in u for x in ("AED", "SAR", "PKR", "USD", "EUR", "GBP")):
        return raw
    return f"{raw} {_currency_suffix(order)}"


def _has_currency_token(s: str) -> bool:
    u = (s or "").upper()
    return any(x in u for x in ("AED", "SAR", "PKR", "USD", "EUR", "GBP"))


def _invoice_row_with_customer_hints(
    inv: Dict[str, Any],
    customer: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Copy invoice row; fill currency/country from customer when API omits them on invoices."""
    if not isinstance(inv, dict):
        return inv
    if not customer or not isinstance(customer, dict):
        return inv
    out = dict(inv)
    if not _pick_str(out, "currency", "currency_code", "curr"):
        c = _pick_str(customer, "currency", "currency_code", "curr")
        if c:
            out["currency"] = c
    if not _pick_str(out, "country", "country_code", "country_iso"):
        cc = _pick_str(customer, "country", "country_code", "country_iso")
        if cc:
            out["country"] = cc
    return out


def _invoice_currency(inv: Dict[str, Any], default: str = "AED") -> str:
    c = _pick_str(inv, "currency", "currency_code", "curr")
    if c:
        return c
    cc = _pick_str(inv, "country", "country_code", "country_iso")
    ccu = cc.upper()
    if ccu in ("AE", "UAE", "UNITED ARAB EMIRATES"):
        return "AED"
    if ccu in ("SA", "SAU", "SAUDI", "KSA", "SAUDI ARABIA"):
        return "SAR"
    if ccu in ("PK", "PAK", "PAKISTAN"):
        return "PKR"
    return default


def _amount_with_currency(amount: str, inv: Dict[str, Any]) -> str:
    if not amount:
        return ""
    if _has_currency_token(amount):
        return amount
    return f"{amount} {_invoice_currency(inv)}"


def format_order_for_llm(order: Dict[str, Any]) -> str:
    """Turn one order dict into short natural-language lines for the LLM context."""
    if not order:
        return ""
    order_num = order.get("order_number") or order.get("number") or order.get("id")
    status_raw = _pick_str(order, "status", "delivery_status", "order_status")
    if not status_raw and isinstance(order.get("tracking_result"), dict):
        status_raw = _pick_str(order["tracking_result"], "status", "delivery_status")
    status_key = (status_raw or "unknown").strip().lower()
    status_text = _STATUS_PHRASES.get(
        status_key,
        f"status is {status_raw or 'unknown'}",
    )
    lines: List[str] = []
    api_id = order.get("id")
    if api_id is not None and str(api_id).strip():
        lines.append(f"API order id: {api_id}")
    lines.append(f"Order #{order_num} {status_text}.")
    order_qty = _pick_str(order, "qty", "total_qty", "total_quantity")
    if order_qty:
        lines.append(f"Total quantity (order): {order_qty}")

    # Prefer seller invoice period date when present (aligns listed orders with invoice cycles).
    od_inv = _pick_str(order, "seller_invoice_row_date", "invoice_row_date")
    od_api = _pick_str(
        order,
        "createdon",
        "created_at",
        "order_date",
        "placed_at",
        "date",
        "booking_date",
    )
    if od_inv:
        lines.append(f"Order date (invoice period for this id): {od_inv}")
    elif od_api:
        lines.append(f"Order date: {od_api}")

    # Items (Arabia API returns items as a list of dicts with title, price, etc.)
    items = order.get("items")
    if isinstance(items, list) and items:
        item_lines: List[str] = []
        for it in items:
            if not isinstance(it, dict):
                continue
            title = _pick_str(it, "title", "name", "product_name")
            price = _pick_str(it, "price", "unit_price")
            qty = _pick_str(it, "qty", "quantity")
            variant = _pick_str(it, "variant", "option")
            part = title or "Unknown item"
            if variant:
                part += f" ({variant})"
            if qty:
                part += f" x{qty}"
            if price:
                pu = str(price).strip().upper()
                if not any(x in pu for x in ("AED", "SAR", "PKR", "USD")):
                    part += f" @ {price} {_currency_suffix(order)}"
                else:
                    part += f" @ {price}"
            item_lines.append(part)
        if item_lines:
            lines.append("Items: " + "; ".join(item_lines))

    # Shipping charges
    sc = _pick_str(order, "shipping_charges", "shipping_cost", "shipping")
    if sc:
        lines.append(f"Shipping charges: {_money(order, 'shipping_charges', 'shipping_cost', 'shipping') or sc}")

    # Profit
    profit = _pick_str(order, "profit", "seller_profit")
    if profit:
        lines.append(f"Profit: {_money(order, 'profit', 'seller_profit') or profit}")

    tn = _pick_str(order, "tracking_number", "tracking", "tracking_id", "awb_number")
    if tn:
        lines.append(f"Tracking: {tn}")
    car = _pick_str(order, "carrier", "shipping_carrier")
    if car:
        lines.append(f"Carrier: {car}")
    ed = _pick_str(order, "estimated_delivery", "delivery_estimate", "expected_delivery", "delivery_date")
    if ed:
        lines.append(f"Expected delivery: {ed}")
    ps = _pick_str(order, "payment_status")
    if ps:
        lines.append(f"Payment: {ps}")
    inv = _pick_str(order, "invoice_id", "invoice_number", "invoice_ref")
    if inv:
        lines.append(f"Invoice: {inv}")
    pen = _pick_str(order, "penalties", "penalty")
    if pen:
        lines.append(f"Penalties: {_money(order, 'penalties', 'penalty') or pen}")

    tot = _pick_str(order, "total_amount", "total", "amount", "net_total")
    if tot:
        lines.append(f"Total: {_money(order, 'total_amount', 'total', 'amount', 'net_total') or tot}")

    # Tracking result (Arabia API embeds this in order details)
    tr = order.get("tracking_result")
    if isinstance(tr, dict) and tr:
        tr_status = _pick_str(tr, "status", "delivery_status")
        if tr_status:
            lines.append(f"Tracking status: {tr_status}")

    # Return details
    ret = _pick_str(order, "return_status")
    if ret or status_key in ("returned",):
        rd = _pick_str(order, "return_date")
        if rd:
            lines.append(f"Return date: {rd}")
        rc = _pick_str(order, "return_charges")
        if rc:
            lines.append(f"Return charges: {_money(order, 'return_charges') or rc}")
        ri = _pick_str(order, "return_charge_invoice")
        if ri:
            lines.append(f"Return charges invoice: {ri}")
        rr = _pick_str(order, "return_reason")
        if rr:
            lines.append(f"Return reason: {rr}")

    # Cancellation details
    if status_key in ("cancelled", "canceled"):
        ct = _pick_str(order, "cancellation_type")
        if ct:
            lines.append(f"Cancellation type: {ct}")
        cr = _pick_str(order, "cancellation_reason")
        if cr:
            lines.append(f"Cancellation reason: {cr}")

    return "\n".join(lines)


def format_orders_summary_for_llm(orders: Optional[List[Dict[str, Any]]]) -> str:
    if not orders:
        return "No orders are listed in the provided context for this turn."
    parts = []
    for o in orders:
        line = format_order_for_llm(o if isinstance(o, dict) else {})
        if line:
            parts.append(line)
    return "\n\n".join(parts) if parts else "No orders are listed in the provided context for this turn."


def format_order_discovery_one_liner(order: Dict[str, Any]) -> str:
    """One line for order-discovery lists: id, date, status, optional tracking (no address/profit)."""
    if not order:
        return ""
    num = order.get("order_number") or order.get("number") or order.get("id") or "?"
    placed = _pick_str(
        order,
        "seller_invoice_row_date",
        "invoice_row_date",
        "createdon",
        "created_at",
        "order_date",
        "placed_at",
        "date",
        "booking_date",
    )
    status_raw = _pick_str(order, "status", "delivery_status", "order_status")
    if not status_raw and isinstance(order.get("tracking_result"), dict):
        status_raw = _pick_str(order["tracking_result"], "status", "delivery_status")
    status_disp = status_raw or "Unknown"
    tr = _pick_str(order, "tracking_number", "tracking", "tracking_id", "awb_number")
    head = f"Order #{num} placed on {placed}." if placed else f"Order #{num}."
    bits = [head, f"Status: {status_disp}."]
    if tr:
        bits.append(f"Tracking: {tr}.")
    return " ".join(bits)


def format_order_discovery_for_llm(fetch_ctx: Dict[str, Any]) -> str:
    """30/90/365-day buckets from ``fetch_customer_context`` for ORDER DISCOVERY RULES."""
    if not isinstance(fetch_ctx, dict):
        return "Order discovery: (invalid fetch context)."
    o30 = fetch_ctx.get("orders_last_30_days")
    o90 = fetch_ctx.get("orders_last_90_days")
    o365 = fetch_ctx.get("orders_last_365_days")
    if not isinstance(o30, list):
        o30 = []
    if not isinstance(o90, list):
        o90 = []
    if not isinstance(o365, list):
        o365 = []
    has_orders = bool(fetch_ctx.get("has_orders"))
    linked = bool(fetch_ctx.get("is_store_customer"))

    if not linked:
        return (
            "Order discovery: store customer not linked in context — buckets empty; "
            "do not invent orders. Follow **Customer identity** rules."
        )
    ro = fetch_ctx.get("recent_orders")
    ro_list = ro if isinstance(ro, list) else []
    if not has_orders and not o30 and not o90 and not o365 and ro_list:
        return (
            "Order discovery: all time-window buckets are empty, but **recent_orders** still lists "
            f"{len(ro_list)} row(s). Dates may be outside the rolling 365-day UTC window or not parsed — "
            "do **not** use Step 4 “no orders” wording; take up to 5 newest rows from **Orders** using the "
            "same one-line discovery format, then ask which order they want details for."
        )
    if not has_orders and not o30 and not o90 and not o365:
        return (
            "Order discovery: has_orders is false and all buckets are empty — use Step 4 (no orders) wording "
            "only if **Orders** is also empty. If **Invoices** show order_ids, mention invoice activity without "
            "contradicting empty buckets."
        )

    lines: List[str] = [
        "Order discovery (backend bucketed; rolling UTC windows on parsed order/invoice dates):",
        f"- has_orders: {has_orders}",
        f"- orders_last_30_days: count={len(o30)} (newest first below, up to 12)",
    ]
    for o in o30[:12]:
        if isinstance(o, dict):
            lines.append(f"  {format_order_discovery_one_liner(o)}")
    lines.append(f"- orders_last_90_days: count={len(o90)} (up to 12)")
    for o in o90[:12]:
        if isinstance(o, dict):
            lines.append(f"  {format_order_discovery_one_liner(o)}")
    lines.append(f"- orders_last_365_days: count={len(o365)} (up to 20)")
    for o in o365[:20]:
        if isinstance(o, dict):
            lines.append(f"  {format_order_discovery_one_liner(o)}")
    lines.append(
        "For user-facing lists without an order number: follow ORDER DISCOVERY RULES — at most 5 orders, "
        "newest first, exact line format from the rules; pick rows from the appropriate non-empty bucket."
    )
    oreq = fetch_ctx.get("orders_requested_range")
    if isinstance(oreq, dict) and oreq.get("date_from") and oreq.get("date_to"):
        cnt = int(oreq.get("order_count") or 0)
        lines.append(
            f"**Requested range (from customer wording):** {oreq.get('label') or ''} "
            f"({oreq.get('date_from')} … {oreq.get('date_to')}), order_count={cnt}, "
            f"has_more={bool(oreq.get('has_more'))}, truncated={bool(oreq.get('truncated'))}."
        )
        lines.append(
            "For this turn, prefer **HANDLING LARGE ORDER REQUESTS** rules: state the total count, "
            "then up to 10 one-line samples from **summary rows** below (newest first), then offer CSV or next batch."
        )
        for o in (oreq.get("summary_orders") or [])[:12]:
            if isinstance(o, dict):
                lines.append(f"  {format_order_discovery_one_liner(o)}")
    return "\n".join(lines)


def _pay_status_label(raw: str) -> str:
    s = (raw or "").strip().lower()
    if s in ("yes", "paid", "true", "1", "y"):
        return "Paid"
    if s in ("no", "unpaid", "false", "0", "n"):
        return "Unpaid"
    return raw or "unknown"


def format_single_invoice_for_llm(inv: Dict[str, Any]) -> str:
    """One invoice row (merchant /customers/invoice or /orders/{id}/invoice)."""
    if not inv:
        return ""
    inv_date = _pick_str(inv, "date", "invoice_date", "created_at")
    inv_items = _pick_str(inv, "no_of_items", "item_count", "items_count")
    inv_payable = _pick_str(inv, "payable", "amount", "total")
    raw_ps = _pick_str(inv, "pay_status", "payment_status", "status")
    inv_id = _pick_str(inv, "id", "invoice_id", "invoice_no", "number")
    penalties = _pick_str(inv, "penalties", "penalty")
    order_ids = inv.get("order_ids")
    parts: List[str] = []
    if inv_id:
        parts.append(f"invoice #{inv_id}")
    if inv_date:
        parts.append(f"date {inv_date}")
    if inv_items:
        parts.append(f"items {inv_items}")
    cur = _invoice_currency(inv)
    inv_net = _pick_str(inv, "net_total", "net")
    if inv_net:
        parts.append(f"net_total {_amount_with_currency(inv_net, inv)}")
    inv_profit = _pick_str(inv, "profit")
    if inv_profit:
        parts.append(f"profit {_amount_with_currency(inv_profit, inv)}")
    if inv_payable:
        parts.append(f"payable {_amount_with_currency(inv_payable, inv)}")
    if raw_ps:
        parts.append(f"payment {_pay_status_label(raw_ps)} (raw: {raw_ps})")
    if penalties:
        parts.append(f"penalties {_amount_with_currency(penalties, inv)}")
    if isinstance(order_ids, list) and order_ids:
        n = len(order_ids)
        sample = [str(x) for x in order_ids[:5]]
        if n > len(sample):
            parts.append(
                f"Contains {n} orders; sample ids: {', '.join(sample)}. "
                f"(Do not list all ids; offer details by invoice date or support.)"
            )
        else:
            parts.append(f"order_ids: {', '.join(sample)}")
    return " | ".join(parts) if parts else str(inv)[:200]


def format_invoice_llm_compact(inv: Dict[str, Any], *, sample_n: int = 5) -> str:
    """One invoice row, WhatsApp-friendly (short id sample, no huge id dumps)."""
    if not inv:
        return ""
    inv_date = _pick_str(inv, "date", "invoice_date", "created_at")
    inv_items = _pick_str(inv, "no_of_items", "item_count", "items_count")
    inv_payable = _pick_str(inv, "payable", "net_payable", "amount")
    raw_ps = _pick_str(inv, "pay_status", "payment_status", "status")
    inv_net = _pick_str(inv, "net_total", "net")
    inv_profit = _pick_str(inv, "profit")
    penalties = _pick_str(inv, "penalties", "penalty")
    order_ids = inv.get("order_ids") if isinstance(inv.get("order_ids"), list) else []
    bits: List[str] = []
    if inv_date:
        bits.append(inv_date)
    if inv_items:
        bits.append(f"{inv_items} items")
    if inv_payable:
        bits.append(f"payable {_amount_with_currency(inv_payable, inv)}")
    if inv_net and inv_net != inv_payable:
        bits.append(f"net {_amount_with_currency(inv_net, inv)}")
    if inv_profit:
        bits.append(f"profit {_amount_with_currency(inv_profit, inv)}")
    if penalties:
        bits.append(f"penalties {_amount_with_currency(penalties, inv)}")
    if raw_ps:
        bits.append(_pay_status_label(raw_ps))
    head = " | ".join(bits) if bits else ""
    n = len(order_ids)
    if n and sample_n >= 0:
        sample = [str(x) for x in order_ids[:sample_n]]
        if n > len(sample):
            tail = (
                f"Contains {n} orders. Latest: {', '.join(sample)}. "
                f"(Do not paste all ids; offer full list via email/support or ask which invoice date to expand.)"
            )
        else:
            tail = f"Orders: {', '.join(sample)}"
        return f"{head} — {tail}" if head else tail
    return head


def format_order_invoice_match_hints(
    orders: Optional[List[Dict[str, Any]]],
    invoices: Optional[List[Dict[str, Any]]],
) -> str:
    """Explicit mapping: each listed order → invoice period (Roman Urdu / follow-up invoice questions)."""
    if not orders:
        return ""
    date_by_oid: Dict[str, str] = {}
    listed_oids: List[str] = []
    for o in orders:
        if not isinstance(o, dict):
            continue
        oid = _order_row_id_for_hints(o)
        if not oid:
            continue
        listed_oids.append(oid)
        d = _pick_str(o, "seller_invoice_row_date", "invoice_row_date")
        if d:
            date_by_oid[oid] = d
    if not listed_oids:
        return ""
    inv_list = invoices if isinstance(invoices, list) else []
    missing = [oid for oid in listed_oids if oid not in date_by_oid]
    if missing and inv_list:
        for inv in inv_list:
            if not isinstance(inv, dict):
                continue
            inv_date = _pick_str(inv, "date", "invoice_date")
            raw = inv.get("order_ids")
            if not isinstance(raw, list) or not inv_date:
                continue
            for x in raw:
                ox = str(x).strip().lstrip("#")
                if ox in missing and ox not in date_by_oid:
                    date_by_oid[ox] = inv_date
    lines: List[str] = [
        "Order ↔ invoice (each order above → which invoice period it appears on):",
    ]
    n = 0
    for oid in listed_oids:
        d = date_by_oid.get(oid)
        if not d:
            continue
        lines.append(f"- Order #{oid} is in the {d} invoice.")
        n += 1
    if n == 0:
        return ""
    lines.append(
        "For amounts and pay status per invoice date, use the **Invoices** summary; do not paste long order-id lists."
    )
    return "\n".join(lines)


def format_invoices_summary_for_llm(
    invoices: Optional[List[Dict[str, Any]]],
    *,
    max_rows: int = 12,
    sample_ids: int = 5,
    customer: Optional[Dict[str, Any]] = None,
) -> str:
    """Compact invoice list for LLM / WhatsApp-length replies."""
    if not invoices:
        return "No invoice rows in context for this turn."
    lines: List[str] = [
        f"Invoices ({len(invoices)} periods). Summarize briefly; offer line-by-line detail when user names a date.",
    ]
    for inv in invoices[:max_rows]:
        if not isinstance(inv, dict):
            continue
        row = format_invoice_llm_compact(
            _invoice_row_with_customer_hints(inv, customer),
            sample_n=sample_ids,
        )
        if row:
            lines.append(f"• {row}")
    if len(invoices) > max_rows:
        lines.append(f"(+{len(invoices) - max_rows} more invoice periods not expanded — offer support for full export.)")
    lines.append(
        "For 'which invoice contains order #X?', use the sample order ids on each line or the Order ↔ invoice block."
    )
    return "\n".join(lines)


def format_tracking_payload_for_llm(
    tracking: Optional[Dict[str, Any]],
    *,
    label: str = "Tracking",
) -> str:
    """Normalize GET /orders/{id}/tracking or GET /tracking/{id} payloads."""
    if not isinstance(tracking, dict) or not tracking:
        return ""
    tid = _pick_str(tracking, "tracking_number", "id", "awb", "awb_number")
    st = _pick_str(tracking, "status", "delivery_status")
    shipped_ref = _pick_str(tracking, "shipped_ref", "reference")
    parts = [f"{label}: "]
    if tid:
        parts.append(f"number {tid}")
    if st:
        parts.append(f"status {st}")
    if shipped_ref:
        parts.append(f"shipped_ref {shipped_ref}")
    tr = tracking.get("tracking_result")
    if isinstance(tr, dict) and tr:
        trs = _pick_str(tr, "status", "delivery_status", "detail")
        if trs:
            parts.append(f"tracking_result {trs}")
    return " ".join(parts).strip()


def build_customer_identity_summary(
    fetch_ctx: Dict[str, Any],
    bot_flow: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Explain merchant linkage vs scripted-bot verification for the model.
    `fetch_ctx` is the dict returned from AIOrchestrator.fetch_customer_context.
    """
    lines: List[str] = []
    err = fetch_ctx.get("store_context_error")
    if err:
        lines.append(
            f"Store API error while loading customer/orders: {err}. "
            "Do not claim store data was successfully retrieved."
        )

    cust = fetch_ctx.get("customer") if isinstance(fetch_ctx.get("customer"), dict) else {}
    store_linked = bool(fetch_ctx.get("is_store_customer"))
    vmethod = fetch_ctx.get("verification_method") or "none"

    if store_linked:
        lines.append(
            f"Merchant/store: customer record linked via {vmethod} "
            f"(store customer id {cust.get('id')}, name: {cust.get('name') or 'n/a'}). "
            "You may use recent_orders from context for personal order questions. "
            "If **Orders** is empty but **Invoices** lists order_ids, summarize invoice periods "
            "and those order numbers — do not say there are no orders."
        )
    else:
        lines.append(
            "Merchant/store: no customer record linked for this phone in the store API. "
            "Do not invent orders or account details from the store."
        )

    bf = bot_flow if isinstance(bot_flow, dict) else {}
    kind = bf.get("customer_kind")
    script_verified = bool(bf.get("verified"))
    sid_bf = bf.get("seller_id")
    if sid_bf is not None and str(sid_bf).strip() and kind == "existing":
        lines.append(
            f"Bot session: seller_id {str(sid_bf).strip()} is on file — for order/invoice follow-ups, use store "
            "context; do not ask the customer to complete email/mobile verification again unless they are clearly "
            "on a different account."
        )

    if kind == "existing":
        if script_verified:
            lines.append(
                "Scripted chat bot: user chose EXISTING customer and completed the in-chat "
                "verification step (lightweight; not bank KYC). They may expect order help — "
                "still only use merchant order list when store is linked; otherwise ask for "
                "an order number or offer **support** — never suggest /reset as a fix for missing data."
            )
        elif bool(getattr(settings, "customer_bot_bypass_script_verification", False)):
            lines.append(
                "Scripted chat bot: user is on the EXISTING-customer path and email/OTP/mobile "
                "verification is temporarily OFF in settings. The bot collects order numbers "
                "for lookups instead. Do not ask them to complete email OTP verification or "
                "send /reset for that reason alone; guide them to share an order number if they "
                "need order help and store data is not linked."
            )
        else:
            lines.append(
                "Scripted chat bot: user chose EXISTING customer but has NOT completed the "
                "bot verification step — treat as UNVERIFIED for account/order answers from "
                "the script's point of view. Say they should complete verification in the chat "
                "flow; do not tell them to use /reset to fix missing orders or invoices."
            )
    elif kind == "new":
        lines.append(
            "Scripted chat bot: user chose NEW customer. Do not assume store order history."
        )
    else:
        lines.append(
            "Scripted chat bot: user has not completed new vs existing selection (or state cleared)."
        )

    sid = fetch_ctx.get("seller_id")
    if sid:
        lines.append(f"Seller linkage: seller_id {sid} is available for scoped store lookups.")

    tracking = fetch_ctx.get("tracking_detail")
    if isinstance(tracking, dict) and tracking:
        tline = format_tracking_payload_for_llm(tracking, label="AWB / tracking number lookup")
        if tline:
            lines.append(tline)

    invoices = fetch_ctx.get("invoices")
    if isinstance(invoices, list) and invoices:
        lines.append(
            f"Invoices: {len(invoices)} row(s) — full detail is in the **Invoices** context block below."
        )

    ot = fetch_ctx.get("order_tracking")
    if isinstance(ot, dict) and ot:
        tline = format_tracking_payload_for_llm(
            ot,
            label="Order-scoped tracking (GET /orders/{id}/tracking)",
        )
        if tline:
            lines.append(tline)

    oi = fetch_ctx.get("order_invoice")
    if isinstance(oi, dict) and oi:
        iline = format_single_invoice_for_llm(
            _invoice_row_with_customer_hints(oi, cust),
        )
        if iline:
            lines.append(f"Order-scoped invoice (GET /orders/{{id}}/invoice): {iline}")

    faq = fetch_ctx.get("faq_entries")
    if isinstance(faq, list) and faq:
        faq_lines: List[str] = []
        for item in faq[:5]:
            if not isinstance(item, dict):
                continue
            q = str(item.get("question") or item.get("title") or "").strip()
            a = str(item.get("answer") or item.get("description") or "").strip()
            if q and a:
                faq_lines.append(f"Q: {q} | A: {a[:180]}")
            elif q:
                faq_lines.append(f"Q: {q}")
        if faq_lines:
            lines.append("FAQ excerpts:\n" + "\n".join(faq_lines))

    return "\n".join(lines)
