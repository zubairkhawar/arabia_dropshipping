"""Format store / bot state into readable strings for the LLM system prompt."""
from __future__ import annotations

from typing import Any, Dict, List, Optional


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
    lines = [f"Order #{order_num} {status_text}."]

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
            "You may use recent_orders from context for personal order questions."
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
                "order number or direct them to the bot order flow or /reset."
            )
        else:
            lines.append(
                "Scripted chat bot: user chose EXISTING customer but has NOT completed the "
                "bot verification step — treat as UNVERIFIED for account/order answers from "
                "the script's point of view. Say they should complete verification in the chat "
                "flow, or send /reset and pick Existing customer again."
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
        tracking_id = tracking.get("tracking_number") or tracking.get("id") or "tracking"
        tracking_status = tracking.get("status") or tracking.get("delivery_status") or "unknown"
        lines.append(f"Tracking lookup: {tracking_id} status is {tracking_status}.")

    invoices = fetch_ctx.get("invoices")
    if isinstance(invoices, list) and invoices:
        lines.append(f"Invoices context: {len(invoices)} invoice records are available.")

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
