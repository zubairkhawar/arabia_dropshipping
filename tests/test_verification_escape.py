"""
Tests for the LLM-handled escape route out of the verification flow.

Reproduces the WhatsApp transcript bug where a customer in
``existing_awaiting_email`` typed KB questions ("Arabia dropship baaki
platforms say kesay behtar hai") and bail signals ("Bs krdo ye") and the
bot kept replying "Apne account se jura hua email address bhejein."

Now those messages bail to conversational and route through the LLM
(or legacy KB path when the flag is off).
"""
from __future__ import annotations

import pytest

from services.customer_bot_flow.service import (
    _looks_like_mobile_number,
    _looks_like_otp_code,
    _should_bail_from_verification,
)


class TestEmailStepEscape:
    """Step = existing_awaiting_email (the trap from the live transcript)."""

    @pytest.mark.parametrize(
        "msg",
        [
            # Direct bail — Roman Urdu
            "Bs krdo ye",
            "bas krdo",
            "bs krdo",
            "rehne do",
            "nahi karna",
            # Direct bail — English
            "stop",
            "cancel",
            "skip",
            "not now",
            "quit",
            "exit",
            # Topic change — KB question about Arabia
            "Arabia dropship baaki platforms say kesay behtar hai",
            "Mein arabia dropship k baray mein pooch rha hon",
            "what services do you offer",
            "how does dropshipping work",
            "kya arabia reliable hai",
            # Agent request
            "agent",
            "i want to talk to a human",
            "support please",
            "insaan se baat karwao",
        ],
    )
    def test_bail_signals_route_out(self, msg: str) -> None:
        assert _should_bail_from_verification(msg, "existing_awaiting_email") is True

    @pytest.mark.parametrize(
        "msg",
        [
            # Real email submissions must NOT bail
            "john@example.com",
            "ALI.HASSAN@gmail.com",
            "test+tag@arabia.co",
            # Plausible typo'd email — still attempted, not bailed
            "john@example",  # incomplete; legacy email_invalid handles
        ],
    )
    def test_email_attempts_do_not_bail(self, msg: str) -> None:
        # Bail only fires when text doesn't look like an email AND looks like
        # a topic change / cancel. A genuine email shape never bails.
        if "@" in msg:
            assert _should_bail_from_verification(msg, "existing_awaiting_email") is False


class TestOtpStepEscape:
    """Step = existing_awaiting_verification_code."""

    @pytest.mark.parametrize(
        "msg",
        [
            "stop",
            "rehne do",
            "agent",
            "what is your shipping policy",
        ],
    )
    def test_bail_signals_route_out(self, msg: str) -> None:
        assert _should_bail_from_verification(msg, "existing_awaiting_verification_code") is True

    @pytest.mark.parametrize("code", ["1234", "123456", "12345", "1234567"])
    def test_otp_codes_do_not_bail(self, code: str) -> None:
        assert _should_bail_from_verification(code, "existing_awaiting_verification_code") is False


class TestMobileStepEscape:
    """Step = existing_awaiting_mobile."""

    @pytest.mark.parametrize(
        "msg",
        [
            "cancel",
            "agent",
            "tell me about agency program",
        ],
    )
    def test_bail_signals_route_out(self, msg: str) -> None:
        assert _should_bail_from_verification(msg, "existing_awaiting_mobile") is True

    @pytest.mark.parametrize(
        "mobile",
        [
            "923001234567",
            "03001234567",
            "+923001234567",
            "971555516304",
            "+971 55 5516304",
            "+966 50 1234567",
        ],
    )
    def test_real_mobiles_do_not_bail(self, mobile: str) -> None:
        assert _should_bail_from_verification(mobile, "existing_awaiting_mobile") is False


class TestEdgeCases:
    def test_empty_string(self) -> None:
        assert _should_bail_from_verification("", "existing_awaiting_email") is False

    def test_short_random_text_does_not_bail(self) -> None:
        # "ok", "hi", "yes" are not bails — they're acks; the step handler
        # has its own logic for those. Bail must be specific.
        for s in ("ok", "hi", "yes", "achha", "hmm"):
            assert _should_bail_from_verification(s, "existing_awaiting_email") is False

    def test_topic_change_requires_both_topic_and_question(self) -> None:
        # Just "shipping" alone (one word, no question) shouldn't bail —
        # could be the customer thinking out loud.
        assert _should_bail_from_verification("shipping", "existing_awaiting_email") is False
        # But "shipping kya hota hai" (topic + question) should bail.
        assert _should_bail_from_verification(
            "shipping kya hota hai", "existing_awaiting_email"
        ) is True

    def test_bus_stop_does_not_false_positive(self) -> None:
        """The 'bs' regex must require it to be a whole-word, not match 'bus'."""
        # "bus stop" contains "stop" though — that one DOES bail (English bail
        # word, intentional). But "bus" alone shouldn't.
        assert _should_bail_from_verification("bus", "existing_awaiting_email") is False


class TestPredicateHelpers:
    def test_looks_like_otp_code(self) -> None:
        for s in ("1234", "12345", "123456", "1 2 3 4"):
            assert _looks_like_otp_code(s) is True
        for s in ("12", "123", "abcd1234e", "", "abcdef"):
            assert _looks_like_otp_code(s) is False

    def test_looks_like_mobile_number(self) -> None:
        for s in ("923001234567", "+92 300 1234567", "03001234567", "+971555516304"):
            assert _looks_like_mobile_number(s) is True
        for s in ("12345", "1", "no number"):
            assert _looks_like_mobile_number(s) is False
