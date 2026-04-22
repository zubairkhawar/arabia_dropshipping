"""
Build UTF-8 CSV exports for merchant orders (StoreIntegrationClient payloads).
"""
from __future__ import annotations

import csv
import io
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

CSV_COLUMNS = [
    "Order ID",
    "Order Date",
    "Status",
    "Tracking Number",
    "Customer Name",
    "Customer Phone",
    "Address",
    "Items",
    "Subtotal",
    "Shipping",
    "Total",
    "Profit",
    "Invoice Date",
    "Invoice Status",
]


def _pick_str(d: Dict[str, Any], *keys: str) -> str:
    for k in keys:
        v = d.get(k)
        if v is None:
            continue
        s = str(v).strip()
        if s:
            return s
    return ""


def _items_cell(order: Dict[str, Any]) -> str:
    raw = order.get("items")
    if isinstance(raw, list) and raw:
        try:
            return json.dumps(raw, ensure_ascii=False)[:8000]
        except (TypeError, ValueError):
            pass
    return _pick_str(order, "details", "product_summary", "items_summary")[:8000]


def _address_cell(order: Dict[str, Any]) -> str:
    for k in ("shipping_address", "address", "delivery_address", "full_address"):
        v = order.get(k)
        if isinstance(v, dict):
            parts = [str(x).strip() for x in v.values() if x is not None and str(x).strip()]
            if parts:
                return " ".join(parts)[:4000]
        elif v is not None and str(v).strip():
            return str(v).strip()[:4000]
    return ""


def orders_to_csv_bytes(
    orders: List[Dict[str, Any]],
    *,
    invoices_by_order_id: Optional[Dict[str, Dict[str, Any]]] = None,
) -> bytes:
    inv_map = invoices_by_order_id or {}
    buf = io.StringIO(newline="")
    w = csv.writer(buf)
    w.writerow(CSV_COLUMNS)
    for o in orders:
        if not isinstance(o, dict):
            continue
        oid = _pick_str(o, "id", "order_id", "order_number")
        inv = inv_map.get(str(oid).lstrip("#")) if oid else None
        if not isinstance(inv, dict):
            inv = {}
        row = [
            oid,
            _pick_str(o, "createdon", "order_date", "created_at", "placed_at"),
            _pick_str(o, "status", "order_status"),
            _pick_str(o, "tracking_number", "tracking", "tracking_id", "awb_number"),
            _pick_str(o, "customer_name", "buyer_name", "name"),
            _pick_str(o, "customer_phone", "phone", "mobile", "buyer_phone"),
            _address_cell(o),
            _items_cell(o),
            _pick_str(o, "subtotal", "sub_total", "items_total"),
            _pick_str(o, "shipping_charges", "shipping", "shipping_fee"),
            _pick_str(o, "total", "grand_total", "amount"),
            _pick_str(o, "profit"),
            _pick_str(inv, "date", "invoice_date", "created_at"),
            _pick_str(inv, "pay_status", "payment_status", "status"),
        ]
        w.writerow(row)
    return buf.getvalue().encode("utf-8-sig")


def build_invoice_index(invoices: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Map first invoice row that mentions each order id."""
    out: Dict[str, Dict[str, Any]] = {}
    for inv in invoices or []:
        if not isinstance(inv, dict):
            continue
        oids = inv.get("order_ids")
        if not isinstance(oids, list):
            continue
        for x in oids:
            key = str(x).strip().lstrip("#")
            if key and key not in out:
                out[key] = inv
    return out


def object_key_for_orders_csv(seller_id: str) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    sid = "".join(c for c in str(seller_id) if c.isalnum() or c in ("-", "_"))[:32]
    return f"exports/orders_{sid}_{ts}.csv"
