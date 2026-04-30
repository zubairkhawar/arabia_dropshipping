"""
Regression test for WhatsApp transcript 2026-04-30 21:06:

  Customer (verified, step=existing_awaiting_order_id, bot just said
  "share your order number or I can show your recent orders"):
    "arabia dropship zambeel say kesay behtar hai"
  Bot:
    "Mujhe aapke account mein yeh order nahi mila. Order number check
    karke dobara try karein..."

Root cause: the existing_awaiting_order_id step handler took ANY
message and looked it up as an order id. A natural-language KB
question got passed through as an order ref, returned not_found, and
the customer received the misleading "order not found" template.

Fix: the handler now checks whether the message actually looks like
an order ask (5–7 digit order id, order-status phrasing, tracking-by-id,
invoice-by-id, or has an embedded order id). If not, bail to ai_forward
(KB question gets a KB answer) or pivot if it's just a greeting / ack.
"""
from __future__ import annotations

from pathlib import Path

import pytest


SERVICE = (
    Path(__file__).resolve().parent.parent
    / "server" / "services" / "customer_bot_flow" / "service.py"
)


def _service() -> str:
    return SERVICE.read_text(encoding="utf-8")


class TestHandlerHasTopicChangeEscape:
    def test_handler_checks_for_order_ask(self) -> None:
        text = _service()
        i = text.find('if step == "existing_awaiting_order_id":')
        end = text.find('if step ==', i + 50)
        block = text[i:end] if end > i else text[i: i + 4000]
        # The handler must classify the message as order-ask first,
        # before treating it as an order-id ref.
        assert "looks_like_order_ask" in block

    def test_non_order_ask_bails_to_ai_forward(self) -> None:
        text = _service()
        i = text.find('if step == "existing_awaiting_order_id":')
        end = text.find('if step ==', i + 50)
        block = text[i:end] if end > i else text[i: i + 4000]
        # Topic-change branch must call ai_forward (NOT the deterministic
        # _lookup_order with the natural-language string).
        assert "if not looks_like_order_ask:" in block
        assert "ai_forward(\"[Customer question] \"" in block

    def test_greeting_pivots_instead(self) -> None:
        text = _service()
        i = text.find('if step == "existing_awaiting_order_id":')
        end = text.find('if step ==', i + 50)
        block = text[i:end] if end > i else text[i: i + 4000]
        assert "_looks_like_greeting(raw)" in block
        assert "_is_pure_ack_or_thanks(raw)" in block


class TestOrderAskClassifierStillRecognisesValidOrderInputs:
    """Make sure we didn't accidentally make the topic-change check too
    aggressive — the handler must still recognise legitimate order-id
    inputs at this step."""

    @pytest.mark.parametrize(
        "msg",
        [
            "157955",        # bare order id
            "#177089",       # order id with hash
            "order 137044",  # order id phrase
            "where is my order 177089",  # order status question
            "track my order PT25238278", # tracking by id
            "show me invoice for order 177089",  # invoice for order
        ],
    )
    def test_order_input_recognised(self, msg: str) -> None:
        from services.customer_bot_flow import service as svc

        # Build the same boolean expression the handler uses.
        looks_like_order_ask = (
            svc._is_likely_order_id_only(msg)
            or svc._looks_like_order_status_question(msg)
            or svc._looks_like_tracking_by_id(msg)
            or svc._looks_like_invoice_by_id(msg)
            or svc._looks_like_invoice_for_order(msg)
            or bool(svc._extract_order_id_from_message(msg, None))
        )
        assert looks_like_order_ask, (
            f"{msg!r} should still be recognised as an order ask at "
            "the existing_awaiting_order_id step"
        )


class TestNonOrderInputsCorrectlyDetectedAsTopicChange:
    """The actual transcript phrasing + similar topic-change patterns
    must NOT be classified as order asks."""

    @pytest.mark.parametrize(
        "msg",
        [
            # The actual bug transcript
            "arabia dropship zambeel say kesay behtar hai",
            # Variations
            "arabia dropship vs zambeel comparison",
            "what is dropshipping",
            "shipping rates kya hain",
            "payment kab hoti hai",
            "fulfillment service kya hai",
            "delivery ratio kya hai mera",
            "kya commission rate hai",
            # Greetings + acks
            "hi",
            "thanks",
            "shukriya",
            "ok",
        ],
    )
    def test_topic_change_not_classified_as_order(self, msg: str) -> None:
        from services.customer_bot_flow import service as svc

        looks_like_order_ask = (
            svc._is_likely_order_id_only(msg)
            or svc._looks_like_order_status_question(msg)
            or svc._looks_like_tracking_by_id(msg)
            or svc._looks_like_invoice_by_id(msg)
            or svc._looks_like_invoice_for_order(msg)
            or bool(svc._extract_order_id_from_message(msg, None))
        )
        assert not looks_like_order_ask, (
            f"{msg!r} is a topic change at the order-id step and must "
            "NOT be looked up as an order ref — that produces the "
            "misleading 'order not found' reply"
        )
