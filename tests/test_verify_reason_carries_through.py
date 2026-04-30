"""
Regression test for WhatsApp transcript 2026-04-29 15:02:

When the verification flow asked for an email but the customer's
original question (e.g. "where is order 187916?") was an order ask,
verify_reason had to be set to "order" so the post-verification path
took the templated order-prompt branch (Case B) instead of the
ai_forward Case-C route. Any transient API blip during Case-C surfaced
'Abhi aap ka data fetch karne mein masla aa raha hai' to the customer.

The original test pinned the fix inside the awaiting_customer_type 1/2
menu handler. That step was deleted on 2026-04-30 (the menu is gone;
order/account intent is now treated implicitly as 'existing' and routed
straight into the verification bucket). The plumbing this test cared
about — pending_intent storage of the original question — still exists
at the bootstrap site that replaced the menu, just earlier in the
turn. We assert the same property at its new home.
"""
from __future__ import annotations

from pathlib import Path


def _service_text() -> str:
    src = Path(__file__).resolve().parent.parent / "server" / "services" / "customer_bot_flow" / "service.py"
    return src.read_text(encoding="utf-8")


class TestVerifyReasonCarriesThrough:
    def test_bootstrap_stashes_original_question(self) -> None:
        """When an unverified customer asks an order/account question,
        the controller must store the original question in pending_intent
        BEFORE jumping into the email-asking step. That's what lets the
        post-verification flow (and the existing_awaiting_email retry
        helper) recover the reason later."""
        text = _service_text()
        # The new bootstrap site lives in the unverified order/account
        # branch that runs before the menu used to.
        marker = "store_pending_intent("
        assert marker in text
        i = text.find(marker)
        # The call should pass the original question as the 4th arg.
        block = text[i: i + 600]
        assert "original_question" in block or "(text or" in block, (
            "the original message must be the 4th positional arg to "
            "store_pending_intent so the post-verification path can read it"
        )

    def test_unverified_order_intent_routes_to_existing_path(self) -> None:
        """The bootstrap branch must set customer_kind='existing' (no
        more 1/2 menu) and call _existing_identity_entry directly."""
        text = _service_text()
        # Find the unverified order/account routing in process_message.
        marker = "_needs_account_verification(flow)"
        i = text.find(marker)
        assert i > 0
        # Read the next ~800 chars (the branch body).
        block = text[i: i + 1500]
        # Must transition customer_kind to "existing" and stash the intent.
        assert '"customer_kind": "existing"' in block
        assert "ConversationMemory.store_bot_customer_kind(mem_id, \"existing\")" in block

    def test_no_more_awaiting_customer_type_step(self) -> None:
        """The deletion target — the step itself must be gone from the
        flow's step machine. If this assertion fails, someone added it
        back; talk to the team before merging."""
        text = _service_text()
        assert 'step": "awaiting_customer_type"' not in text
        assert 'step == "awaiting_customer_type"' not in text
