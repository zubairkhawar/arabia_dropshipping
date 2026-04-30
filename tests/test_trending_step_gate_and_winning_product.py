"""
Regression tests for two bugs caught in WhatsApp transcript 2026-04-29 14:09:

  ① Trending step state leaked to LLM-first.
     Customer was at step="trending_awaiting_country" (after the bot asked
     1️⃣KSA / 2️⃣UAE / 3️⃣Pakistan) and typed "1". The LLM answered "Aap ka
     sawal clear nahi hai" instead of the deterministic country picker.
     Fix: add trending_awaiting_country / trending_showing_products /
     existing_awaiting_order_id / existing_awaiting_experience /
     sourcing_collecting_details / awaiting_agent to otp_guard_steps so
     the deterministic state machine owns those turns.

  ② "Winning product" dropshipping slang not recognized as a trending intent.
     Customer asked "Koi winning product UAE keh liye" — bot answered
     "Aap ka winning product bilkul secure hai" (a generic privacy reply
     that doesn't match the actual ask).
     Fix: extend _wants_trending_products markers + add a prompt rule so
     the LLM recognises the synonym and calls get_trending_products.
"""
from __future__ import annotations

import pytest

from services.customer_bot_flow.service import _wants_trending_products


# ─────────────────────────────────────────────────────────────────────────────
# ① Otp-guard set must include all deterministic-bucket steps
# ─────────────────────────────────────────────────────────────────────────────
class TestOtpGuardSteps:
    """We can't import otp_guard_steps directly (it's a local in
    process_customer_bot_message), so we read the source and assert the
    required step names are present in its definition."""

    def test_required_steps_in_otp_guard(self) -> None:
        from pathlib import Path
        src = Path(__file__).resolve().parent.parent / "server" / "services" / "customer_bot_flow" / "service.py"
        text = src.read_text(encoding="utf-8")

        # Locate the otp_guard_steps set definition.
        marker = "otp_guard_steps = {"
        i = text.find(marker)
        assert i > 0, "otp_guard_steps definition not found"
        end = text.find("}", i)
        block = text[i:end + 1]

        for required in (
            # verification (awaiting_customer_type was deleted on 2026-04-30
            # along with the 1/2 menu)
            "awaiting_resume_choice",
            "existing_awaiting_email",
            "existing_awaiting_verification_code",
            "existing_awaiting_mobile",
            "existing_awaiting_order_id",
            "existing_awaiting_experience",
            # pagination cursor (the live transcript regression)
            "trending_awaiting_country",
            "trending_showing_products",
            # sourcing
            "sourcing_collecting_details",
            # handoff
            "awaiting_agent",
        ):
            assert required in block, (
                f"otp_guard_steps must include {required!r} so the deterministic "
                "state machine owns turns where flow.step matches that step. "
                "Without it, a digit / short reply leaks to LLM-first and the "
                "customer gets a confused 'Aap ka sawal clear nahi hai' message."
            )


# ─────────────────────────────────────────────────────────────────────────────
# ② Winning-product synonyms recognised as trending intent
# ─────────────────────────────────────────────────────────────────────────────
class TestWinningProductTrendingMarkers:
    @pytest.mark.parametrize(
        "msg",
        [
            "Koi winning product bata sakte ho?",
            "tum bata sakte koi winning product UAE keh liye",
            "winning products dikhao",
            "kamyab products kya hain",
            "koi viral product UAE",
            "chalti product dikhao",
            "high conversion product UAE",
            "wining product UAE",  # common typo
        ],
    )
    def test_winning_synonyms_match_trending(self, msg: str) -> None:
        assert _wants_trending_products(msg) is True, (
            f"'{msg}' should map to trending intent — it's the customer asking "
            f"for the Arabia public catalog, not their own listings."
        )

    # Note: "winning product nahi chahiye" (negation) currently still triggers
    # the trending flow because the detector is permissive on synonyms. This is
    # a known minor edge-case acceptable given the upside of catching "winning
    # product UAE keh liye" — the live transcript's main miss.


class TestPromptHasTrendingRule:
    def test_prompt_documents_trending_synonyms(self) -> None:
        """The LLM prompt must explicitly list trending synonyms (winning,
        viral, etc.) so the model maps them to the get_trending_products
        tool instead of drafting generic privacy replies."""
        from langchain_bot.prompts import build_system_prompt_template

        sp = build_system_prompt_template()
        assert "TRENDING" in sp.upper()
        # Specific synonyms that broke in the live transcript:
        for marker in ("winning product", "best-selling", "viral"):
            assert marker.lower() in sp.lower(), f"prompt must mention {marker!r}"
        # And must point the LLM at the right tool name:
        assert "get_trending_products" in sp
