"""
CSV export integration test — compares the CSV the bot generates against
the raw API data for the same query window.

For each scenario:
  1. fetch the live orders/invoice list directly via store_client (ground truth)
  2. call build_orders_csv_export_bytes / build_invoice_csv_export_bytes
     (the same pipeline the bot triggers when the customer asks for CSV)
  3. parse the CSV back into rows and compare:
       - row count
       - presence of every order id from the API
       - aggregate profit / shipping match
       - tracking number coverage

Run: python3 scripts/integration_test_csv_export.py
"""
from __future__ import annotations

import asyncio
import csv
import io
import sys
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / "server" / ".env")
except Exception:
    pass


SELLER_ID = "12630"


def _hr() -> None:
    print("─" * 80)


def _f(x: Any) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def _parse_csv_rows(body: bytes) -> Tuple[List[str], List[Dict[str, str]]]:
    """Decode using utf-8-sig so the leading byte-order-mark (the bot writes
    UTF-8-BOM CSVs for Excel compatibility) is stripped from the first
    column name."""
    text = body.decode("utf-8-sig", errors="ignore")
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        return [], []
    header = rows[0]
    data = [dict(zip(header, r)) for r in rows[1:]]
    return header, data


def _find_col(header: List[str], *candidates: str) -> str | None:
    """Find first matching column name (case-insensitive)."""
    low = {h.lower(): h for h in header}
    for cand in candidates:
        if cand.lower() in low:
            return low[cand.lower()]
    return None


async def _curl_orders(date_from: str, date_to: str, retries: int = 3) -> List[Dict[str, Any]]:
    from services.store_integration_service.client import StoreIntegrationClient

    sc = StoreIntegrationClient()
    for i in range(retries):
        rows = await sc.get_orders_all(seller_id=SELLER_ID, date_from=date_from, date_to=date_to) or []
        if rows:
            return rows
        if i < retries - 1:
            await asyncio.sleep(0.6 * (i + 1))
    return []


async def _curl_invoices(date_from: str = "2020-01-01", date_to: str = "2026-04-30") -> List[Dict[str, Any]]:
    from services.store_integration_service.client import StoreIntegrationClient

    sc = StoreIntegrationClient()
    return await sc.get_invoice_by_seller_id(seller_id=SELLER_ID, date_from=date_from, date_to=date_to) or []


# ─────────────────────────────────────────────────────────────────────────────
async def run() -> None:
    from services.orders_export_service.exporter import (
        build_invoice_csv_export_bytes,
        build_orders_csv_export_bytes,
    )
    from services.store_integration_service.client import StoreIntegrationClient

    sc = StoreIntegrationClient()
    print(f"CSV export integration test — seller_id={SELLER_ID}\n")
    _hr()

    pass_count = fail_count = 0

    def _check(label: str, expected: Any, actual: Any) -> None:
        nonlocal pass_count, fail_count
        ok = expected == actual
        mark = "✅" if ok else "❌"
        print(f"  {mark} {label}: expected={expected!r}  actual={actual!r}")
        if ok:
            pass_count += 1
        else:
            fail_count += 1

    def _check_close(label: str, expected: float, actual: float, tol: float = 1.0) -> None:
        nonlocal pass_count, fail_count
        ok = abs(expected - actual) <= tol
        mark = "✅" if ok else "❌"
        print(f"  {mark} {label}: expected≈{expected!r}  actual={actual!r}  (tol±{tol})")
        if ok:
            pass_count += 1
        else:
            fail_count += 1

    # ── A. Orders CSV — last 30 days ─────────────────────────────────────
    print("\n[A] Orders CSV — last 30 days (2026-03-30 → 2026-04-29)")
    _hr()
    df_30, dt_30 = "2026-03-30", "2026-04-29"
    api_orders_30 = await _curl_orders(df_30, dt_30)
    print(f"  → API returned {len(api_orders_30)} orders for last 30d")

    body, n, trunc = await build_orders_csv_export_bytes(sc, SELLER_ID, df_30, dt_30)
    print(f"  → CSV reported row_count={n} truncated={trunc}, bytes={len(body)}")

    header, rows = _parse_csv_rows(body)
    print(f"  → CSV parsed: {len(rows)} data rows, columns={len(header)}")
    print(f"  → CSV header: {header}")

    _check("CSV row count == API order count", len(api_orders_30), len(rows))
    _check("CSV reported n == row count", len(rows), n)

    id_col = _find_col(header, "Order ID", "id")
    profit_col = _find_col(header, "Profit", "profit", "Seller Profit")
    track_col = _find_col(header, "Tracking", "Tracking #", "Shipped Ref", "tracking_number")

    api_ids: Set[str] = {str(o.get("id")).strip() for o in api_orders_30 if o.get("id")}
    csv_ids: Set[str] = {str(r.get(id_col, "")).strip().lstrip("#") for r in rows if id_col} if id_col else set()
    missing = api_ids - csv_ids
    extra = csv_ids - api_ids
    _check("every API order id is in CSV", set(), missing)
    _check("no extra order ids in CSV (vs API)", set(), extra)

    if profit_col:
        csv_profit_total = sum(_f(r.get(profit_col)) for r in rows)
        api_profit_total = sum(_f(o.get("profit")) for o in api_orders_30)
        _check_close("total profit matches (last 30d)", api_profit_total, csv_profit_total, tol=1.0)

    if track_col:
        api_with_track = sum(1 for o in api_orders_30 if (o.get("shipped_ref") or "").strip())
        csv_with_track = sum(1 for r in rows if (r.get(track_col) or "").strip())
        # CSV may include tracking enrichment; we just want the API-known trackings to be present
        _check("CSV has at least as many tracking values as the API does",
               True, csv_with_track >= api_with_track)

    # ── B. Orders CSV — March 2026 ───────────────────────────────────────
    print("\n[B] Orders CSV — March 2026 (2026-03-01 → 2026-03-31)")
    _hr()
    api_mar = await _curl_orders("2026-03-01", "2026-03-31")
    body, n, _ = await build_orders_csv_export_bytes(sc, SELLER_ID, "2026-03-01", "2026-03-31")
    header, rows = _parse_csv_rows(body)
    _check("March CSV row_count == API count", len(api_mar), len(rows))

    if profit_col := _find_col(header, "Profit", "profit", "Seller Profit"):
        csv_profit = sum(_f(r.get(profit_col)) for r in rows)
        api_profit = sum(_f(o.get("profit")) for o in api_mar)
        _check_close("March CSV total profit matches API", api_profit, csv_profit, tol=1.0)

    # ── C. Orders CSV — April 2026 ───────────────────────────────────────
    print("\n[C] Orders CSV — April 2026 (2026-04-01 → 2026-04-30)")
    _hr()
    api_apr = await _curl_orders("2026-04-01", "2026-04-30")
    body, n, _ = await build_orders_csv_export_bytes(sc, SELLER_ID, "2026-04-01", "2026-04-30")
    header, rows = _parse_csv_rows(body)
    _check("April CSV row_count == API count", len(api_apr), len(rows))

    # ── D. Orders CSV — all time (wide range) ────────────────────────────
    print("\n[D] Orders CSV — all time (2020-01-01 → 2026-04-30)")
    _hr()
    api_all = await _curl_orders("2020-01-01", "2026-04-30")
    body, n, trunc = await build_orders_csv_export_bytes(sc, SELLER_ID, "2020-01-01", "2026-04-30")
    header, rows = _parse_csv_rows(body)
    print(f"  → API: {len(api_all)} orders / CSV: {len(rows)} rows / truncated: {trunc}")
    if trunc:
        # Truncation cap — CSV row count ≤ API; but rows that ARE in the CSV must all be valid order ids.
        _check("CSV row count ≤ API count when truncated", True, len(rows) <= len(api_all))
        api_id_set = {str(o.get("id")).strip() for o in api_all if o.get("id")}
        id_col = _find_col(header, "Order ID", "id")
        csv_id_set = {str(r.get(id_col, "")).strip().lstrip("#") for r in rows if id_col}
        leaked = csv_id_set - api_id_set
        _check("no order ids in CSV that aren't in the API set", set(), leaked)
    else:
        _check("all-time CSV row_count == API count", len(api_all), len(rows))

    # ── E. Invoice CSV — biggest invoice (22-Apr-2026, 211 orders) ───────
    print("\n[E] Invoice CSV — 22-Apr-2026 (biggest invoice, 211 orders)")
    _hr()
    invoices = await _curl_invoices()
    target_inv = next((i for i in invoices if "22-Apr-2026" in (i.get("date") or "")), None)
    if target_inv is None:
        print("  ⚠️  Could not locate 22-Apr-2026 invoice in API response — skipping")
    else:
        api_inv_ids = {str(o).strip().lstrip("#") for o in (target_inv.get("order_ids") or [])}
        print(f"  → API invoice has {len(api_inv_ids)} order_ids on the date")
        body, n, ref, dt = await build_invoice_csv_export_bytes(
            sc, SELLER_ID, invoice_date="2026-04-22"
        )
        header, rows = _parse_csv_rows(body)
        print(f"  → CSV: {n} rows, ref={ref!r}, parsed_rows={len(rows)}")
        _check("invoice CSV row_count ≈ invoice order_id count",
               len(api_inv_ids), n)
        if id_col := _find_col(header, "Order ID", "id"):
            csv_ids = {str(r.get(id_col)).strip().lstrip("#") for r in rows}
            missing = api_inv_ids - csv_ids
            extra = csv_ids - api_inv_ids
            _check("every invoice order_id is in the CSV", set(), missing)
            _check("no order ids in CSV that aren't in the invoice", set(), extra)

    # ── F. Invoice CSV — smaller invoice (08-Apr-2026, 90 orders) ────────
    print("\n[F] Invoice CSV — 08-Apr-2026 (90 orders)")
    _hr()
    target_inv = next((i for i in invoices if "08-Apr-2026" in (i.get("date") or "")), None)
    if target_inv is None:
        print("  ⚠️  Could not locate 08-Apr-2026 invoice — skipping")
    else:
        api_inv_ids = {str(o).strip().lstrip("#") for o in (target_inv.get("order_ids") or [])}
        body, n, ref, dt = await build_invoice_csv_export_bytes(
            sc, SELLER_ID, invoice_date="2026-04-08"
        )
        _check("CSV row count == invoice order_id count (08-Apr)",
               len(api_inv_ids), n)

    # ── G. Invoice CSV — non-existent date (graceful failure) ────────────
    print("\n[G] Invoice CSV — non-existent date 2025-01-01 (should ValueError)")
    _hr()
    try:
        await build_invoice_csv_export_bytes(sc, SELLER_ID, invoice_date="2025-01-01")
        _check("non-existent invoice raises ValueError", True, False)
    except ValueError as e:
        _check("non-existent invoice raises ValueError", True, True)
        _check("ValueError message says 'invoice_not_found'",
               True, "invoice_not_found" in str(e))

    _hr()
    print(f"\nResult: {pass_count} passed, {fail_count} failed.\n")


if __name__ == "__main__":
    asyncio.run(run())
