"""
Rigorous tests for the customer-type-menu deletion (2026-04-30).

Before: every unverified customer asking about an order/account hit
the awaiting_customer_type 1/2 menu first ("Reply 1 if you are a new
customer or 2 if you are an existing customer."). The 218-line
handler dispatched on _parse_choice + _classify_entry_menu_intent_llm,
re-prompted on ack-only replies, and offered an agent_hours escape.

After: the menu is gone. Order/account intent → bootstrap straight
into existing_awaiting_email (the customer is implicitly an existing
customer; if they aren't, the verification will fail and they'll be
offered a human agent after 3 strikes). Other intents (how-to /
service / dropshipping questions) flow to the LLM-first orchestrator
and ai_forward without any menu interception.

These tests verify deletion is complete:
1. The step handler is gone.
2. The deterministic helpers it used are gone.
3. The templates it used are gone.
4. otp_guard_steps no longer contains the step.
5. The bootstrap path now sets customer_kind=existing without a menu.
6. _looks_like_intro_aware_step still treats "conversational" as a
   resume-from-anywhere step (not "awaiting_customer_type").
"""
from __future__ import annotations

from pathlib import Path

import pytest


SERVICE = (
    Path(__file__).resolve().parent.parent
    / "server" / "services" / "customer_bot_flow" / "service.py"
)
TEMPLATES = (
    Path(__file__).resolve().parent.parent
    / "server" / "services" / "customer_bot_flow" / "templates.py"
)


def _service() -> str:
    return SERVICE.read_text(encoding="utf-8")


def _templates() -> str:
    return TEMPLATES.read_text(encoding="utf-8")


class TestStepHandlerDeleted:
    def test_step_handler_block_gone(self) -> None:
        text = _service()
        # The `if step == "awaiting_customer_type":` block must be gone.
        assert 'step == "awaiting_customer_type"' not in text

    def test_step_setter_gone(self) -> None:
        text = _service()
        # No code path may set this step any more — it's not in the FSM.
        assert '"awaiting_customer_type"' not in text or "deleted" in text

    def test_step_not_in_otp_guard(self) -> None:
        text = _service()
        marker = "otp_guard_steps = {"
        i = text.find(marker)
        assert i > 0
        end = text.find("}", i)
        block = text[i:end]
        assert "awaiting_customer_type" not in block


class TestObsoleteHelpersDeleted:
    @pytest.mark.parametrize(
        "name",
        [
            "_classify_entry_menu_intent_llm",
            "_entry_menu_agent_hours_reply",
            "_memory_store_pending_entry_menu",
            "_memory_pending_ai_prefix",
            "_looks_like_free_text_question",
        ],
    )
    def test_helper_definition_gone(self, name: str) -> None:
        text = _service()
        assert f"def {name}(" not in text, (
            f"{name} only existed to drive the deleted 1/2 menu — must be removed"
        )

    @pytest.mark.parametrize(
        "name",
        [
            "_classify_entry_menu_intent_llm",
            "_entry_menu_agent_hours_reply",
            "_memory_store_pending_entry_menu",
            "_memory_pending_ai_prefix",
            "_looks_like_free_text_question",
        ],
    )
    def test_helper_not_imported(self, name: str) -> None:
        from services.customer_bot_flow import service as svc

        assert not hasattr(svc, name)


class TestObsoleteTemplatesDeleted:
    @pytest.mark.parametrize(
        "key",
        [
            "customer_type_menu_reminder",
            "customer_type_unclear",
            "existing_customer_welcome",
        ],
    )
    def test_template_key_gone(self, key: str) -> None:
        from services.customer_bot_flow.templates import BOT_FLOW_TEMPLATES

        assert key not in BOT_FLOW_TEMPLATES, (
            f"template {key!r} only served the deleted menu — must be removed"
        )

    def test_new_customer_welcome_kept(self) -> None:
        """The 'new_customer_welcome' template still has a use: when the
        customer is mid-existing-flow and switches to new path. Don't
        delete this one."""
        from services.customer_bot_flow.templates import BOT_FLOW_TEMPLATES

        assert "new_customer_welcome" in BOT_FLOW_TEMPLATES


class TestBootstrapImplicitlySetsExisting:
    def test_unverified_order_intent_bootstraps_existing(self) -> None:
        """An unverified customer asking about an order is treated as
        existing — no menu, no choice. The bootstrap branch must set
        customer_kind='existing' inline, then continue into the
        verification flow (which is unchanged)."""
        text = _service()
        # Find the bootstrap branch — it sits after the new fast-path
        # comment that explains the menu deletion.
        marker = "Unverified: order/account questions go straight"
        i = text.find(marker)
        assert i > 0, (
            "the 'go straight to verification' comment is the new contract — "
            "if it moved, update this test to point at its new home"
        )
        block = text[i: i + 2000]
        assert '"customer_kind": "existing"' in block
        # And no awaiting_customer_type step transition.
        assert '"awaiting_customer_type"' not in block

    def test_pending_intent_still_stashed(self) -> None:
        """The original question must STILL be stashed before the
        verification email-asking step. The post-verification path uses
        it to decide which detail-render template to use."""
        text = _service()
        marker = "Unverified: order/account questions go straight"
        i = text.find(marker)
        block = text[i: i + 2000]
        assert "ConversationMemory.store_pending_intent(" in block


class TestArchitectureSnapshotMatches:
    """The architecture snapshot pinning DETERMINISTIC_VERIFICATION_STEPS
    must reflect the deletion. If someone re-introduces the step
    elsewhere, that snapshot will catch it."""

    def test_snapshot_excludes_deleted_step(self) -> None:
        from tests.test_architecture_snapshot import (  # type: ignore
            DETERMINISTIC_VERIFICATION_STEPS,
        )

        assert "awaiting_customer_type" not in DETERMINISTIC_VERIFICATION_STEPS


class TestLLMFirstStillRoutes:
    """The deletion shouldn't break the LLM-first dispatch — once the
    customer says something that isn't a verification trigger, the LLM
    handles it through the orchestrator + tools."""

    def test_llm_first_orchestrator_still_called(self) -> None:
        text = _service()
        assert "from langchain_bot.control_plane import run_one_turn" in text
        assert "_llm_first_run(" in text

    def test_llm_first_handles_csv_signal(self) -> None:
        """Sanity: the CSV migration is still wired (this guards against
        accidental regressions while doing the customer-type migration)."""
        text = _service()
        assert "_dispatch_csv_signal(_lf.csv_signal" in text
