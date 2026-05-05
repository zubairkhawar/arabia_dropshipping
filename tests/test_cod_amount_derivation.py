"""
Regression test for WhatsApp transcript 2026-05-05 03:50.

Customer asked for order 184209 details. Bot replied:

  Order #184209 ki detail yeh hai:
  • Order date: 14-Apr-2026
  • Status: Delivered
  • Items: Essential Men's Perfume ×1 @ 13 AED
  • Selling price/COD amount: 13 AED        ❌ WRONG
  • Shipping charges: 18 AED
  • Seller profit: 34 AED

The actual COD (what the end customer paid the courier) was
13 + 18 + 34 = 65 AED. The store API for this order has:
  - items[0].price = "13"  (supplier cost — what seller pays Arabia)
  - shipping_charges = "18"
  - profit = "34"
  - NO total_amount / cod_amount / invoice_payable / invoice_net_total

The bot was reading items[0].price (the supplier cost) as the
"Selling price/COD amount". That's three different concepts in one
field name — the bug was conflating supplier cost with customer COD.

Fix: _extract_order_fields now derives total_amount via
_derive_cod_amount(): explicit total fields if present, otherwise
sum(items × qty) + shipping_charges + profit. Plus a prompt rule
teaches the LLM the same formula.
"""
from __future__ import annotations

import pytest

from services.customer_bot_flow.service import (
    _extract_order_fields,
    _format_order_full_details,
)


# Exact API response shape for order 184209 (curl-confirmed 2026-05-05).
ORDER_184209 = {
    "id": "184209",
    "name": "Romulo -",
    "address": "Bigmart hypermarket airport road",
    "sellers": "8241",
    "shipped_ref": "PT25258404",
    "tracking_result": "Delivered",
    "mobile": "+971543264708",
    "city_name": "Abu Dhabi",
    "details": "Essential Men's Perfume[ 1 x Multicolor /  ]",
    "qty": "1",
    "shipping_charges": "18",
    "profit": "34",
    "createdon": "2026-04-14 20:13:30",
    "items": [
        {
            "order_id": "184209",
            "title": "Essential Men's Perfume",
            "price": "13",
            "qty": "1",
        }
    ],
}


class TestCodDerivation:
    def test_cod_for_184209_is_65(self) -> None:
        """The exact transcript order: 13 + 18 + 34 = 65 AED."""
        out = _extract_order_fields(ORDER_184209, "184209")
        assert out["total_amount"] == "65", (
            f"COD for order 184209 must be 65 AED (item 13 + ship 18 + "
            f"profit 34). Got: {out['total_amount']!r}. The bot was "
            "showing 13 AED — that's the supplier cost, not the COD."
        )

    def test_cod_with_multi_qty(self) -> None:
        """Two units of the same item → cost doubles."""
        order = dict(ORDER_184209)
        order["items"] = [{"order_id": "X", "title": "Foo", "price": "13", "qty": "2"}]
        order["shipping_charges"] = "18"
        order["profit"] = "34"
        out = _extract_order_fields(order, "X")
        # 13 × 2 + 18 + 34 = 78
        assert out["total_amount"] == "78"

    def test_cod_with_multiple_items(self) -> None:
        """Multi-item order sums each line."""
        order = dict(ORDER_184209)
        order["items"] = [
            {"price": "13", "qty": "1"},
            {"price": "20", "qty": "2"},
        ]
        order["shipping_charges"] = "18"
        order["profit"] = "10"
        out = _extract_order_fields(order, "X")
        # 13 + (20 × 2) + 18 + 10 = 81
        assert out["total_amount"] == "81"

    def test_explicit_total_amount_preferred(self) -> None:
        """If the API ever DOES return total_amount, honour it (don't
        recompute). Some Arabia DB rows already carry it."""
        order = dict(ORDER_184209)
        order["total_amount"] = "100"  # explicit override
        out = _extract_order_fields(order, "184209")
        assert out["total_amount"] == "100", (
            "explicit total_amount must win over the derived sum"
        )

    def test_explicit_invoice_payable_preferred(self) -> None:
        """invoice_payable is also a known explicit total field."""
        order = dict(ORDER_184209)
        order["invoice_payable"] = "67"
        out = _extract_order_fields(order, "184209")
        assert out["total_amount"] == "67"

    def test_no_items_returns_empty_string(self) -> None:
        """Order with no items / no shipping / no profit → no derivation
        possible → empty string (formatter then skips the line)."""
        out = _extract_order_fields({"id": "X", "items": []}, "X")
        assert out["total_amount"] == ""


class TestFormatOrderFullDetailsShowsRealCod:
    """End-to-end: the final reply text must include 65 AED, NOT 13 AED."""

    @pytest.mark.parametrize("lang", ["english", "roman_urdu", "arabic"])
    def test_reply_shows_65_not_13(self, lang: str) -> None:
        order = _extract_order_fields(ORDER_184209, "184209")
        out = _format_order_full_details(lang, order)
        # The COD amount line must reflect 65, not 13.
        assert "65" in out
        # The supplier cost (13) may still appear in the items line, but
        # the COD/Selling-price line itself must NOT be "13 AED".
        # We check the line that contains the localized "COD" label.
        cod_line = next(
            (ln for ln in out.splitlines() if "COD" in ln or "selling" in ln.lower() or "البيع" in ln),
            None,
        )
        assert cod_line is not None, f"No COD line in reply:\n{out}"
        assert "65" in cod_line, (
            f"COD line must show 65 AED (not 13 / 18 / 34). Got: {cod_line!r}"
        )
        assert "13 AED" not in cod_line


class TestPromptTeachesFormula:
    def test_prompt_documents_cod_formula(self) -> None:
        from langchain_bot.prompts import build_system_prompt_template

        p = build_system_prompt_template()
        # The CRITICAL rule explaining the formula.
        assert "COD / selling-price computation" in p
        assert "items[].price` is the SUPPLIER cost" in p
        assert "13 + 18 + 34" in p
        assert "65 AED" in p
