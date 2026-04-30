"""
Tests for the verification bootstrap migration (2026-04-30).

Before: an early `needs_verification_bootstrap` regex gate inside
process_message blocked LLM-first whenever an unverified customer's
message looked like an order / invoice / account / tracking question
(or a bare order id, or explicit verification consent, or a bare email
address). The deterministic state machine then forced the flow into
existing_awaiting_email regardless of LLM behaviour.

After: only two narrow deterministic fast-paths remain — bare email
and explicit verification consent. Everything else (order status, "kahan
hai mera parcel", "invoice btao", "157955" alone, "kitne orders deliver
hue") goes through the LLM-first orchestrator. The LLM calls
`start_verification` per the strict VERIFICATION GATE prompt rule, and
the `verification_signal` handler in process_message advances the step
to existing_awaiting_email.

These tests verify the deletion is complete:
1. The wide regex gate (`needs_verification_bootstrap`) is gone.
2. The narrow fast-path (`bare_email_or_consent`) is in place and
   only triggers on bare email / explicit consent.
3. The LLM-first gate condition uses `bare_email_or_consent`, not
   `needs_verification_bootstrap`.
4. The `verification_signal` handler still advances the step.
5. The system prompt now teaches the LLM the specific phrasings that
   MUST call `start_verification`, since there's no regex safety net.
"""
from __future__ import annotations

from pathlib import Path

import pytest


SERVICE = (
    Path(__file__).resolve().parent.parent
    / "server" / "services" / "customer_bot_flow" / "service.py"
)
PROMPTS = (
    Path(__file__).resolve().parent.parent
    / "server" / "langchain_bot" / "prompts.py"
)


def _service() -> str:
    return SERVICE.read_text(encoding="utf-8")


def _prompts() -> str:
    return PROMPTS.read_text(encoding="utf-8")


class TestWideRegexGateGone:
    def test_no_needs_verification_bootstrap_variable(self) -> None:
        text = _service()
        # No assignment of the variable — only comments may mention the
        # name as part of the deletion record.
        for ln in text.splitlines():
            if "needs_verification_bootstrap" in ln and not ln.lstrip().startswith("#"):
                pytest.fail(f"non-comment reference still exists: {ln!r}")

    def test_old_gate_condition_gone(self) -> None:
        text = _service()
        assert "and not needs_verification_bootstrap" not in text


class TestNarrowFastPathInPlace:
    def test_bare_email_or_consent_variable_defined(self) -> None:
        text = _service()
        assert "bare_email_or_consent = (" in text

    def test_fast_path_only_two_triggers(self) -> None:
        text = _service()
        i = text.find("bare_email_or_consent = (")
        end = text.find("    )", i)
        block = text[i: end + 5]
        # Must include consent + bare email...
        assert "_is_explicit_verification_consent(text)" in block
        assert "_extract_standalone_email(text)" in block
        # ...and NOT the wider order/account regex set that was deleted.
        assert "_looks_like_order_status_question(text)" not in block
        assert "_looks_like_account_question(text)" not in block
        assert "_looks_like_invoice_for_order(text)" not in block
        assert "_is_likely_order_id_only(text)" not in block

    def test_gate_condition_uses_narrow_fast_path(self) -> None:
        text = _service()
        # The if-condition that gates the LLM-first block must use the
        # new narrow variable, not the deleted wide one.
        assert (
            "if step not in otp_guard_steps "
            "and not bare_email_or_consent "
            "and not wants_trending_now:"
        ) in text

    def test_only_unverified_customers_triggered(self) -> None:
        """The fast-path must only fire for unverified customers — a
        verified customer typing their email accidentally shouldn't
        re-enter the verification flow."""
        text = _service()
        i = text.find("bare_email_or_consent = (")
        end = text.find("    )", i)
        block = text[i: end + 5]
        assert "not bool(flow.get(\"verified\"))" in block


class TestVerificationSignalStillWired:
    def test_verification_signal_handler_present(self) -> None:
        """When the LLM calls start_verification, the control plane
        returns a verification_signal. The process_message handler must
        advance step → existing_awaiting_email."""
        text = _service()
        assert (
            'if (\n                    _lf.verification_signal\n'
            in text
        ) or (
            "_lf.verification_signal\n" in text and
            'verification_signal.get("step") == "start"' in text
        )
        # Step transition must still happen.
        assert '_f_after["step"] = "existing_awaiting_email"' in text
        assert '_f_after["customer_kind"] = "existing"' in text


class TestPromptTeachesIntentDetection:
    """Without the regex safety net, the prompt must explicitly teach
    the LLM which phrasings require `start_verification`."""

    def test_prompt_warns_no_safety_net(self) -> None:
        p = _prompts()
        assert "no longer a deterministic regex safety net" in p, (
            "the prompt must tell the LLM the safety net is gone so it "
            "treats the call to start_verification as obligatory"
        )

    def test_prompt_lists_concrete_trigger_phrasings(self) -> None:
        p = _prompts()
        # English / Roman Urdu / Arabic example phrasings the prompt
        # now enumerates.
        for phrase in [
            "where is my order",
            "order ki status",
            "kahan hai mera parcel",
            "invoice btao",
            "saari orders dikhao",
            "verify me",
            "haan verify kardo",
        ]:
            assert phrase in p, (
                f"prompt must list {phrase!r} as an explicit trigger so "
                "the LLM doesn't miss this intent"
            )

    def test_prompt_warns_about_bare_order_id(self) -> None:
        p = _prompts()
        assert "bare 5–7 digit order id" in p or "bare 5-7 digit order id" in p

    def test_prompt_keeps_tool_only_rule(self) -> None:
        p = _prompts()
        # The original VERIFICATION GATE rule must still be there.
        assert "VERIFICATION GATE" in p
        assert "TOOL ONLY" in p
        assert "MUST call the `start_verification` tool" in p


class TestUnderlyingDetectorsKept:
    """The regex helpers themselves stay — they still serve other
    consumers (the trending escape, the verified-customer fast-path).
    Only the bootstrap-specific *use* of them was deleted."""

    @pytest.mark.parametrize(
        "name",
        [
            "_looks_like_order_status_question",
            "_looks_like_account_question",
            "_looks_like_invoice_for_order",
            "_is_explicit_verification_consent",
            "_extract_standalone_email",
        ],
    )
    def test_helper_still_importable(self, name: str) -> None:
        from services.customer_bot_flow import service as svc

        assert hasattr(svc, name), (
            f"{name} was kept intentionally — used by the trending escape "
            "and verified-customer fast-paths. Don't delete it."
        )

    def test_trending_escape_still_uses_them(self) -> None:
        text = _service()
        i = text.find("def _maybe_escape_trending_for_order_intent(")
        end = text.find("\n    def ", i + 50)
        block = text[i:end] if end > i else text[i: i + 2000]
        assert "_looks_like_order_status_question(msg_text)" in block
        assert "_looks_like_account_question(msg_text)" in block
