"""
Regression tests for two fixes from WhatsApp transcript 2026-04-29 14:28-14:30:

  ① Trending pagination (`Aur dikhao` / `Show more`) hit the LLM-unavailable
     fallback because `_try_trending_llm` ran BEFORE the deterministic
     pagination check. When the LLM trending runner failed (rate limit
     from another job consuming OpenAI quota), the customer saw 'Hamare
     server par mukhtasar technical masla'. Pagination is a pure cursor
     advance — it shouldn't go through the LLM at all.

  ② The verbose `account_verify_intro` / `order_verify_intro` templates
     (200+ words explaining the verification process) are no longer
     used. `_existing_identity_entry` now shows the short `ask_email`
     template directly. Customer typing an order id at the email step
     stashes it as `pending_order_ref` instead of showing 'order not
     found' (which was misleading — no verification = no seller scope).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from services.customer_bot_flow.service import (
    _existing_identity_entry,
    _wants_trending_more,
)


# ─────────────────────────────────────────────────────────────────────────────
# ① Pagination short-circuit
# ─────────────────────────────────────────────────────────────────────────────
class TestPaginationShortCircuit:
    """The trending_showing_products handler must skip the LLM trending
    runner when the customer's message is unambiguously pagination."""

    def test_aur_dikhao_is_pagination(self) -> None:
        assert _wants_trending_more("Aur dikhao") is True

    def test_show_more_is_pagination(self) -> None:
        assert _wants_trending_more("Show more") is True

    def test_more_is_pagination(self) -> None:
        assert _wants_trending_more("more") is True

    def test_random_message_is_not_pagination(self) -> None:
        # The bail-to-LLM path should still fire for genuinely off-topic input.
        assert _wants_trending_more("kya arabia reliable hai") is False

    def test_handler_skips_llm_for_pagination(self) -> None:
        """Read service.py and assert the handler structure: pagination
        intent skips the LLM runner."""
        src = Path(__file__).resolve().parent.parent / "server" / "services" / "customer_bot_flow" / "service.py"
        text = src.read_text(encoding="utf-8")
        # Find the trending_showing_products step block
        i = text.find('if step == "trending_showing_products":')
        assert i > 0, "trending step handler not found"
        block = text[i: i + 2000]
        # Must contain the short-circuit guard before _try_trending_llm
        assert "_is_pagination_only = _wants_trending_more(text)" in block, (
            "trending_showing_products must compute a pagination-only flag "
            "BEFORE invoking the LLM trending runner"
        )
        assert "if _is_pagination_only else await _try_trending_llm()" in block, (
            "the LLM trending runner must be skipped when pagination_only is True"
        )


# ─────────────────────────────────────────────────────────────────────────────
# ② Verify-intro template removed; ask_email shown directly
# ─────────────────────────────────────────────────────────────────────────────
class TestExistingIdentityEntry:
    @pytest.mark.parametrize("intro_key", ["account_verify_intro", "order_verify_intro"])
    def test_returns_short_ask_email_message(self, intro_key: str) -> None:
        flow = {"customer_kind": "existing", "lang": "roman_urdu"}
        new_flow, msg = _existing_identity_entry(
            flow,
            "roman_urdu",
            verify_reason="order",
            pending_order_ref=None,
            intro_key=intro_key,
        )
        # No more verbose 'Main samajh gaya ke aap order details dekhna chahte hain'
        # paragraph. The reply is now just the ask-email prompt.
        assert "Main samajh gaya ke aap" not in msg, (
            f"verbose verify intro must not appear with intro_key={intro_key!r}"
        )
        assert "Aap kaun sa bhejna chahenge" not in msg
        # Short reply mentions email.
        assert "email" in msg.lower() or "Email" in msg
        # Step transitions to email-asking step.
        assert new_flow["step"] == "existing_awaiting_email"

    def test_expired_reverify_keeps_brief_explanation(self) -> None:
        """Customer returning after 3-day expiry needs a brief 'your previous
        verification expired' line so they know why they're being prompted again."""
        flow = {"customer_kind": "existing", "lang": "roman_urdu"}
        _, msg = _existing_identity_entry(
            flow,
            "roman_urdu",
            verify_reason="order",
            pending_order_ref=None,
            intro_key="verification_expired_reverify",
        )
        assert "expire" in msg.lower() or "expired" in msg.lower() or "expir" in msg.lower()
        # Still ends with email ask.
        assert "email" in msg.lower()

    def test_pending_order_ref_persisted(self) -> None:
        flow = {"customer_kind": "existing"}
        new_flow, _msg = _existing_identity_entry(
            flow,
            "roman_urdu",
            verify_reason="order",
            pending_order_ref="157955",
            intro_key="account_verify_intro",
        )
        assert new_flow["pending_order_ref"] == "157955"
