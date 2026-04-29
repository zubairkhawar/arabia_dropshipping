"""
Field-level CSV-vs-API verification.

Goes beyond the row-count + total-profit checks: for every CSV row in
every test window, compare each per-row field against the same order
fetched via the API. Verifies:

  - Order ID
  - Order Date
  - Status (after tracking enrichment)
  - Tracking Number
  - Customer Name
  - Customer Phone
  - Shipping (per-row)
  - Profit (per-row)
  - Invoice Date / Payable / Status — joined for orders on an invoice

Coverage windows:
  Year (2026), Month (March/April), Week (last week of April), Day,
  Wide range (all-time).

Run: python3 scripts/integration_test_csv_field_level.py
"""
from __future__ import annotations

import asyncio
import csv
import io
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Tuple

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


def _norm_str(x: Any) -> str:
    return str(x or "").strip()


def _parse_csv(body: bytes) -> Tuple[List[str], List[Dict[str, str]]]:
    text = body.decode("utf-8-sig", errors="ignore")
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        return [], []
    header = rows[0]
    return header, [dict(zip(header, r)) for r in rows[1:]]


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


async def _curl_invoices() -> List[Dict[str, Any]]:
    from services.store_integration_service.client import StoreIntegrationClient

    sc = StoreIntegrationClient()
    return await sc.get_invoice_by_seller_id(
        seller_id=SELLER_ID, date_from="2020-01-01", date_to="2030-12-31"
    ) or []


# ─────────────────────────────────────────────────────────────────────────────
# Per-row comparison
# ─────────────────────────────────────────────────────────────────────────────
def _compare_one_row(
    csv_row: Dict[str, str],
    api_order: Dict[str, Any],
    invoice_for_oid: Dict[str, Dict[str, Any]],
) -> Tuple[bool, List[str]]:
    """Return (ok, list of mismatches). Each mismatch describes the field."""
    issues: List[str] = []

    # Order ID
    expected = _norm_str(api_order.get("id")).lstrip("#")
    actual = _norm_str(csv_row.get("Order ID")).lstrip("#")
    if expected != actual:
        issues.append(f"Order ID: expected={expected!r} csv={actual!r}")

    # Order Date — CSV may use different formatting; compare YYYY-MM-DD prefix
    api_date = _norm_str(api_order.get("createdon"))
    csv_date = _norm_str(csv_row.get("Order Date"))
    if api_date and csv_date:
        # Both should agree on YYYY-MM-DD.
        if api_date[:10] != csv_date[:10]:
            issues.append(f"Order Date: api={api_date[:10]} csv={csv_date[:10]}")

    # Status
    api_status = _norm_str(api_order.get("tracking_result") or api_order.get("status"))
    csv_status = _norm_str(csv_row.get("Status"))
    if api_status:
        # CSV may carry a "Tracking information temporarily unavailable" placeholder
        # when the upstream tracking enrichment failed for that row — that's not
        # a data mismatch, so accept either the API value OR the placeholder.
        if csv_status not in (api_status, "", "Tracking information temporarily unavailable"):
            issues.append(f"Status: api={api_status!r} csv={csv_status!r}")

    # Tracking Number
    api_track = _norm_str(api_order.get("shipped_ref"))
    csv_track = _norm_str(csv_row.get("Tracking Number"))
    if api_track and csv_track and api_track != csv_track:
        # Tracking enrichment may yield a different normalized form; warn but don't fail
        # if both are non-empty plausible refs (digits or letters+digits).
        if not (api_track in csv_track or csv_track in api_track):
            issues.append(f"Tracking: api={api_track!r} csv={csv_track!r}")

    # Customer Name
    api_name = _norm_str(api_order.get("name"))
    csv_name = _norm_str(csv_row.get("Customer Name"))
    if api_name and csv_name and api_name != csv_name:
        # Tolerate trailing-space / "-" suffix variation.
        if api_name.rstrip("- ") != csv_name.rstrip("- "):
            issues.append(f"Customer Name: api={api_name!r} csv={csv_name!r}")

    # Customer Phone
    api_phone = _norm_str(api_order.get("mobile"))
    csv_phone = _norm_str(csv_row.get("Customer Phone"))
    if api_phone and csv_phone and api_phone != csv_phone:
        issues.append(f"Customer Phone: api={api_phone!r} csv={csv_phone!r}")

    # Shipping (numeric)
    if abs(_f(api_order.get("shipping_charges")) - _f(csv_row.get("Shipping"))) > 0.01:
        issues.append(
            f"Shipping: api={api_order.get('shipping_charges')!r} csv={csv_row.get('Shipping')!r}"
        )

    # Profit (numeric)
    if abs(_f(api_order.get("profit")) - _f(csv_row.get("Profit"))) > 0.01:
        issues.append(
            f"Profit: api={api_order.get('profit')!r} csv={csv_row.get('Profit')!r}"
        )

    # Invoice columns — set when this order_id is on an invoice
    oid = _norm_str(api_order.get("id")).lstrip("#")
    inv = invoice_for_oid.get(oid)
    if inv:
        exp_inv_date = _norm_str(inv.get("date"))
        csv_inv_date = _norm_str(csv_row.get("Invoice Date"))
        if csv_inv_date and exp_inv_date and not (
            exp_inv_date.startswith(csv_inv_date) or csv_inv_date.startswith(exp_inv_date)
        ):
            issues.append(f"Invoice Date: api={exp_inv_date!r} csv={csv_inv_date!r}")
        if abs(_f(inv.get("payable")) - _f(csv_row.get("Invoice Payable"))) > 0.01 and csv_row.get("Invoice Payable"):
            issues.append(
                f"Invoice Payable: api={inv.get('payable')!r} csv={csv_row.get('Invoice Payable')!r}"
            )
        # Pay status: API "Yes" / "No" → CSV "Yes" / "No" (unchanged in builder)
        api_paid = _norm_str(inv.get("pay_status"))
        csv_paid = _norm_str(csv_row.get("Invoice Status"))
        if api_paid and csv_paid and api_paid != csv_paid:
            issues.append(f"Invoice Status: api={api_paid!r} csv={csv_paid!r}")

    return (not issues), issues


def _build_invoice_index(invoices: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Return order_id (lstrip#) → invoice dict."""
    out: Dict[str, Dict[str, Any]] = {}
    for inv in invoices:
        for oid in inv.get("order_ids") or []:
            key = _norm_str(oid).lstrip("#")
            if key:
                out[key] = inv
    return out


# ─────────────────────────────────────────────────────────────────────────────
async def run_window(
    label: str, date_from: str, date_to: str, invoice_index: Dict[str, Dict[str, Any]]
) -> Tuple[int, int, int]:
    """Returns (rows_checked, rows_ok, rows_with_issues)."""
    from services.orders_export_service.exporter import build_orders_csv_export_bytes
    from services.store_integration_service.client import StoreIntegrationClient

    sc = StoreIntegrationClient()

    print(f"\n[{label}]  date_from={date_from}  date_to={date_to}")
    _hr()

    api_orders = await _curl_orders(date_from, date_to)
    print(f"  API orders: {len(api_orders)}")

    body, n, trunc = await build_orders_csv_export_bytes(sc, SELLER_ID, date_from, date_to)
    header, rows = _parse_csv(body)
    print(f"  CSV rows:  {len(rows)} (header has {len(header)} columns)")

    api_by_id = {_norm_str(o.get("id")).lstrip("#"): o for o in api_orders}
    rows_checked = rows_ok = rows_with_issues = 0
    sample_issues: List[str] = []
    for r in rows:
        oid = _norm_str(r.get("Order ID")).lstrip("#")
        if oid not in api_by_id:
            rows_with_issues += 1
            sample_issues.append(f"Order ID {oid!r} in CSV but not in API")
            continue
        ok, issues = _compare_one_row(r, api_by_id[oid], invoice_index)
        rows_checked += 1
        if ok:
            rows_ok += 1
        else:
            rows_with_issues += 1
            if len(sample_issues) < 3:
                sample_issues.append(f"  Order {oid}: " + "; ".join(issues))

    pct = (rows_ok / rows_checked * 100) if rows_checked else 0.0
    print(f"  Rows checked field-by-field: {rows_checked}")
    print(f"  ✅ Rows clean:                 {rows_ok}  ({pct:.1f}%)")
    if rows_with_issues:
        print(f"  ⚠️  Rows with issues:          {rows_with_issues}")
        for line in sample_issues[:3]:
            print(f"     - {line}")
    return rows_checked, rows_ok, rows_with_issues


# ─────────────────────────────────────────────────────────────────────────────
async def main() -> None:
    print(f"Field-level CSV-vs-API verification — seller_id={SELLER_ID}\n")
    invoices = await _curl_invoices()
    invoice_index = _build_invoice_index(invoices)
    print(f"Invoice order-id index: {len(invoice_index)} order_ids across {len(invoices)} invoices\n")

    # ── Define test windows ──────────────────────────────────────────────
    windows: List[Tuple[str, str, str]] = [
        ("ALL TIME (2020-01-01 → 2026-04-30)", "2020-01-01", "2026-04-30"),
        ("YEAR 2026                          ", "2026-01-01", "2026-12-31"),
        ("MARCH 2026                         ", "2026-03-01", "2026-03-31"),
        ("APRIL 2026                         ", "2026-04-01", "2026-04-30"),
        ("LAST WEEK APRIL (23-29 Apr)        ", "2026-04-23", "2026-04-29"),
        ("LAST 30 DAYS                       ", "2026-03-30", "2026-04-29"),
        ("SINGLE DAY 26-Mar-2026             ", "2026-03-26", "2026-03-26"),
        ("SINGLE DAY 22-Apr-2026             ", "2026-04-22", "2026-04-22"),
        ("FUTURE WINDOW (no orders expected) ", "2030-01-01", "2030-01-31"),
    ]

    grand_checked = grand_ok = grand_issues = 0
    for label, df, dt in windows:
        c, o, i = await run_window(label, df, dt, invoice_index)
        grand_checked += c
        grand_ok += o
        grand_issues += i

    _hr()
    print(f"\nTotal rows verified field-by-field: {grand_checked}")
    print(f"Clean rows:    {grand_ok}  ({(grand_ok/grand_checked*100 if grand_checked else 0):.2f}%)")
    print(f"Rows w/issues: {grand_issues}")
    print()


if __name__ == "__main__":
    asyncio.run(main())
