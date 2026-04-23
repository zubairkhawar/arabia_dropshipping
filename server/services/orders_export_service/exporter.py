"""
Fetch orders + invoices from the merchant API and build CSV bytes.
"""
from __future__ import annotations

import csv
import io
import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple

from services.orders_export_service.csv_builder import (
    build_invoice_index,
    normalize_export_column_keys,
    orders_to_csv_bytes,
    resolve_include_tracking_flag,
)
from services.store_integration_service.client import StoreIntegrationClient

logger = logging.getLogger(__name__)

MAX_EXPORT_ORDERS = 5000
_TRACKING_ENRICH_CONCURRENCY = 12


def _pick_str(d: Dict[str, Any], *keys: str) -> str:
    for k in keys:
        v = d.get(k)
        if v is None:
            continue
        s = str(v).strip()
        if s:
            return s
    return ""


def _invoice_ref(inv: Dict[str, Any]) -> str:
    return _pick_str(inv, "invoice_id", "invoice_number", "id", "reference", "ref")


def _norm_date(s: str) -> str:
    return str(s or "").strip()[:10]


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


async def fetch_orders_and_invoices_for_export(
    store_client: StoreIntegrationClient,
    seller_id: str,
    date_from: str,
    date_to: str,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    sid = (seller_id or "").strip()
    orders: List[Dict[str, Any]] = []
    invoices: List[Dict[str, Any]] = []
    if not sid:
        return orders, invoices
    try:
        inv_payload = await store_client.get_invoice_by_seller_id(
            sid,
            date_from=date_from,
            date_to=date_to,
            all_invoices=True,
        )
        invoices = _invoices_from_merchant_payload(inv_payload)
        if isinstance(inv_payload.get("orders"), list):
            orders = [x for x in inv_payload.get("orders") if isinstance(x, dict)]
        elif isinstance(inv_payload.get("data"), list):
            orders = [x for x in inv_payload.get("data") if isinstance(x, dict)]
    except Exception:
        logger.exception("export: invoice fetch failed seller_id=%s", sid[:8])

    if not orders:
        try:
            orders = await store_client.get_orders_all(sid, date_from=date_from, date_to=date_to)
        except Exception:
            logger.exception("export: get_orders_all failed seller_id=%s", sid[:8])
    if not orders:
        try:
            orders = await store_client.get_orders_all(sid)
        except Exception:
            logger.exception("export: get_orders_all unscoped failed seller_id=%s", sid[:8])

    return orders, invoices


async def build_orders_csv_export_bytes(
    store_client: StoreIntegrationClient,
    seller_id: str,
    date_from: str,
    date_to: str,
    *,
    column_keys: Optional[Sequence[str]] = None,
    include_tracking: Optional[bool] = None,
) -> Tuple[bytes, int, bool]:
    """
    Returns (csv_bytes, row_count, truncated).

    When ``include_tracking`` is true (default when status/tracking columns are present),
    calls GET /orders/{id}/tracking for each order (bounded concurrency) and merges fields.
    """
    sid = (seller_id or "").strip()
    keys = normalize_export_column_keys(list(column_keys) if column_keys is not None else None)
    do_tracking = resolve_include_tracking_flag(keys, include_tracking)

    orders, invoices = await fetch_orders_and_invoices_for_export(
        store_client, seller_id, date_from, date_to
    )
    truncated = False
    if len(orders) > MAX_EXPORT_ORDERS:
        orders = orders[:MAX_EXPORT_ORDERS]
        truncated = True

    if do_tracking and orders and sid:
        try:
            orders = await store_client.enrich_orders_with_tracking(
                sid,
                orders,
                max_orders=MAX_EXPORT_ORDERS,
                max_concurrent=_TRACKING_ENRICH_CONCURRENCY,
            )
        except Exception:
            logger.exception("export: tracking enrichment failed seller_id=%s", sid[:8])

    inv_idx = build_invoice_index(invoices)
    body = orders_to_csv_bytes(orders, invoices_by_order_id=inv_idx, column_keys=keys)
    return body, len(orders), truncated


async def build_invoice_csv_export_bytes(
    store_client: StoreIntegrationClient,
    seller_id: str,
    *,
    invoice_id: Optional[str] = None,
    invoice_date: Optional[str] = None,
    include_tracking: bool = True,
) -> Tuple[bytes, int, str, str]:
    """
    Build CSV for a single invoice and its order rows.

    Returns (csv_bytes, row_count, invoice_ref, invoice_date).
    Raises ValueError when invoice cannot be resolved.
    """
    sid = (seller_id or "").strip()
    if not sid:
        raise ValueError("missing seller_id")

    iid = (invoice_id or "").strip()
    idate = _norm_date(invoice_date or "")

    inv_payload = await store_client.get_invoice_by_seller_id(
        sid,
        date_from=idate or "2020-01-01",
        date_to=idate or _norm_date("9999-12-31"),
        all_invoices=True,
        invoice_id=iid or None,
    )
    invoices = _invoices_from_merchant_payload(inv_payload)
    if not invoices:
        raise ValueError("invoice_not_found")

    chosen: Optional[Dict[str, Any]] = None
    if iid:
        for inv in invoices:
            if _invoice_ref(inv) == iid:
                chosen = inv
                break
    if chosen is None and idate:
        for inv in invoices:
            if _norm_date(_pick_str(inv, "date", "invoice_date", "created_at")) == idate:
                chosen = inv
                break
    if chosen is None:
        chosen = invoices[0]
    if not isinstance(chosen, dict):
        raise ValueError("invoice_not_found")

    inv_ref = _invoice_ref(chosen) or "invoice"
    inv_date = _norm_date(_pick_str(chosen, "date", "invoice_date", "created_at"))
    raw_oids = chosen.get("order_ids")
    order_ids = [str(x).strip() for x in raw_oids] if isinstance(raw_oids, list) else []
    order_ids = [x for x in order_ids if x][:MAX_EXPORT_ORDERS]

    orders: List[Dict[str, Any]] = []
    if order_ids:
        orders = await store_client.fetch_orders_for_order_ids(
            sid,
            order_ids,
            max_orders=MAX_EXPORT_ORDERS,
            max_concurrent=8,
        )
        # Keep only rows explicitly belonging to this invoice order id set.
        idset = {x.lstrip("#") for x in order_ids}
        filtered: List[Dict[str, Any]] = []
        for o in orders:
            oid = _pick_str(o, "id", "order_id", "order_number").lstrip("#")
            if oid in idset:
                filtered.append(o)
        orders = filtered

    if include_tracking and orders:
        try:
            orders = await store_client.enrich_orders_with_tracking(
                sid,
                orders,
                max_orders=MAX_EXPORT_ORDERS,
                max_concurrent=_TRACKING_ENRICH_CONCURRENCY,
            )
        except Exception:
            logger.exception("invoice export: tracking enrichment failed seller_id=%s", sid[:8])

    # Build CSV: invoice summary section + order rows.
    headers = [
        "Order ID",
        "Order Date",
        "Status",
        "Tracking Number",
        "Items",
        "Shipping",
        "Total",
        "Profit",
    ]
    buf = io.StringIO(newline="")
    w = csv.writer(buf)
    w.writerow(["Invoice Reference", inv_ref])
    w.writerow(["Invoice Date", inv_date or ""])
    w.writerow(["Invoice Payable", _pick_str(chosen, "payable", "net_total", "payable_amount")])
    w.writerow(["Invoice Status", _pick_str(chosen, "pay_status", "payment_status", "status")])
    w.writerow(["Invoice Order Count", str(len(order_ids))])
    w.writerow([])
    w.writerow(headers)
    for o in orders:
        w.writerow([
            _pick_str(o, "id", "order_id", "order_number"),
            _pick_str(o, "createdon", "order_date", "created_at"),
            _pick_str(o, "status", "order_status", "delivery_status"),
            _pick_str(o, "tracking_number", "tracking_id", "awb", "awb_number"),
            _pick_str(o, "details", "product_summary"),
            _pick_str(o, "shipping_charges", "shipping", "shipping_fee"),
            _pick_str(o, "total", "amount", "grand_total"),
            _pick_str(o, "profit"),
        ])

    return buf.getvalue().encode("utf-8-sig"), len(orders), inv_ref, inv_date
