"""
Tests that verify the prompt rules added for TC1-L are actually present in the
rendered system prompt. These don't call OpenAI — they confirm the rule strings
are wired into `build_system_prompt_template()` and the context formatter so
the LLM will see them at inference time.
"""
from __future__ import annotations

import pytest

from langchain_bot.context_format import build_customer_identity_summary
from langchain_bot.prompts import (
    build_system_prompt_template,
    knowledge_gap_reply,
    llm_unavailable_reply,
)


@pytest.fixture
def system_prompt() -> str:
    return build_system_prompt_template()


class TestCoreRulesPresent:
    @pytest.mark.parametrize(
        "phrase",
        [
            # CORE rules added in this session
            "apology-only",                # never apologise without explanation
            "Privacy",                     # don't reveal stored email/phone
            "kyun nahi kar sakte",         # 'why can't you' explainer
            "Always address the LATEST",   # don't drop a turn
            # Verification gate
            "VERIFICATION GATE",
            "new** or **existing",
            # Store API error
            "Store API error while loading customer/orders",
            # Patterns
            "not found",                   # wrong order # handling (TCH)
            "csv",                         # CSV offer (TCG, TCL)
        ],
    )
    def test_rule_phrases_in_prompt(self, system_prompt: str, phrase: str) -> None:
        assert phrase.lower() in system_prompt.lower(), (
            f"Expected rule fragment {phrase!r} not present in system prompt"
        )

    def test_core_facts_still_present(self, system_prompt: str) -> None:
        # Sanity: previous facts must not be lost in the edits.
        for fact in [
            "every **Wednesday**",
            "5 AED",            # UAE return
            "10 AED",           # KSA return
            "Crypto if >1000 AED",
        ]:
            assert fact in system_prompt, f"Lost critical fact: {fact}"


class TestFallbackMessages:
    """`llm_unavailable_reply` is shown when the LLM call hard-fails after retries.
    The text was tightened so it clearly reads as a transient server issue rather
    than a refusal of the customer's question (TC8)."""

    def test_unavailable_reply_includes_resend_hint(self) -> None:
        out = llm_unavailable_reply("english")
        assert "resend" in out.lower() or "again" in out.lower()
        assert "agent" in out.lower()

    def test_unavailable_reply_roman_urdu(self) -> None:
        out = llm_unavailable_reply("roman_urdu")
        assert "agent" in out.lower()
        # Should NOT contain the old vague phrasing implying user error
        assert "abhi jawab" not in out.lower()

    def test_knowledge_gap_reply_offers_agent(self) -> None:
        out = knowledge_gap_reply("english")
        assert "agent" in out.lower()


class TestStoreContextErrorSurfaced:
    """The orchestrator sets `store_context_error` on store-API failures and the
    identity summary must surface it to the LLM (TCJ)."""

    def test_error_line_present_when_set(self) -> None:
        ctx = {
            "customer": {},
            "is_store_customer": False,
            "verification_method": "none",
            "store_context_error": "orders_all_total:HTTPStatusError(...)",
        }
        out = build_customer_identity_summary(ctx)
        assert "Store API error while loading customer/orders" in out

    def test_error_line_absent_when_no_error(self) -> None:
        ctx = {
            "customer": {},
            "is_store_customer": False,
            "verification_method": "none",
            "store_context_error": None,
        }
        out = build_customer_identity_summary(ctx)
        assert "Store API error" not in out


class TestPrecomputedTotalsSurfaced:
    """Pre-computed `total_order_count` and `total_paid_amount` must appear in
    the identity block so the LLM doesn't re-count or hallucinate (TCB, TCK)."""

    def test_total_order_count_surfaced(self) -> None:
        ctx = {
            "customer": {},
            "is_store_customer": True,
            "verification_method": "email",
            "total_order_count": 590,
        }
        out = build_customer_identity_summary(ctx)
        assert "590" in out
        assert "total order count" in out.lower()

    def test_total_paid_amount_surfaced(self) -> None:
        ctx = {
            "customer": {},
            "is_store_customer": True,
            "verification_method": "email",
            "total_paid_amount": 9506.0,
        }
        out = build_customer_identity_summary(ctx)
        assert "9506" in out
        assert "total paid" in out.lower()

    def test_zero_totals_not_surfaced(self) -> None:
        """Don't leak '0 orders' / '0 paid' — only show when meaningful."""
        ctx = {
            "customer": {},
            "is_store_customer": True,
            "verification_method": "email",
            "total_order_count": 0,
            "total_paid_amount": 0,
        }
        out = build_customer_identity_summary(ctx)
        assert "total order count" not in out.lower()
        assert "total paid" not in out.lower()


class TestRequestedOrderNotFound:
    """When customer asks for a specific order # that doesn't exist, the LLM
    must be told explicitly (TCH)."""

    def test_not_found_signal_in_identity(self) -> None:
        ctx = {
            "customer": {},
            "is_store_customer": True,
            "verification_method": "email",
            "requested_order_not_found": "999999",
        }
        out = build_customer_identity_summary(ctx)
        assert "999999" in out
        assert "not found" in out.lower()

    def test_no_signal_when_field_unset(self) -> None:
        ctx = {
            "customer": {},
            "is_store_customer": True,
            "verification_method": "email",
        }
        out = build_customer_identity_summary(ctx)
        assert "not found" not in out.lower()
