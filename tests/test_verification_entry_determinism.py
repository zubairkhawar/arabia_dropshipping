"""
Tests for the verification ENTRY determinism fix (2026-04-29 regression).

Live transcript showed the LLM drafting the verification dialogue verbatim
without actually calling the start_verification tool, so flow.step never
advanced. Verification could never complete.

Fix: deterministic bootstrap — when an unverified customer asks for account
data OR explicitly consents to verification, the state machine advances
step BEFORE invoking the LLM. The LLM still drafts the intro reply but it
cannot fail to advance the state.

Also tests the tightened `_looks_like_invoice_for_order` so plural /
account-wide invoice queries route to `account_verify_intro` (mentions
invoices) instead of `order_verify_intro` (orders-themed).
"""
from __future__ import annotations

import pytest

from services.customer_bot_flow.service import (
    _is_explicit_verification_consent,
    _looks_like_account_question,
    _looks_like_invoice_for_order,
    _looks_like_order_status_question,
)


class TestExplicitVerificationConsent:
    """Customer says 'yes do verification' — must trigger deterministic bootstrap."""

    @pytest.mark.parametrize(
        "msg",
        [
            "Han kro verification",
            "haan kro verification",
            "yes verify me",
            "yes do verification",
            "ok verify",
            "ok kr do verification",
            "verification kro",
            "verify start kro",
            "ji haan verification kar do",
            "haa verification karein",
            "tasdeeq kro",  # Roman Urdu for 'verification' / 'verify'
            "please start verification",
            "sure go ahead with verification",
        ],
    )
    def test_consent_detected(self, msg: str) -> None:
        assert _is_explicit_verification_consent(msg) is True

    @pytest.mark.parametrize(
        "msg",
        [
            "what is verification",          # asking ABOUT verification, not consenting
            "tell me about verification",
            "verification kya hai",
            "no I don't want verification",  # wrong sentiment
            "skip verification",             # bail, not consent
            "han bhai shukriya",            # 'han' alone — too short, no verif word
            "verify",                        # no affirmative
            "",
            "what",
        ],
    )
    def test_non_consent_does_not_match(self, msg: str) -> None:
        assert _is_explicit_verification_consent(msg) is False


class TestInvoiceForOrderTightened:
    """Plural / account-wide invoice queries should NOT match `_looks_like_invoice_for_order`
    so they route to `account_verify_intro` (mentions invoices) instead of `order_verify_intro`."""

    @pytest.mark.parametrize(
        "msg",
        [
            "Mujhay meri abhi tak ki total invoices btao",  # the live transcript message
            "saari invoices btao",
            "total invoices kitni hain",
            "meri invoices ki details do",
            "invoices ki list bhejo",
            "kitni invoices hain meri",
        ],
    )
    def test_account_wide_invoice_queries_not_order_specific(self, msg: str) -> None:
        # Should NOT match _looks_like_invoice_for_order (which is for invoice-of-an-order)
        assert _looks_like_invoice_for_order(msg) is False
        # SHOULD match _looks_like_account_question (it mentions invoice + personal)
        assert _looks_like_account_question(msg) is True

    @pytest.mark.parametrize(
        "msg",
        [
            "iska invoice btao",
            "is order ka invoice batao",
            "iss order ka invoice dikha do",
            "order 137044 ka invoice btao",
            "us order ka invoice bhejo",
        ],
    )
    def test_order_specific_invoice_queries_still_match(self, msg: str) -> None:
        assert _looks_like_invoice_for_order(msg) is True


class TestVerificationBootstrapTriggers:
    """The deterministic bootstrap fires when ANY of these intent detectors is True
    AND the customer is unverified — ensuring step always advances regardless of LLM."""

    def test_order_status_intent_triggers(self) -> None:
        assert _looks_like_order_status_question("Mujhay order k baray mein janna hai") is True

    def test_account_invoice_intent_triggers(self) -> None:
        assert _looks_like_account_question("Mujhay meri abhi tak ki total invoices btao") is True

    def test_consent_after_explanation_triggers(self) -> None:
        # Bot has explained verification is needed, customer says yes → bootstrap fires
        assert _is_explicit_verification_consent("Han kro verification") is True

    def test_kb_question_does_not_trigger(self) -> None:
        # Customer asking about Arabia generally — should go to LLM-first, not verification
        assert _looks_like_order_status_question("kya arabia reliable hai") is False
        assert _looks_like_account_question("kya arabia reliable hai") is False
        assert _is_explicit_verification_consent("kya arabia reliable hai") is False
