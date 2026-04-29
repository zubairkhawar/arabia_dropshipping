"""
Defensive guards: phone-shaped strings must NEVER be treated as order IDs.

WhatsApp transcript on 2026-04-29 13:23 showed the bot looking up the
customer's typed mobile number ("03474685920") as an order — got "not
found" — explained to the customer that "order #03474685920" wasn't in
their records. Embarrassing. Confusing.

Three defenses now in place:

  1. _is_likely_order_id_only — rejects 10+ digit strings
  2. _extract_order_id_from_message — rejects phone-shaped candidates
  3. handle_lookup_order — refuses 10+ digit args with not_an_order_id_phone_shaped
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.ai_orchestrator_service.services import _extract_order_id_from_message
from services.customer_bot_flow.service import _is_likely_order_id_only


PK_PHONE = "923474685920"


class TestIsLikelyOrderIdOnly:
    @pytest.mark.parametrize(
        "s",
        [
            "137044",         # real Arabia order id (6 digits)
            "177089",         # real
            "182970",         # real
            "1234",            # min length
            "999999",          # 6 digits
            "12345678",        # 8 digits — borderline accepted
            "123456789",       # 9 digits — still order-id-shaped (max)
            "#137044",         # with hash
            "#137044  ",       # with whitespace
        ],
    )
    def test_real_order_ids_accepted(self, s: str) -> None:
        assert _is_likely_order_id_only(s) is True, f"should accept {s!r}"

    @pytest.mark.parametrize(
        "s",
        [
            "03474685920",       # PK mobile (the live transcript trigger)
            "0347 4685 920",     # PK mobile with spaces
            "+923474685920",     # international PK
            "971555516304",      # UAE mobile
            "+971555516304",     # UAE international
            "966501234567",      # KSA mobile
            "12345678901",       # 11 digits (any phone-length)
            "1234567890",        # 10 digits with leading 1
            "0123456789",        # 10 digits leading 0
            "abc",                # too short
            "abc123",             # contains letters → fullmatch fails
            "",                   # empty
            "12",                 # too short
            "123",                # too short
        ],
    )
    def test_phone_shaped_or_invalid_rejected(self, s: str) -> None:
        assert _is_likely_order_id_only(s) is False, f"should reject {s!r}"


class TestExtractOrderIdFromMessage:
    """Phone-shaped numbers must not be extracted as order IDs even when
    prefixed with 'order' — the customer almost certainly typed their mobile
    by mistake, not an order id."""

    @pytest.mark.parametrize(
        "msg",
        [
            "03474685920",
            "order 03474685920",
            "order #03474685920",
            "Mera order 03474685920 hai",
            "order id 03474685920",
            "+923474685920",
        ],
    )
    def test_phone_shapes_not_extracted(self, msg: str) -> None:
        assert _extract_order_id_from_message(msg, PK_PHONE) is None, (
            f"phone-shaped value should not be extracted from {msg!r}"
        )

    @pytest.mark.parametrize(
        "msg, expected",
        [
            ("order 137044", "137044"),
            ("Mujhay order #177089 ki details", "177089"),
            ("order id 182970", "182970"),
            ("kya 191491 deliver hua", "191491"),
        ],
    )
    def test_real_order_ids_extracted(self, msg: str, expected: str) -> None:
        assert _extract_order_id_from_message(msg, PK_PHONE) == expected


class TestHandleLookupOrderHandler:
    """Last line of defence: even if the LLM ignores its prompt and passes a
    phone-shaped string, the handler refuses with `not_an_order_id_phone_shaped`."""

    @pytest.mark.asyncio
    async def test_phone_shaped_args_rejected_by_handler(self) -> None:
        from langchain_bot.tools.handlers import ToolContext, handle_lookup_order
        from langchain_bot.tools.schemas import LookupOrderArgs

        ctx = ToolContext(
            db=MagicMock(),
            tenant_id=1,
            customer_phone="03474685920",
            conversation_id=1,
            language="english",
            store_client=MagicMock(),
            bot_flow={"verified": True, "seller_id": "12630", "step": "conversational"},
        )

        result = await handle_lookup_order(LookupOrderArgs(order_id="03474685920"), ctx)
        assert result.ok is False
        assert "not_an_order_id_phone_shaped" in (result.error or "")
        # Importantly, the store_client must NOT have been called — we shouldn't
        # waste API quota on a doomed lookup.
        ctx.store_client.get_order_by_id.assert_not_called()

    @pytest.mark.asyncio
    async def test_real_order_id_still_accepted(self) -> None:
        from langchain_bot.tools.handlers import ToolContext, handle_lookup_order
        from langchain_bot.tools.schemas import LookupOrderArgs

        store = MagicMock()
        store.get_order_by_id = AsyncMock(return_value={"id": "137044", "status": "Delivered"})
        store.get_order_by_number = AsyncMock(return_value=None)
        store.get_order_tracking = AsyncMock(return_value={})
        store.get_order_invoice_mapping = AsyncMock(return_value={})

        ctx = ToolContext(
            db=MagicMock(),
            tenant_id=1,
            customer_phone="03474685920",
            conversation_id=1,
            language="english",
            store_client=store,
            bot_flow={"verified": True, "seller_id": "12630", "step": "conversational"},
        )

        result = await handle_lookup_order(LookupOrderArgs(order_id="137044"), ctx)
        assert result.ok is True
        store.get_order_by_id.assert_called()
