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
    "cancelled": "was cancelled",
    "canceled": "was cancelled",
    "refunded": "was refunded",
    "completed": "is completed",
}


def format_order_for_llm(order: Dict[str, Any]) -> str:
    """Turn one order dict into short natural-language lines."""
    if not order:
        return ""
    order_num = order.get("order_number") or order.get("number") or order.get("id")
    status = (order.get("status") or "unknown").strip().lower()
    status_text = _STATUS_PHRASES.get(status, f"status is {order.get('status') or 'unknown'}")
    lines = [f"Order #{order_num} {status_text}."]
    tn = order.get("tracking_number") or order.get("tracking")
    if tn:
        lines.append(f"Tracking: {tn}")
    car = order.get("carrier") or order.get("shipping_carrier")
    if car:
        lines.append(f"Carrier: {car}")
    ed = order.get("estimated_delivery") or order.get("delivery_estimate")
    if ed:
        lines.append(f"Expected delivery: {ed}")
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

    return "\n".join(lines)
