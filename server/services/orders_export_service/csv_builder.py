"""
Build UTF-8 CSV exports for merchant orders (StoreIntegrationClient payloads).
Supports dynamic column subsets; default includes tracking/invoice fields when data is present.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

# Canonical machine keys (API / request body). Order = default CSV column order.
CANONICAL_EXPORT_COLUMN_KEYS: Tuple[str, ...] = (
    "order_id",
    "order_date",
    "status",
    "tracking_number",
    "customer_name",
    "customer_phone",
    "address",
    "items",
    "subtotal",
    "shipping",
    "total",
    "profit",
    "invoice_date",
    "invoice_payable",
    "invoice_status",
)

_CANONICAL_SET = frozenset(CANONICAL_EXPORT_COLUMN_KEYS)

# Accept common aliases from LLM / humans → canonical key
_COLUMN_KEY_ALIASES: Dict[str, str] = {
    "order": "order_id",
    "orderid": "order_id",
    "id": "order_id",
    "date": "order_date",
    "placed_at": "order_date",
    "tracking": "tracking_number",
    "tracking_no": "tracking_number",
    "awb": "tracking_number",
    "invoiceamount": "invoice_payable",
    "payable": "invoice_payable",
    "payment_status": "invoice_status",
    "pay_status": "invoice_status",
}

COLUMN_LABELS: Dict[str, str] = {
    "order_id": "Order ID",
    "order_date": "Order Date",
    "status": "Status",
    "tracking_number": "Tracking Number",
    "customer_name": "Customer Name",
    "customer_phone": "Customer Phone",
    "address": "Address",
    "items": "Items",
    "subtotal": "Subtotal",
    "shipping": "Shipping",
    "total": "Total",
    "profit": "Profit",
    "invoice_date": "Invoice Date",
    "invoice_payable": "Invoice Payable",
    "invoice_status": "Invoice Status",
}

CSV_COLUMNS = [COLUMN_LABELS[k] for k in CANONICAL_EXPORT_COLUMN_KEYS]


def normalize_export_column_keys(requested: Optional[Sequence[str]]) -> List[str]:
    """
    Return a non-empty ordered list of canonical keys.
    Unknown keys are skipped; duplicates removed. Empty / None → full default set.
    """
    if not requested:
        return list(CANONICAL_EXPORT_COLUMN_KEYS)
    out: List[str] = []
    seen: set[str] = set()
    for raw in requested:
        k0 = str(raw).strip().lower().replace(" ", "_").replace("-", "_")
        k = _COLUMN_KEY_ALIASES.get(k0, k0)
        if k not in _CANONICAL_SET or k in seen:
            continue
        out.append(k)
        seen.add(k)
    return out if out else list(CANONICAL_EXPORT_COLUMN_KEYS)


def resolve_include_tracking_flag(
    column_keys: Sequence[str],
    include_tracking: Optional[bool],
) -> bool:
    """When ``include_tracking`` is None, fetch tracking if status/tracking columns are exported."""
    if include_tracking is not None:
        return bool(include_tracking)
    return "status" in column_keys or "tracking_number" in column_keys


def export_options_fingerprint(column_keys: Sequence[str], include_tracking: bool) -> str:
    """Stable short token for cache keys / filenames."""
    payload = json.dumps(
        {"columns": list(column_keys), "include_tracking": bool(include_tracking)},
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


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


def _cell_value(key: str, order: Dict[str, Any], inv: Dict[str, Any]) -> str:
    if key == "order_id":
        return _pick_str(order, "id", "order_id", "order_number")
    if key == "order_date":
        return _pick_str(order, "createdon", "order_date", "created_at", "placed_at")
    if key == "status":
        return _pick_str(order, "status", "order_status", "delivery_status")
    if key == "tracking_number":
        return _pick_str(order, "tracking_number", "tracking", "tracking_id", "awb_number", "awb")
    if key == "customer_name":
        return _pick_str(order, "customer_name", "buyer_name", "name")
    if key == "customer_phone":
        return _pick_str(order, "customer_phone", "phone", "mobile", "buyer_phone")
    if key == "address":
        return _address_cell(order)
    if key == "items":
        return _items_cell(order)
    if key == "subtotal":
        return _pick_str(order, "subtotal", "sub_total", "items_total")
    if key == "shipping":
        return _pick_str(order, "shipping_charges", "shipping", "shipping_fee")
    if key == "total":
        return _pick_str(order, "total", "grand_total", "amount")
    if key == "profit":
        return _pick_str(order, "profit")
    if key == "invoice_date":
        return _pick_str(inv, "date", "invoice_date", "created_at")
    if key == "invoice_payable":
        return _pick_str(inv, "payable", "invoice_payable", "payable_amount", "net_total")
    if key == "invoice_status":
        return _pick_str(inv, "pay_status", "payment_status", "status")
    return ""


def orders_to_csv_bytes(
    orders: List[Dict[str, Any]],
    *,
    invoices_by_order_id: Optional[Dict[str, Dict[str, Any]]] = None,
    column_keys: Optional[Sequence[str]] = None,
) -> bytes:
    inv_map = invoices_by_order_id or {}
    keys = normalize_export_column_keys(list(column_keys) if column_keys is not None else None)
    buf = io.StringIO(newline="")
    w = csv.writer(buf)
    w.writerow([COLUMN_LABELS[k] for k in keys])
    for o in orders:
        if not isinstance(o, dict):
            continue
        oid = _pick_str(o, "id", "order_id", "order_number")
        inv: Dict[str, Any] = {}
        if oid:
            raw_inv = inv_map.get(str(oid).lstrip("#"))
            if isinstance(raw_inv, dict):
                inv = raw_inv
        row = [_cell_value(k, o, inv) for k in keys]
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


def object_key_for_orders_csv(seller_id: str, fingerprint: str = "") -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    sid = "".join(c for c in str(seller_id) if c.isalnum() or c in ("-", "_"))[:32]
    fp = "".join(c for c in str(fingerprint) if c.isalnum())[:16]
    suffix = f"_{fp}" if fp else ""
    return f"exports/orders_{sid}{suffix}_{ts}.csv"


def object_key_for_invoice_csv(seller_id: str, invoice_ref: str = "") -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    sid = "".join(c for c in str(seller_id) if c.isalnum() or c in ("-", "_"))[:32]
    iref = "".join(c for c in str(invoice_ref) if c.isalnum() or c in ("-", "_"))[:32]
    suffix = f"_{iref}" if iref else ""
    return f"exports/invoice_{sid}{suffix}_{ts}.csv"
