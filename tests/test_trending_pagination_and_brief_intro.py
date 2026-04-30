"""
Regression tests for fixes from WhatsApp transcript 2026-04-29 14:28-14:30.

(Original ① — the pagination short-circuit — was deleted on 2026-04-30
when `_wants_trending_more` was removed. Pagination is now handled
naturally by the trending LLM-runner via prompt rule 4 + memory.shown_ids
tracking, since page-size 50 covers the full catalogue on the first
turn for typical tenants. The empty-cache branch refetches via
`_show_trending_for_country` if the runner fails.)

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
)


# ─────────────────────────────────────────────────────────────────────────────
# ① Pagination handler (deterministic short-circuit deleted 2026-04-30)
# ─────────────────────────────────────────────────────────────────────────────
class TestPaginationHandledByLLMRunner:
    def test_handler_always_calls_llm_runner(self) -> None:
        """The trending_showing_products handler now calls
        `_try_trending_llm()` unconditionally — there's no longer a
        pagination short-circuit that bypasses the runner."""
        src = (
            Path(__file__).resolve().parent.parent
            / "server" / "services" / "customer_bot_flow" / "service.py"
        )
        text = src.read_text(encoding="utf-8")
        i = text.find('if step == "trending_showing_products":')
        assert i > 0
        block = text[i: i + 2000]
        # New shape: unconditional `await _try_trending_llm()`.
        assert "llm_res = await _try_trending_llm()" in block
        # Old shape (no longer present).
        assert "_wants_trending_more(text)" not in block
        assert "_is_pagination_only" not in block

    def test_wants_trending_more_helper_deleted(self) -> None:
        from services.customer_bot_flow import service as svc

        assert not hasattr(svc, "_wants_trending_more"), (
            "_wants_trending_more was supposed to be deleted along with the "
            "deterministic pagination branch on 2026-04-30"
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
