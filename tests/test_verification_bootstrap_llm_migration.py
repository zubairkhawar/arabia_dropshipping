"""
Regression tests for the verification bootstrap.

History:
  - 2026-04-30 (commit 75fb86a): the deterministic verification
    bootstrap was deleted in favour of letting the LLM call
    `start_verification` itself, guarded by a strict prompt rule.
  - 2026-05-01: REVERTED. WhatsApp transcript 2026-05-01 03:03
    showed the LLM still drifting in production:
      Customer: "Mujhy orders k baray mein jnaa hai"
      Bot: clarifying question (didn't call start_verification)
      Customer: "Han kro verification"
      Bot: "Theek hai, pehle main aap ki verification kar leta hoon"
            (step never advanced)
      Customer: "Kro bhi"
      Bot: HALLUCINATED "verification process start ho gaya tha lekin
            account nahi mila" — no email asked, no OTP, no mobile,
            no store-API call. Pure fabrication.
    The strict VERIFICATION GATE prompt rule isn't enough on its own.
    The bootstrap regex is now back as a safety net so the
    deterministic state machine ALWAYS owns the transition into the
    verification bucket on order / invoice / account intent.

These tests verify the restored bootstrap is wired correctly.
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


class TestBootstrapRestored:
    def test_needs_verification_bootstrap_defined(self) -> None:
        text = _service()
        assert "needs_verification_bootstrap = (" in text, (
            "the verification bootstrap regex was supposed to be restored "
            "after the 2026-05-01 transcript bug — see the deletion-revert "
            "commit"
        )

    def test_gate_uses_bootstrap(self) -> None:
        text = _service()
        # The if-condition that gates the LLM-first block must use the
        # bootstrap variable.
        assert (
            "if step not in otp_guard_steps "
            "and not needs_verification_bootstrap "
            "and not wants_trending_now:"
        ) in text

    def test_bootstrap_includes_full_intent_detector_set(self) -> None:
        text = _service()
        i = text.find("needs_verification_bootstrap = (")
        end = text.find("    )", i)
        block = text[i: end + 5]
        # Must include the full set of order/account intent detectors,
        # not just bare email + consent.
        for fn in (
            "_looks_like_order_status_question(text)",
            "_is_likely_order_id_only(text)",
            "_looks_like_account_question(text)",
            "_looks_like_invoice_for_order(text)",
            "_is_explicit_verification_consent(text)",
            "_extract_standalone_email(text)",
        ):
            assert fn in block, f"bootstrap must call {fn}"

    def test_only_unverified_customers_triggered(self) -> None:
        text = _service()
        i = text.find("needs_verification_bootstrap = (")
        end = text.find("    )", i)
        block = text[i: end + 5]
        assert "not bool(flow.get(\"verified\"))" in block

    def test_only_at_conversational_step(self) -> None:
        """Bootstrap must only fire from the conversational step,
        not from inside a verification step (where the deterministic
        flow is already running) or trending."""
        text = _service()
        i = text.find("needs_verification_bootstrap = (")
        end = text.find("    )", i)
        block = text[i: end + 5]
        assert 'step == "conversational"' in block


class TestVerificationSignalStillWired:
    """When the LLM calls start_verification (e.g. for "verify me" with
    no other context where the regex didn't catch it), the
    verification_signal handler must still advance the step."""

    def test_verification_signal_handler_present(self) -> None:
        text = _service()
        assert 'verification_signal.get("step") == "start"' in text
        assert '_f_after["step"] = "existing_awaiting_email"' in text
        assert '_f_after["customer_kind"] = "existing"' in text


class TestPromptStillForbidsFabrication:
    """Even with the regex safety net back, the prompt must explicitly
    forbid the LLM from drafting verification dialogue or fabricating
    results — that's the failure mode that caused the 2026-05-01 bug."""

    def test_prompt_keeps_tool_only_rule(self) -> None:
        p = _prompts()
        assert "VERIFICATION GATE" in p
        assert "TOOL ONLY" in p
        assert "MUST call the `start_verification` tool" in p

    def test_prompt_forbids_fabrication(self) -> None:
        p = _prompts()
        # The new rule added on 2026-05-01 explicitly bans the
        # hallucinated "verification kar liya hai" pattern that broke
        # production.
        assert "Never fabricate verification results" in p
        # Examples of the bad outputs the prompt now flags.
        for bad in [
            "verification kar liya hai",
            "verification process start ho gaya tha lekin",
            "I've verified you",
        ]:
            assert bad in p, f"prompt must list {bad!r} as a forbidden phrase"


class TestUnderlyingDetectorsKept:
    @pytest.mark.parametrize(
        "name",
        [
            "_looks_like_order_status_question",
            "_looks_like_account_question",
            "_looks_like_invoice_for_order",
            "_is_explicit_verification_consent",
            "_extract_standalone_email",
            "_is_likely_order_id_only",
        ],
    )
    def test_helper_still_importable(self, name: str) -> None:
        from services.customer_bot_flow import service as svc

        assert hasattr(svc, name)

    def test_trending_escape_still_uses_them(self) -> None:
        text = _service()
        i = text.find("def _maybe_escape_trending_for_order_intent(")
        end = text.find("\n    def ", i + 50)
        block = text[i:end] if end > i else text[i: i + 2000]
        assert "_looks_like_order_status_question(msg_text)" in block
        assert "_looks_like_account_question(msg_text)" in block


class TestTranscript_2026_05_01_RegressionPinned:
    """Pin the exact failure modes from the 2026-05-01 03:03 WhatsApp
    transcript. With the bootstrap restored, the deterministic flow
    intercepts these messages BEFORE the LLM has a chance to drift."""

    @pytest.mark.parametrize(
        "msg",
        [
            # Turn 1 of the transcript — the message that SHOULD have
            # triggered the bootstrap immediately. With the regex
            # restored, this customer never reaches the hallucination
            # bug at all because the deterministic flow takes over here.
            "Mujhy orders k baray mein jnaa hai",
            # Turn 2 — explicit consent. Even if Turn 1 had somehow
            # missed the bootstrap, this catches it.
            "Han kro verification",
            # Adjacent variants from the broader transcript history:
            "verify me please",
            "haan verify kar do",
            "I want to check my orders",
        ],
    )
    def test_transcript_messages_classified_as_bootstrap_triggers(
        self, msg: str
    ) -> None:
        from services.customer_bot_flow import service as svc

        # Mimic the bootstrap expression for an unverified-conversational
        # customer.
        triggers = (
            svc._looks_like_order_status_question(msg)
            or svc._is_likely_order_id_only(msg)
            or svc._looks_like_account_question(msg)
            or svc._looks_like_invoice_for_order(msg)
            or svc._is_explicit_verification_consent(msg)
            or bool(svc._extract_standalone_email(msg))
        )
        assert triggers, (
            f"{msg!r} from the 2026-05-01 transcript must hit the "
            "bootstrap regex so the deterministic state machine owns the "
            "step transition. If this fails, the LLM is back in charge "
            "of verification entry and can hallucinate again."
        )
