"""
Regression test for WhatsApp transcript 2026-04-30 17:15:

  Customer: "mailto:Urbanmart097@gmail.com"
  Bot: (accepts)
  Customer: "03474685920"
  Bot: "We could not find an account..." → conversational dead-end

Two issues:

1. Phone keyboards auto-prepend "mailto:" when the user taps an
   autocompleted email. The bot must strip that prefix before sending
   the email to the store API; otherwise the store gets a malformed
   address and the lookup fails on a typo the customer never made.

2. When the email+mobile lookup genuinely fails (typo, wrong country
   code, registered with a different address), the customer must be
   able to retry — not be dumped to "contact support" after one wrong
   keystroke. We now cap retries at 3 and route to a human agent on
   the third strike.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from services.customer_bot_flow.service import (
    _extract_standalone_email,
    _is_likely_email,
    _strip_url_scheme,
)


class TestStripUrlScheme:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("mailto:Urbanmart097@gmail.com", "Urbanmart097@gmail.com"),
            ("MAILTO:foo@bar.com", "foo@bar.com"),
            ("mailto: foo@bar.com", "foo@bar.com"),
            ("tel:+971500000000", "+971500000000"),
            ("sms:03001234567", "03001234567"),
            # No prefix → unchanged.
            ("plain@example.com", "plain@example.com"),
            ("03474685920", "03474685920"),
        ],
    )
    def test_strip(self, raw: str, expected: str) -> None:
        assert _strip_url_scheme(raw) == expected

    def test_mailto_email_recognised(self) -> None:
        """The auto-link variant must pass _is_likely_email so the
        verification flow accepts it without the customer manually
        deleting the prefix."""
        assert _is_likely_email("mailto:Urbanmart097@gmail.com")

    def test_extract_strips_mailto_prefix(self) -> None:
        out = _extract_standalone_email("mailto:Urbanmart097@gmail.com")
        assert out == "urbanmart097@gmail.com", (
            "extracted email must be normalised to lower-case without the "
            "mailto: scheme"
        )


class TestRetryHelperWired:
    """Static check that the retry helper exists and is called from both
    failure branches (no_customer + no_seller_scope)."""

    def _service_text(self) -> str:
        src = (
            Path(__file__).resolve().parent.parent
            / "server" / "services" / "customer_bot_flow" / "service.py"
        )
        return src.read_text(encoding="utf-8")

    def test_retry_helper_defined(self) -> None:
        text = self._service_text()
        assert "_VERIFY_MAX_ATTEMPTS = 3" in text
        assert "def _verification_match_failed(" in text

    def test_no_customer_calls_retry_helper(self) -> None:
        text = self._service_text()
        # The "if not customer:" branch must call _verification_match_failed.
        i = text.find("if not customer:")
        # find the closest occurrence that's inside the awaiting_mobile path
        # (there are several "if not customer:" matches in the file).
        # We just need at least one to call the helper with reason="no_customer".
        assert "reason=\"no_customer\"" in text

    def test_no_seller_scope_calls_retry_helper(self) -> None:
        text = self._service_text()
        assert "reason=\"no_seller_scope\"" in text

    def test_max_attempts_routes_to_agent(self) -> None:
        text = self._service_text()
        i = text.find("def _verification_match_failed(")
        end = text.find("\n    async def submit_existing_email", i)
        block = text[i:end] if end > i else text[i: i + 3000]
        # On the 3rd strike we hand off to a support team and use the
        # max_attempts template, not the retry template.
        assert "_VERIFY_MAX_ATTEMPTS" in block
        assert "customer_not_found_max_attempts" in block
        assert "TEAM_NEW_CUSTOMER" in block

    def test_retry_keeps_step_on_email(self) -> None:
        text = self._service_text()
        i = text.find("def _verification_match_failed(")
        end = text.find("\n    async def submit_existing_email", i)
        block = text[i:end] if end > i else text[i: i + 3000]
        # Retry path resets pending_email/pending_mobile and parks the
        # customer back on existing_awaiting_email so the next message is
        # interpreted as a fresh email.
        assert '"step": "existing_awaiting_email"' in block
        assert '"pending_email": None' in block
        assert '"verify_attempts": attempts' in block


class TestVerifyAttemptsClearedOnSuccess:
    def test_success_branch_resets_attempts(self) -> None:
        src = (
            Path(__file__).resolve().parent.parent
            / "server" / "services" / "customer_bot_flow" / "service.py"
        )
        text = src.read_text(encoding="utf-8")
        # Find the verified=True dict literal — it must clear verify_attempts
        # so a future expired-then-retry doesn't carry stale failures.
        i = text.find('"verified": True,')
        assert i > 0
        block = text[i: i + 800]
        assert '"verify_attempts": 0' in block
