"""
Tool handlers — the actual side-effecting code.

Each handler accepts:
  - validated_args: a Pydantic model instance (already passed schema validation)
  - ctx: ToolContext (db session, customer, conversation, lang, store_client, ...)
and returns a ``ToolResult``.

Handlers DO NOT trust the LLM. They:
  1. Re-validate verification state for account_data tools (defense in depth —
     the control plane already filtered, but a misconfigured registry shouldn't
     be the only thing standing between a hallucinated tool call and PII.)
  2. Call existing services (store_client, knowledge_service, etc.) — no
     duplication of business logic.
  3. Return compact, LLM-friendly payloads (the LLM sees the result string,
     so giant blobs waste tokens and confuse it).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from langchain_bot.tools import schemas as S
from langchain_bot.tools.registry import ToolResult

logger = logging.getLogger(__name__)


@dataclass
class ToolContext:
    """Everything a handler needs to do its job. Built once per orchestrator invocation."""

    db: Session
    tenant_id: int
    customer_phone: str
    conversation_id: Optional[int]
    language: str
    store_client: Any  # StoreIntegrationClient — typed as Any to avoid circular imports
    bot_flow: Dict[str, Any]  # the persisted flow dict (verification state, customer_kind, etc.)

    @property
    def is_verified(self) -> bool:
        return bool(self.bot_flow.get("verified"))

    @property
    def seller_id(self) -> Optional[str]:
        sid = self.bot_flow.get("seller_id")
        return str(sid) if sid else None


def _require_verified(ctx: ToolContext, tool_name: str) -> Optional[ToolResult]:
    if not ctx.is_verified or not ctx.seller_id:
        return ToolResult(
            ok=False,
            data={},
            error=(
                f"{tool_name} requires verified customer with seller_id; "
                "call start_verification first."
            ),
        )
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Handler: lookup_order
# ─────────────────────────────────────────────────────────────────────────────
async def handle_lookup_order(args: S.LookupOrderArgs, ctx: ToolContext) -> ToolResult:
    guard = _require_verified(ctx, "lookup_order")
    if guard:
        return guard
    order_id = args.order_id.lstrip("#").strip()
    # Defence in depth: even if the LLM ignores its prompt rule, refuse to
    # look up a clearly-phone-shaped string (10+ digits or leading 0/+ with
    # 10+ digits). Arabia order ids are 5–7 digits; anything longer is a
    # phone number, not an order. Returns 'not an order' so the LLM can
    # ack briefly instead of presenting a confusing 'order not found'.
    digits_only = "".join(c for c in order_id if c.isdigit())
    if len(digits_only) >= 10 or (len(digits_only) >= 10 and digits_only.startswith("0")):
        return ToolResult(
            ok=False,
            data={"requested": order_id},
            error="not_an_order_id_phone_shaped",
        )
    try:
        detail = await ctx.store_client.get_order_by_id(order_id, seller_id=ctx.seller_id)
        if not detail:
            detail = await ctx.store_client.get_order_by_number(order_id, seller_id=ctx.seller_id)
        if not detail:
            return ToolResult(ok=False, data={"requested_order_id": order_id}, error="order_not_found")
        # Enrich with tracking + invoice mapping when available.
        try:
            tracking = await ctx.store_client.get_order_tracking(order_id, seller_id=ctx.seller_id)
        except Exception:
            tracking = {}
        try:
            inv = await ctx.store_client.get_order_invoice_mapping(order_id)
            if isinstance(inv, dict):
                inv = inv.get("invoice", inv)
        except Exception:
            inv = {}
        return ToolResult(
            ok=True,
            data={"order": detail, "tracking": tracking or {}, "invoice": inv or {}},
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("lookup_order failed")
        return ToolResult(ok=False, data={}, error=f"store_api_error:{type(exc).__name__}")


# ─────────────────────────────────────────────────────────────────────────────
# Handler: lookup_orders_by_range
# ─────────────────────────────────────────────────────────────────────────────
def _aggregate_order_stats(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compact stats over a list of orders so the LLM can answer
    'profit of last 30 days' / 'returned orders kitny hain?' /
    'delivery ratio kya hai?' / 'top city kaunsi hai?' / 'best product?'
    without needing the full list (which can be hundreds of rows).
    """
    total_profit = 0.0
    total_shipping = 0.0
    total_qty = 0
    by_status: Dict[str, int] = {}
    by_city: Dict[str, int] = {}
    by_product: Dict[str, int] = {}     # qty across items
    by_month: Dict[str, int] = {}        # YYYY-MM → count
    profit_by_month: Dict[str, float] = {}
    tracking_numbers: List[str] = []
    delivered = 0
    returned = 0
    pending = 0
    cancelled = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        order_profit = _safe_float(row.get("profit"))
        total_profit += order_profit
        total_shipping += _safe_float(row.get("shipping_charges"))
        try:
            total_qty += int(row.get("qty") or 0)
        except (TypeError, ValueError):
            pass
        status_raw = (row.get("tracking_result") or row.get("status") or "").strip() or "Unknown"
        by_status[status_raw] = by_status.get(status_raw, 0) + 1
        s_low = status_raw.lower()
        if "deliver" in s_low and "return" not in s_low:
            delivered += 1
        elif "return" in s_low:
            returned += 1
        elif "cancel" in s_low:
            cancelled += 1
        else:
            pending += 1
        tn = (row.get("shipped_ref") or "").strip()
        if tn:
            tracking_numbers.append(tn)
        city = (row.get("city_name") or "").strip() or "Unknown"
        by_city[city] = by_city.get(city, 0) + 1
        items = row.get("items")
        if isinstance(items, list):
            for it in items:
                if not isinstance(it, dict):
                    continue
                title = (it.get("title") or "").strip() or "Unknown"
                try:
                    item_qty = int(it.get("qty") or 1)
                except (TypeError, ValueError):
                    item_qty = 1
                by_product[title] = by_product.get(title, 0) + item_qty
        # createdon = "YYYY-MM-DD HH:MM:SS"
        created = (row.get("createdon") or "").strip()
        if len(created) >= 7:
            ym = created[:7]
            by_month[ym] = by_month.get(ym, 0) + 1
            profit_by_month[ym] = round(profit_by_month.get(ym, 0.0) + order_profit, 2)

    total = len(rows)
    delivery_ratio_pct = round((delivered / total * 100), 2) if total else 0.0
    return_ratio_pct = round((returned / total * 100), 2) if total else 0.0
    cancel_ratio_pct = round((cancelled / total * 100), 2) if total else 0.0
    avg_profit = round((total_profit / total), 2) if total else 0.0
    avg_shipping = round((total_shipping / total), 2) if total else 0.0

    def _topn(d: Dict[str, Any], n: int = 5) -> List[Dict[str, Any]]:
        items = sorted(d.items(), key=lambda kv: kv[1], reverse=True)[:n]
        return [{"name": k, "count": v} for k, v in items]

    return {
        "total_profit": round(total_profit, 2),
        "total_shipping": round(total_shipping, 2),
        "total_qty": total_qty,
        "delivered": delivered,
        "returned": returned,
        "pending_or_other": pending,
        "cancelled": cancelled,
        "delivery_ratio_pct": delivery_ratio_pct,
        "return_ratio_pct": return_ratio_pct,
        "cancel_ratio_pct": cancel_ratio_pct,
        "avg_profit_per_order": avg_profit,
        "avg_shipping_per_order": avg_shipping,
        "by_status": by_status,
        "top_cities": _topn(by_city, 5),
        "top_products": _topn(by_product, 5),
        "by_month": by_month,
        "profit_by_month": profit_by_month,
        "tracking_numbers": tracking_numbers,
    }


async def handle_lookup_orders_by_range(
    args: S.LookupOrdersByRangeArgs, ctx: ToolContext
) -> ToolResult:
    guard = _require_verified(ctx, "lookup_orders_by_range")
    if guard:
        return guard
    if args.date_from > args.date_to:
        return ToolResult(ok=False, data={}, error="date_from is after date_to")
    try:
        rows = await ctx.store_client.get_orders_all(
            seller_id=ctx.seller_id,
            date_from=args.date_from.isoformat(),
            date_to=args.date_to.isoformat(),
        )
        rows = list(rows or [])
        truncated = len(rows) > 5
        agg = _aggregate_order_stats(rows)
        # Cap tracking_numbers list to avoid blowing the LLM context for huge ranges.
        tracking_capped = agg["tracking_numbers"][:50]
        return ToolResult(
            ok=True,
            data={
                "label": args.label or f"{args.date_from} to {args.date_to}",
                "date_from": args.date_from.isoformat(),
                "date_to": args.date_to.isoformat(),
                "total_count": len(rows),
                "sample": rows[:5],
                "truncated": truncated,
                "aggregate": {
                    "total_profit": agg["total_profit"],
                    "total_shipping": agg["total_shipping"],
                    "total_qty": agg["total_qty"],
                    "delivered": agg["delivered"],
                    "returned": agg["returned"],
                    "pending_or_other": agg["pending_or_other"],
                    "cancelled": agg["cancelled"],
                    "delivery_ratio_pct": agg["delivery_ratio_pct"],
                    "return_ratio_pct": agg["return_ratio_pct"],
                    "cancel_ratio_pct": agg["cancel_ratio_pct"],
                    "avg_profit_per_order": agg["avg_profit_per_order"],
                    "avg_shipping_per_order": agg["avg_shipping_per_order"],
                    "by_status": agg["by_status"],
                    "top_cities": agg["top_cities"],
                    "top_products": agg["top_products"],
                    "by_month": agg["by_month"],
                    "profit_by_month": agg["profit_by_month"],
                },
                "tracking_numbers": tracking_capped,
                "tracking_numbers_truncated": len(agg["tracking_numbers"]) > len(tracking_capped),
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("lookup_orders_by_range failed")
        return ToolResult(ok=False, data={}, error=f"store_api_error:{type(exc).__name__}")


# ─────────────────────────────────────────────────────────────────────────────
# Handler: list_invoices
# ─────────────────────────────────────────────────────────────────────────────
def _is_paid(status: Any) -> bool:
    s = str(status or "").strip().lower()
    return s in ("yes", "paid", "true", "1")


_WIDE_RANGE_FROM = "2020-01-01"


def _wide_today() -> str:
    return date.today().isoformat()


async def handle_list_invoices(args: S.ListInvoicesArgs, ctx: ToolContext) -> ToolResult:
    guard = _require_verified(ctx, "list_invoices")
    if guard:
        return guard
    try:
        # Without dates the upstream API returns only the single latest invoice;
        # use a wide range so 'list invoices' / 'kitni invoices' is accurate.
        df = args.date_from.isoformat() if args.date_from else _WIDE_RANGE_FROM
        dt = args.date_to.isoformat() if args.date_to else _wide_today()
        rows = await ctx.store_client.get_invoice_by_seller_id(
            seller_id=ctx.seller_id,
            date_from=df,
            date_to=dt,
        )
        rows = [r for r in (rows or []) if isinstance(r, dict)]
        if args.only_unpaid:
            rows = [r for r in rows if not _is_paid(r.get("pay_status"))]
        return ToolResult(
            ok=True,
            data={
                "total_count": len(rows),
                "sample": rows[:5],
                "truncated": len(rows) > 5,
                "filters": {"date_from": df, "date_to": dt, "only_unpaid": bool(args.only_unpaid)},
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("list_invoices failed")
        return ToolResult(ok=False, data={}, error=f"store_api_error:{type(exc).__name__}")


# ─────────────────────────────────────────────────────────────────────────────
# Handler: get_total_paid
# ─────────────────────────────────────────────────────────────────────────────
def _safe_float(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


async def handle_get_total_paid(args: S.GetTotalPaidArgs, ctx: ToolContext) -> ToolResult:
    guard = _require_verified(ctx, "get_total_paid")
    if guard:
        return guard
    try:
        rows = await ctx.store_client.get_invoice_by_seller_id(
            seller_id=ctx.seller_id,
            date_from=_WIDE_RANGE_FROM,
            date_to=_wide_today(),
        )
        rows = [r for r in (rows or []) if isinstance(r, dict)]
        total = 0.0
        currency = None
        unpaid_amount = 0.0
        for r in rows:
            payable = _safe_float(r.get("payable") or r.get("net_total"))
            if _is_paid(r.get("pay_status")):
                total += payable
                currency = currency or r.get("currency")
            else:
                unpaid_amount += payable
        return ToolResult(
            ok=True,
            data={
                "total_paid": round(total, 2),
                "total_unpaid": round(unpaid_amount, 2),
                "currency": currency or "AED",
                "invoice_count": len(rows),
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("get_total_paid failed")
        return ToolResult(ok=False, data={}, error=f"store_api_error:{type(exc).__name__}")


# ─────────────────────────────────────────────────────────────────────────────
# Handler: get_total_orders
# ─────────────────────────────────────────────────────────────────────────────
async def handle_get_total_orders(args: S.GetTotalOrdersArgs, ctx: ToolContext) -> ToolResult:
    guard = _require_verified(ctx, "get_total_orders")
    if guard:
        return guard
    try:
        invoices = await ctx.store_client.get_invoice_by_seller_id(
            seller_id=ctx.seller_id,
            date_from=_WIDE_RANGE_FROM,
            date_to=_wide_today(),
        )
        ids: set[str] = set()
        for inv in invoices or []:
            if not isinstance(inv, dict):
                continue
            for oid in inv.get("order_ids") or []:
                sid = str(oid or "").strip().lstrip("#")
                if sid:
                    ids.add(sid)
        # Cross-check with /orders/all for orders not yet on any invoice.
        try:
            all_orders = await ctx.store_client.get_orders_all(
                seller_id=ctx.seller_id,
                date_from=_WIDE_RANGE_FROM,
                date_to=_wide_today(),
            )
            for row in all_orders or []:
                oid = str(row.get("id") or "").strip().lstrip("#")
                if oid:
                    ids.add(oid)
        except Exception:
            logger.debug("get_total_orders: /orders/all sweep failed; falling back to invoice ids only")
        return ToolResult(ok=True, data={"total_orders": len(ids)})
    except Exception as exc:  # noqa: BLE001
        logger.exception("get_total_orders failed")
        return ToolResult(ok=False, data={}, error=f"store_api_error:{type(exc).__name__}")


# ─────────────────────────────────────────────────────────────────────────────
# Handler: search_kb
# ─────────────────────────────────────────────────────────────────────────────
async def handle_search_kb(args: S.SearchKbArgs, ctx: ToolContext) -> ToolResult:
    """Wrap ArabiaLangChainBot's KB retrieval — single source of truth for KB ranking."""
    try:
        from langchain_bot.bot import ArabiaLangChainBot

        bot = ArabiaLangChainBot(ctx.db)
        knowledge_str, followups = bot._build_knowledge_context(  # noqa: SLF001
            ctx.tenant_id, user_message=args.query, max_chunks=args.max_chunks
        )
        return ToolResult(
            ok=True,
            data={"knowledge_excerpts": knowledge_str, "kb_followup_suggestions": followups},
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("search_kb failed")
        return ToolResult(ok=False, data={}, error=f"kb_error:{type(exc).__name__}")


# ─────────────────────────────────────────────────────────────────────────────
# Handler: escalate_to_agent
# ─────────────────────────────────────────────────────────────────────────────
async def handle_escalate_to_agent(
    args: S.EscalateToAgentArgs, ctx: ToolContext
) -> ToolResult:
    """Mark the turn for handoff. Actual agent assignment is performed by the
    legacy ``BotFlowResult`` plumbing in messaging_service — the orchestrator
    surfaces ``escalation_signal=True`` so the caller can trigger it.
    """
    return ToolResult(
        ok=True,
        data={"escalation_signal": True, "reason": args.reason, "team": args.team},
    )


# ─────────────────────────────────────────────────────────────────────────────
# Handler: get_trending_products
# Pagination cursor lives in Redis (memory_service); LLM only passes a direction.
# ─────────────────────────────────────────────────────────────────────────────
async def handle_get_trending_products(
    args: S.GetTrendingProductsArgs, ctx: ToolContext
) -> ToolResult:
    """The full trending/non-trending renderer is in the legacy state machine
    because it produces structured WhatsApp image+caption messages.

    For now the tool returns a *signal* that the orchestrator turns into a
    fall-through to the deterministic trending handler. Phase 4.2+ will move
    the structured rendering itself behind this tool.
    """
    return ToolResult(
        ok=True,
        data={
            "trending_signal": True,
            "country": args.country,
            "mode": args.mode,
            "direction": args.direction,
            "category": args.category,
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# Handler: generate_csv
# ─────────────────────────────────────────────────────────────────────────────
async def handle_generate_csv(args: S.GenerateCsvArgs, ctx: ToolContext) -> ToolResult:
    """Same fall-through pattern as trending — the CSV builder + R2 upload +
    WhatsApp document send is wired in service.py. The orchestrator surfaces
    a signal; the caller dispatches to the existing CSV pipeline."""
    guard = _require_verified(ctx, "generate_csv")
    if guard:
        return guard
    today = date.today()
    df = (args.date_from or (today - timedelta(days=365))).isoformat()
    dt = (args.date_to or today).isoformat()
    return ToolResult(
        ok=True,
        data={
            "csv_signal": True,
            "kind": args.kind,
            "date_from": df,
            "date_to": dt,
            "invoice_id": args.invoice_id,
            "invoice_date": args.invoice_date.isoformat() if args.invoice_date else None,
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# Handler: start_verification — only verification tool the LLM is allowed to call.
# email/OTP/mobile parsing stays in the deterministic state machine; letting
# the LLM call submit_* tools resulted in the LLM 'playing verification'
# without actually advancing the flow (WhatsApp transcript bug 2026-04-29).
# ─────────────────────────────────────────────────────────────────────────────
async def handle_start_verification(
    args: S.StartVerificationArgs, ctx: ToolContext
) -> ToolResult:
    return ToolResult(ok=True, data={"verification_signal": "start", "reason": args.reason})


# ─────────────────────────────────────────────────────────────────────────────
# Dispatch table — name → handler
# ─────────────────────────────────────────────────────────────────────────────
HANDLERS: Dict[str, Any] = {
    "start_verification": handle_start_verification,
    "lookup_order": handle_lookup_order,
    "lookup_orders_by_range": handle_lookup_orders_by_range,
    "list_invoices": handle_list_invoices,
    "get_total_paid": handle_get_total_paid,
    "get_total_orders": handle_get_total_orders,
    "generate_csv": handle_generate_csv,
    "search_kb": handle_search_kb,
    "get_trending_products": handle_get_trending_products,
    "escalate_to_agent": handle_escalate_to_agent,
}
