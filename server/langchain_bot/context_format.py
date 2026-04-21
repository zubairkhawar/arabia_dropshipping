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


def format_order_for_llm(order: Dict[str, Any]) -> str:
    """Turn one order dict into short natural-language lines for the LLM context."""
    if not order:
        return ""
    order_num = order.get("order_number") or order.get("number") or order.get("id")
    status = (order.get("status") or "unknown").strip().lower()
    status_text = _STATUS_PHRASES.get(status, f"status is {order.get('status') or 'unknown'}")
    lines: List[str] = []
    api_id = order.get("id")
    if api_id is not None and str(api_id).strip():
        lines.append(f"API order id: {api_id}")
    lines.append(f"Order #{order_num} {status_text}.")
    order_qty = _pick_str(order, "qty", "total_qty", "total_quantity")
    if order_qty:
        lines.append(f"Total quantity (order): {order_qty}")

    # Order date (Arabia API uses 'createdon')
    od = _pick_str(order, "createdon", "created_at", "order_date", "date")
    if od:
        lines.append(f"Order date: {od}")

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
                part += f" @ {price} AED"
            item_lines.append(part)
        if item_lines:
            lines.append("Items: " + "; ".join(item_lines))

    # Shipping charges
    sc = _pick_str(order, "shipping_charges", "shipping_cost", "shipping")
    if sc:
        lines.append(f"Shipping charges: {sc} AED")

    # Profit
    profit = _pick_str(order, "profit", "seller_profit")
    if profit:
        lines.append(f"Profit: {profit} AED")

    # Customer address / delivery info
    addr = _pick_str(order, "address", "delivery_address", "shipping_address")
    if addr:
        lines.append(f"Address: {addr}")
    mob = _pick_str(order, "mobile", "customer_phone")
    if mob:
        lines.append(f"Customer mobile: {mob}")

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
        lines.append(f"Penalties: {pen} AED")

    # Tracking result (Arabia API embeds this in order details)
    tr = order.get("tracking_result")
    if isinstance(tr, dict) and tr:
        tr_status = _pick_str(tr, "status", "delivery_status")
        if tr_status:
            lines.append(f"Tracking status: {tr_status}")

    # Return details
    ret = _pick_str(order, "return_status")
    if ret or status in ("returned",):
        rd = _pick_str(order, "return_date")
        if rd:
            lines.append(f"Return date: {rd}")
        rc = _pick_str(order, "return_charges")
        if rc:
            cur = _pick_str(order, "currency")
            lines.append(f"Return charges: {rc} {cur}".strip())
        ri = _pick_str(order, "return_charge_invoice")
        if ri:
            lines.append(f"Return charges invoice: {ri}")
        rr = _pick_str(order, "return_reason")
        if rr:
            lines.append(f"Return reason: {rr}")

    # Cancellation details
    if status in ("cancelled", "canceled"):
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
    inv_net = _pick_str(inv, "net_total", "net")
    if inv_net:
        parts.append(f"net_total {inv_net} AED")
    inv_profit = _pick_str(inv, "profit")
    if inv_profit:
        parts.append(f"profit {inv_profit} AED")
    if inv_payable:
        parts.append(f"payable {inv_payable} AED")
    if raw_ps:
        parts.append(f"payment {_pay_status_label(raw_ps)} (raw: {raw_ps})")
    if penalties:
        parts.append(f"penalties {penalties} AED")
    if isinstance(order_ids, list) and order_ids:
        ids = ", ".join(str(x) for x in order_ids[:20])
        more = f" (+{len(order_ids) - 20} more)" if len(order_ids) > 20 else ""
        parts.append(f"order_ids [{ids}{more}]")
    return " | ".join(parts) if parts else str(inv)[:200]


def format_invoices_summary_for_llm(
    invoices: Optional[List[Dict[str, Any]]],
    *,
    max_rows: int = 12,
) -> str:
    """All invoice rows for the seller — used as a dedicated LLM context block."""
    if not invoices:
        return "No invoice rows in context for this turn."
    lines: List[str] = []
    for inv in invoices[:max_rows]:
        if not isinstance(inv, dict):
            continue
        row = format_single_invoice_for_llm(inv)
        if row:
            lines.append(f"- {row}")
    if not lines:
        return "No invoice rows in context for this turn."
    head = (
        f"Invoice list ({len(invoices)} row(s); showing up to {max_rows}). "
        "Use order_ids to answer 'which invoice contains order #X?'; "
        "filter pay_status raw 'No' or Unpaid for unpaid-only questions."
    )
    return head + "\n" + "\n".join(lines)


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
        iline = format_single_invoice_for_llm(oi)
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
