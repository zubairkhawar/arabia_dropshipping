"""
Regression tests for WhatsApp transcript 2026-04-29 15:54:

Verified customer typed an order id ('187916'), got a brief reply with
the order's tracking + status. Then asked 'Tell me order details' on
the next turn — bot replied with 'Currently, there is a technical
issue fetching your order details from the store system' (the
store_context_error prompt rule).

Root cause: the LLM-first orchestrator was being called with no
conversation history. The LLM had no way to resolve 'Tell me order
details' to '187916'. It either called a tool with hallucinated args
(rejected by the phone-shape guard) or drafted the prompt-rule message
preemptively.

Fix: control_plane.run_one_turn now (a) loads recent conversation
history from the Message table and passes it as the
`conversation_history` block, and (b) injects a brief verified-customer
identity block telling the LLM how to resolve back-references.
"""
from __future__ import annotations

from pathlib import Path


def _control_plane_text() -> str:
    src = Path(__file__).resolve().parent.parent / "server" / "langchain_bot" / "control_plane.py"
    return src.read_text(encoding="utf-8")


class TestConversationHistoryWiring:
    def test_helper_exists(self) -> None:
        text = _control_plane_text()
        assert "_load_recent_conversation_history" in text
        assert "from models import Message" in text or "import Message" in text, (
            "must query the Message table to pull recent turns"
        )
        # The label is computed from sender_type — check the if/else expression.
        assert '"Customer"' in text and '"Bot"' in text, (
            "must label customer/bot turns so the LLM can read the history"
        )

    def test_run_one_turn_passes_history(self) -> None:
        text = _control_plane_text()
        # The blocks dict must be built and conversation_history populated
        # before being passed to run_turn.
        i = text.find("blocks: Dict[str, str] = dict(extra_context_blocks or {})")
        assert i > 0, (
            "control_plane must build a blocks dict so it can inject "
            "conversation_history without clobbering caller-provided blocks"
        )
        # And the orchestrator must receive it.
        assert "extra_context_blocks=blocks" in text, (
            "the populated blocks dict must reach the orchestrator"
        )

    def test_verified_customer_identity_hint(self) -> None:
        text = _control_plane_text()
        # The hint should explain to the LLM how to resolve back-references.
        assert "lookup_order with that id" in text, (
            "prompt LLM to use lookup_order when the customer references an "
            "order id from earlier in the conversation"
        )
        assert 'Customer verification status: VERIFIED' in text, (
            "verified-customer identity block must be present"
        )


class TestNoRegressionToOldDefaults:
    def test_no_hardcoded_none_for_history(self) -> None:
        """The orchestrator's defaults still have 'None' for conversation_history
        as a fallback, but the control plane must override it. Make sure
        the override is actually written (not just a no-op)."""
        text = _control_plane_text()
        # The control plane must not pass extra_context_blocks=None when
        # routing to LLM-first. It must pass `blocks` after populating it.
        i = text.find("orch_result: OrchestratorResult = await run_turn(")
        assert i > 0
        block = text[i: i + 800]
        assert "extra_context_blocks=None" not in block, (
            "the orchestrator call must pass the populated blocks, not None"
        )
        assert "extra_context_blocks=blocks" in block
