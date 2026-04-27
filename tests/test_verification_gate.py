"""
Unit tests for the customer_bot_flow verification gate (TC3, TC7, TCI).

These cover the pure-Python intent detectors that run BEFORE the LLM is called.
No DB / Redis / OpenAI / Meta needed.
"""
from __future__ import annotations

import pytest

from services.customer_bot_flow.service import (
    _looks_like_account_question,
    _looks_like_order_status_question,
    _needs_account_verification,
)


class TestOrderIntentDetector:
    """`_looks_like_order_status_question` decides whether a message is a personal
    order/tracking lookup that requires verification, vs. an FAQ/policy question."""

    @pytest.mark.parametrize(
        "msg",
        [
            "my order status",
            "where is my order",
            "mera order kahan hai",
            "mere orders dikhao",
            "track my order",
            "tracking id 1234567",
            "Mujhay order details btao",
            "order id 137044",
            "show me my orders",
            "i want my order",
        ],
    )
    def test_personal_order_questions_match(self, msg: str) -> None:
        assert _looks_like_order_status_question(msg) is True

    @pytest.mark.parametrize(
        "msg",
        [
            "Mujhay orde details btao",  # TC7 typo
            "mera oder kahan hai",        # 'oder' typo
            "ordr details please",         # contracted typo
            "ordre 137044 ki info do",     # transposed typo
        ],
    )
    def test_typo_tolerant_order_words(self, msg: str) -> None:
        """TC7 — typos like 'orde' / 'oder' / 'ordr' should still trigger the gate."""
        assert _looks_like_order_status_question(msg) is True

    @pytest.mark.parametrize(
        "msg",
        [
            "what is order confirmation service",
            "order confirmation charges kya hain",
            "shipping policy kya hai",
            "return policy",
            "kya arabia reliable hai",
            "agar mera order cancel ho jaye to",
            "how much is shipping",
            "what services do you offer",
            "dropshipping kya hoti hai",
            "compensation for non-delivery",
        ],
    )
    def test_policy_and_faq_do_not_match(self, msg: str) -> None:
        """Policy / FAQ questions must NOT trigger the verification gate."""
        assert _looks_like_order_status_question(msg) is False

    @pytest.mark.parametrize(
        "msg",
        [
            "inventory question",
            "reorder process please",  # 'reorder' contains 'order' but isn't a personal order ask
        ],
    )
    def test_word_boundary_avoids_false_positives(self, msg: str) -> None:
        assert _looks_like_order_status_question(msg) is False


class TestAccountIntentDetector:
    @pytest.mark.parametrize(
        "msg",
        [
            "show my invoice",
            "saari invoices ki details do",
            "Mujjhay orders ki invoice do",  # TC9 — invoice intent
            "invoice details",
            "billing statement",
            "my account details",
        ],
    )
    def test_account_questions_match(self, msg: str) -> None:
        assert _looks_like_account_question(msg) is True

    @pytest.mark.parametrize(
        "msg",
        [
            "payment kab milti hai",
            "payment kaise hoti hai",
            "when do i get paid",
            "payment schedule kya hai",
        ],
    )
    def test_payment_policy_does_not_match(self, msg: str) -> None:
        """Generic payment-policy questions are NOT account-specific."""
        assert _looks_like_account_question(msg) is False


class TestVerificationGuard:
    """`_needs_account_verification` returns True when the bot must run the
    new/existing → email → OTP → mobile script before showing data."""

    def test_unverified_flow_needs_verification(self) -> None:
        assert _needs_account_verification({"verified": False}) is True

    def test_verified_flow_does_not_need_verification(self) -> None:
        assert _needs_account_verification({"verified": True}) is False

    def test_existing_with_seller_id_skips_script(self) -> None:
        """If seller_id is on file from a prior verify, don't re-script (TCI behaviour)."""
        flow = {"verified": False, "customer_kind": "existing", "seller_id": 12630}
        assert _needs_account_verification(flow) is False

    def test_empty_flow_needs_verification(self) -> None:
        assert _needs_account_verification({}) is True
