"""
Fetch orders + invoices from the merchant API and build CSV bytes.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Tuple

from services.orders_export_service.csv_builder import (
    build_invoice_index,
    orders_to_csv_bytes,
)
from services.store_integration_service.client import StoreIntegrationClient

logger = logging.getLogger(__name__)

MAX_EXPORT_ORDERS = 5000


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
) -> Tuple[bytes, int, bool]:
    """
    Returns (csv_bytes, row_count, truncated).
    """
    orders, invoices = await fetch_orders_and_invoices_for_export(
        store_client, seller_id, date_from, date_to
    )
    truncated = False
    if len(orders) > MAX_EXPORT_ORDERS:
        orders = orders[:MAX_EXPORT_ORDERS]
        truncated = True
    inv_idx = build_invoice_index(invoices)
    body = orders_to_csv_bytes(orders, invoices_by_order_id=inv_idx)
    return body, len(orders), truncated
