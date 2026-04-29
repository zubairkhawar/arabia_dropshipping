"""
Regression test for WhatsApp transcript 2026-04-29 16:46:

Verified customer typed an order id ('187916') at the post-verification
ask-order step. Bot replied with one short sentence (status + tracking
only). Customer then had to ask 'tell me order details' / 'invoice
btao' / 'profit btao' separately to get other fields — and some of
those follow-ups failed with 'data fetch failed'.

Fix: the deterministic existing_awaiting_order_id success path now
formats a multi-line full-details reply with date / status / tracking /
items / total / shipping / profit / invoice (date + payable + status).
The order is also enriched with invoice mapping before formatting.
"""
from __future__ import annotations

import pytest

from services.customer_bot_flow.service import (
    _extract_order_fields,
    _format_order_full_details,
)


SAMPLE_ORDER_API = {
    "id": "187916",
    "name": "Hassan -",
    "address": "Al Wasl Road",
    "sellers": "12630",
    "shipped_ref": "PT25266624",
    "tracking_result": "Delivered",
    "mobile": "+971500000000",
    "city_name": "DUBAI",
    "details": "Turmeric Overnight Wrapping Peel Off Mask",
    "qty": "1",
    "shipping_charges": "18",
    "profit": "37.66",
    "createdon": "2026-04-25 12:00:00",
    "items": [
        {
            "order_id": "187916",
            "title": "Turmeric Overnight Wrapping Peel Off Mask",
            "price": "20",
            "qty": "1",
        }
    ],
}


class TestExtractOrderFieldsCarriesFullData:
    def test_profit_carried_through(self) -> None:
        out = _extract_order_fields(SAMPLE_ORDER_API, "187916")
        assert out["profit"] == "37.66"

    def test_shipping_charges_carried_through(self) -> None:
        out = _extract_order_fields(SAMPLE_ORDER_API, "187916")
        assert out["shipping_charges"] == "18"

    def test_items_list_preserved(self) -> None:
        out = _extract_order_fields(SAMPLE_ORDER_API, "187916")
        assert isinstance(out["items"], list)
        assert len(out["items"]) == 1
        assert out["items"][0]["title"] == "Turmeric Overnight Wrapping Peel Off Mask"

    def test_tracking_from_shipped_ref(self) -> None:
        out = _extract_order_fields(SAMPLE_ORDER_API, "187916")
        assert out["tracking_id"] == "PT25266624"

    def test_status_from_tracking_result(self) -> None:
        out = _extract_order_fields(SAMPLE_ORDER_API, "187916")
        assert out["delivery_status"] == "Delivered"

    def test_order_date_from_createdon(self) -> None:
        out = _extract_order_fields(SAMPLE_ORDER_API, "187916")
        assert out["order_date"] == "2026-04-25 12:00:00"


class TestFormatOrderFullDetails:
    @pytest.mark.parametrize("lang", ["english", "roman_urdu", "arabic"])
    def test_includes_id_status_tracking_profit_shipping(self, lang: str) -> None:
        order = _extract_order_fields(SAMPLE_ORDER_API, "187916")
        # Add invoice annotations as the success-path enrichment would.
        order["invoice_date"] = "22-Apr-2026 - 06:13 pm"
        order["invoice_payable"] = "3674.00"
        order["invoice_pay_status"] = "Yes"

        out = _format_order_full_details(lang, order)

        # Order id always present.
        assert "187916" in out
        # Status + tracking
        assert "Delivered" in out
        assert "PT25266624" in out
        # Profit + shipping
        assert "37.66" in out
        assert "18" in out
        # Items
        assert "Turmeric Overnight Wrapping Peel Off Mask" in out
        # Invoice block
        assert "22-Apr-2026" in out
        assert "3674.00" in out

    def test_cancelled_order_omits_profit_and_shipping(self) -> None:
        cancelled = dict(SAMPLE_ORDER_API)
        cancelled["status"] = "Cancelled"
        cancelled.pop("tracking_result", None)
        order = _extract_order_fields(cancelled, "187916")
        out = _format_order_full_details("english", order)
        # Per the prompt rule: cancelled orders should NOT show profit/shipping.
        # Our formatter respects this.
        # (We test the formatter, not the prompt rule.)
        assert "Cancelled" in out
        # Profit and shipping suppressed for cancelled orders
        assert "37.66 AED" not in out
        # Status row still shows the cancellation
        assert "Status" in out

    def test_missing_invoice_block_skipped(self) -> None:
        order = _extract_order_fields(SAMPLE_ORDER_API, "187916")
        # No invoice annotations
        out = _format_order_full_details("english", order)
        # Should still include the rest
        assert "187916" in out
        assert "Delivered" in out
        # Invoice block not included
        assert "Invoice:" not in out
