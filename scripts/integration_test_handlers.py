"""
Integration test: bot handlers vs. live Arabia store API.

Calls each tool handler against the real store API for seller_id=12630
(Urban Mart) and prints the result + a comparison to the curl ground
truth captured on 2026-04-29. Run from server/ with .env loaded:

    cd server
    python ../scripts/integration_test_handlers.py

This is a one-off comparison runner, not a pytest test — it hits the
live API and is meant to be run manually when validating the data layer.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

# Make `server/` importable.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))

# Load .env if dotenv is available.
try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / "server" / ".env")
except Exception:
    pass


GROUND_TRUTH = {
    "seller_id": "12630",
    "name": "Urban Mart",
    "total_orders_all_time": 888,  # /orders/all wide range
    "total_invoices": 6,
    "order_ids_in_invoices": 211 + 140 + 90 + 120 + 27 + 2,  # 590
    "total_payable": 3674 + 2648 + 45 + 2508 + 641 + (-10),  # 9506.0
    "total_unpaid": 0.0,  # all 6 invoices are paid
    "last_30d_orders": 598,
    "last_2m_orders": 888,
    "real_order_id": "177089",
    "real_order_profit": "36",
    "real_order_status": "Delivered",
    "real_order_tracking": "PT25238278",
    "wrong_seller_order": "137044",  # exists in system but NOT for seller 12630
}


def _hr() -> None:
    print("─" * 72)


def _check(label: str, expected: object, actual: object) -> None:
    ok = "✅" if expected == actual else "❌"
    print(f"  {ok} {label}: expected={expected!r}, actual={actual!r}")


async def run_tests() -> None:
    from langchain_bot.tools.handlers import (
        ToolContext,
        handle_get_total_orders,
        handle_get_total_paid,
        handle_list_invoices,
        handle_lookup_order,
        handle_lookup_orders_by_range,
    )
    from langchain_bot.tools.schemas import (
        GetTotalOrdersArgs,
        GetTotalPaidArgs,
        ListInvoicesArgs,
        LookupOrderArgs,
        LookupOrdersByRangeArgs,
    )
    from services.store_integration_service.client import StoreIntegrationClient

    store = StoreIntegrationClient()
    ctx = ToolContext(
        db=MagicMock(),
        tenant_id=1,
        customer_phone="03474685920",
        conversation_id=1,
        language="english",
        store_client=store,
        bot_flow={
            "verified": True,
            "seller_id": GROUND_TRUTH["seller_id"],
            "step": "conversational",
        },
    )

    # ── 1. lookup_order — real order
    print("\n[1] lookup_order(177089) — Urban Mart's real order")
    _hr()
    r = await handle_lookup_order(LookupOrderArgs(order_id="177089"), ctx)
    if not r.ok:
        print(f"  ❌ FAILED: {r.error}")
    else:
        order = r.data.get("order") or {}
        _check("status", GROUND_TRUTH["real_order_status"], order.get("status") or order.get("tracking_result"))
        _check("profit", GROUND_TRUTH["real_order_profit"], order.get("profit"))
        _check("shipped_ref", GROUND_TRUTH["real_order_tracking"], order.get("shipped_ref"))
        _check("tracking present", True, bool(r.data.get("tracking")))
        _check("invoice present", True, bool(r.data.get("invoice")))

    # ── 2. lookup_order — wrong seller (TCH)
    print("\n[2] lookup_order(137044) — exists but not for this seller")
    _hr()
    r = await handle_lookup_order(LookupOrderArgs(order_id="137044"), ctx)
    if r.ok:
        print(f"  ⚠️  Unexpected: handler returned ok=True for wrong-seller order. data={r.data}")
    else:
        _check("error contains 'not_found'", True, "not_found" in (r.error or ""))

    # ── 3. lookup_orders_by_range — last 30 days
    print("\n[3] lookup_orders_by_range — last 30 days (2026-03-30 → 2026-04-29)")
    _hr()
    # DEBUG: also call client directly to compare
    raw = await store.get_orders_all(seller_id="12630", date_from="2026-03-30", date_to="2026-04-29")
    print(f"  [DEBUG] direct store.get_orders_all returned len={len(raw)}")
    if raw:
        print(f"  [DEBUG] first id={raw[0].get('id')}")
    print(f"  [DEBUG] base_url={store.base_url!r}")
    r = await handle_lookup_orders_by_range(
        LookupOrdersByRangeArgs(date_from=date(2026, 3, 30), date_to=date(2026, 4, 29)),
        ctx,
    )
    if not r.ok:
        print(f"  ❌ FAILED: {r.error}")
    else:
        _check("total_count", GROUND_TRUTH["last_30d_orders"], r.data.get("total_count"))
        _check("sample_size", 5, len(r.data.get("sample") or []))
        _check("truncated", True, r.data.get("truncated"))

    # ── 4. lookup_orders_by_range — last 2 months
    print("\n[4] lookup_orders_by_range — last 2 months (2026-03-01 → 2026-04-30)")
    _hr()
    r = await handle_lookup_orders_by_range(
        LookupOrdersByRangeArgs(date_from=date(2026, 3, 1), date_to=date(2026, 4, 30)),
        ctx,
    )
    if not r.ok:
        print(f"  ❌ FAILED: {r.error}")
    else:
        _check("total_count", GROUND_TRUTH["last_2m_orders"], r.data.get("total_count"))

    # ── 5. list_invoices — all
    print("\n[5] list_invoices — all (no filter)")
    _hr()
    r = await handle_list_invoices(ListInvoicesArgs(), ctx)
    if not r.ok:
        print(f"  ❌ FAILED: {r.error}")
    else:
        _check("total_count", GROUND_TRUTH["total_invoices"], r.data.get("total_count"))

    # ── 6. list_invoices — only_unpaid
    print("\n[6] list_invoices — only_unpaid=True")
    _hr()
    r = await handle_list_invoices(ListInvoicesArgs(only_unpaid=True), ctx)
    if not r.ok:
        print(f"  ❌ FAILED: {r.error}")
    else:
        # Ground truth: all 6 invoices are paid → 0 unpaid
        _check("total_count (unpaid)", 0, r.data.get("total_count"))

    # ── 7. get_total_paid
    print("\n[7] get_total_paid")
    _hr()
    r = await handle_get_total_paid(GetTotalPaidArgs(), ctx)
    if not r.ok:
        print(f"  ❌ FAILED: {r.error}")
    else:
        _check("total_paid", float(GROUND_TRUTH["total_payable"]), r.data.get("total_paid"))
        _check("invoice_count", GROUND_TRUTH["total_invoices"], r.data.get("invoice_count"))

    # ── 8. get_total_orders
    print("\n[8] get_total_orders")
    _hr()
    r = await handle_get_total_orders(GetTotalOrdersArgs(), ctx)
    if not r.ok:
        print(f"  ❌ FAILED: {r.error}")
    else:
        # Combined: union of invoice order_ids ∪ /orders/all ids = 888 (all-orders is superset).
        _check("total_orders (combined sweep)", GROUND_TRUTH["total_orders_all_time"], r.data.get("total_orders"))

    # ── 9. AGGREGATE: profit + tracking numbers in a date range
    print("\n[9] lookup_orders_by_range AGGREGATE — last 30 days")
    _hr()
    r = await handle_lookup_orders_by_range(
        LookupOrdersByRangeArgs(date_from=date(2026, 3, 30), date_to=date(2026, 4, 29)),
        ctx,
    )
    if not r.ok:
        print(f"  ❌ FAILED: {r.error}")
    else:
        agg = r.data.get("aggregate") or {}
        print(f"  → total_profit (last 30d): {agg.get('total_profit')} AED")
        print(f"  → total_shipping (last 30d): {agg.get('total_shipping')} AED")
        print(f"  → delivered: {agg.get('delivered')}, returned: {agg.get('returned')}, "
              f"cancelled: {agg.get('cancelled')}, pending: {agg.get('pending_or_other')}")
        tracks = r.data.get("tracking_numbers") or []
        print(f"  → tracking_numbers count: {len(tracks)} "
              f"(truncated={r.data.get('tracking_numbers_truncated')})")
        if tracks:
            print(f"  → first 3 trackings: {tracks[:3]}")
        # Sanity: profit should be positive for active seller
        _check("aggregate present", True, isinstance(agg, dict) and "total_profit" in agg)
        _check("delivered+returned+cancelled+pending == total_count",
               r.data.get("total_count"),
               agg.get("delivered", 0) + agg.get("returned", 0) + agg.get("cancelled", 0) + agg.get("pending_or_other", 0))

    # ── 10. AGGREGATE: profit + tracking numbers all-time
    print("\n[10] lookup_orders_by_range AGGREGATE — all time")
    _hr()
    r = await handle_lookup_orders_by_range(
        LookupOrdersByRangeArgs(date_from=date(2020, 1, 1), date_to=date(2026, 4, 30)),
        ctx,
    )
    if not r.ok:
        print(f"  ❌ FAILED: {r.error}")
    else:
        agg = r.data.get("aggregate") or {}
        _check("total_count (all time)", GROUND_TRUTH["total_orders_all_time"], r.data.get("total_count"))
        print(f"  → total_profit (all time): {agg.get('total_profit')} AED")
        print(f"  → total_shipping (all time): {agg.get('total_shipping')} AED")
        print(f"  → status breakdown: {agg.get('by_status')}")
        tracks = r.data.get("tracking_numbers") or []
        print(f"  → tracking_numbers in response (capped): {len(tracks)} "
              f"(truncated={r.data.get('tracking_numbers_truncated')})")

    # ── 11. UNPAID amount + count
    print("\n[11] get_total_paid — also reports unpaid amount")
    _hr()
    r = await handle_get_total_paid(GetTotalPaidArgs(), ctx)
    if r.ok:
        _check("total_unpaid", GROUND_TRUTH["total_unpaid"], r.data.get("total_unpaid"))
        print(f"  → currency: {r.data.get('currency')}")


if __name__ == "__main__":
    print(f"Integration test — handlers vs. live Arabia store API")
    print(f"Seller: {GROUND_TRUTH['name']} (seller_id={GROUND_TRUTH['seller_id']})\n")
    asyncio.run(run_tests())
    print("\n[done]")
