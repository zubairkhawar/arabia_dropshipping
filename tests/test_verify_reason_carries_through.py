"""
Regression test for WhatsApp transcript 2026-04-29 15:02:

When customer types '2' to the 1/2 menu (choosing 'existing'), the
awaiting_customer_type handler used to call _existing_identity_entry
with verify_reason=None. That meant the post-verification path
couldn't tell the customer's original ask was about orders — so it
took the ai_forward Case-C route (full LLM context fetch) instead of
the templated order-prompt path. Any transient API blip during the
context fetch then surfaced 'Abhi aap ka data fetch karne mein masla
aa raha hai' to the customer.

Fix: read pending_intent.original_question after the customer picks
'existing', classify the reason from it, and pass it into
_existing_identity_entry. Post-verification then takes the right
deterministic branch (Case B for reason=order — templated order
prompt, no LLM context fetch).

This test reads service.py and asserts the pending_intent-reading
branch is in place.
"""
from __future__ import annotations

from pathlib import Path


def _service_text() -> str:
    src = Path(__file__).resolve().parent.parent / "server" / "services" / "customer_bot_flow" / "service.py"
    return src.read_text(encoding="utf-8")


class TestVerifyReasonCarriesThrough:
    def test_existing_choice_reads_pending_intent(self) -> None:
        text = _service_text()
        # Find the awaiting_customer_type → existing branch
        i = text.find('if choice == "existing":')
        assert i > 0, "awaiting_customer_type existing-branch not found"
        block = text[i: i + 2000]
        # The fix should: (1) call get_pending_intent(mem_id),
        # (2) classify _orig_q with the order/account detectors,
        # (3) pass verify_reason=existing_reason instead of None.
        assert "ConversationMemory.get_pending_intent(mem_id)" in block, (
            "must read pending_intent so we know the customer's original ask"
        )
        assert "_looks_like_order_status_question(_orig_q)" in block, (
            "must classify against the original question, not the '2' reply"
        )
        assert "verify_reason=existing_reason" in block, (
            "must pass the classified reason into _existing_identity_entry"
        )
        # And it should NOT regress to verify_reason=None on this branch.
        # Search for that exact pattern still being present in this block:
        legacy_call = "verify_reason=None,\n                pending_order_ref=None,"
        # The legacy call may still exist in OTHER branches, so we just check
        # this specific branch doesn't contain it.
        existing_branch = block[: block.find("if _wants_non_trending_products(text):") if "if _wants_non_trending_products" in block else len(block)]
        assert legacy_call not in existing_branch, (
            "the existing-customer branch must not pass verify_reason=None — "
            "the post-verification routing depends on the reason."
        )

    def test_pending_order_ref_extracted_from_original_question(self) -> None:
        """If the customer's original question included an order id, that
        ref should be persisted as pending_order_ref so the post-verification
        path can look up the order directly (Case A)."""
        text = _service_text()
        i = text.find('if choice == "existing":')
        block = text[i: i + 2000]
        assert "existing_pre_ref" in block
        assert "_extract_order_id_from_message(_orig_q, phone)" in block, (
            "must extract order id from the original question"
        )
        assert "pending_order_ref=existing_pre_ref" in block
