"""
Tests for two regressions caught in live WhatsApp transcript on 2026-04-29:

  1. After verification, a duplicate mobile-number send was processed as a new
     conversational turn and the LLM called `lookup_order(order_id="03474685920")`.
     The prompt now tells the LLM that 10+ digit phone-shaped strings are NOT
     order IDs.

  2. "Mujhay service 9 k baray mein btao" hit the unavailable-LLM fallback
     because the orchestrator gave up on the first transient OpenAI exception.
     The orchestrator now retries once with backoff (mirroring legacy bot.py).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock

import pytest


@dataclass
class _FakeAIMessage:
    content: str = ""
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    response_metadata: Dict[str, Any] = field(default_factory=dict)


class _FakeBoundLLM:
    def __init__(self, responses: List[Any]) -> None:
        # `responses` may contain Exception instances (will be raised) or
        # _FakeAIMessage instances (will be returned).
        self._responses = list(responses)
        self.ainvoke = AsyncMock(side_effect=self._next)

    async def _next(self, *_args, **_kwargs):
        if not self._responses:
            return _FakeAIMessage(content="(empty)")
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class _FakeChatOpenAI:
    def __init__(self, *_a, **_k) -> None:
        self.script: List[Any] = []

    def bind_tools(self, _tools):
        return _FakeBoundLLM(self.script)


@pytest.fixture
def patched_llm(monkeypatch):
    import langchain_openai
    from langchain_bot import orchestrator as _orch

    monkeypatch.setattr(langchain_openai, "ChatOpenAI", _FakeChatOpenAI)
    monkeypatch.setattr(_orch, "get_openai_api_key", lambda: "test-key")
    yield _FakeChatOpenAI


def _stage(monkeypatch, script: List[Any]) -> None:
    original_init = _FakeChatOpenAI.__init__

    def patched_init(self, *a, **k):
        original_init(self, *a, **k)
        self.script = list(script)

    monkeypatch.setattr(_FakeChatOpenAI, "__init__", patched_init)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Retry on transient failure
# ─────────────────────────────────────────────────────────────────────────────
class TestOrchestratorRetry:
    @pytest.mark.asyncio
    async def test_first_call_fails_second_succeeds(self, monkeypatch, patched_llm):
        """A single transient OpenAI failure should NOT surface the
        'mukhtasar technical masla' fallback to the customer — the
        orchestrator must retry once."""
        from langchain_bot import orchestrator
        from langchain_bot.tools import tools_for_verification_state

        _stage(
            monkeypatch,
            [
                # First attempt: simulated transient failure (e.g. OpenAI 429)
                TimeoutError("upstream timed out"),
                # Second attempt: succeeds with a normal text reply
                _FakeAIMessage(
                    content="Local & China sourcing service: Arabia ka 9th service hai...",
                    response_metadata={"token_usage": {"prompt_tokens": 100, "completion_tokens": 30}},
                ),
            ],
        )

        result = await orchestrator.run_turn(
            db=MagicMock(),
            tenant_id=1,
            customer_phone="9230",
            conversation_id=1,
            user_message="Mujhay service 9 k baray mein btao",
            language="roman_urdu",
            bot_flow={"verified": False, "step": "conversational"},
            store_client=MagicMock(),
            allowed_tools=tools_for_verification_state(verified=False, in_verification_flow=False),
        )

        assert result.used_fallback is False, (
            "Single transient failure must be retried, not surfaced as fallback. "
            f"Got reply: {result.reply_text!r}"
        )
        assert "sourcing" in result.reply_text.lower() or "service" in result.reply_text.lower()

    @pytest.mark.asyncio
    async def test_two_failures_in_a_row_do_surface_fallback(self, monkeypatch, patched_llm):
        """If the LLM fails on BOTH retries, the fallback should still fire —
        we don't want to retry forever on a real outage."""
        from langchain_bot import orchestrator
        from langchain_bot.tools import tools_for_verification_state

        _stage(
            monkeypatch,
            [
                ConnectionError("first failure"),
                ConnectionError("second failure"),
            ],
        )

        result = await orchestrator.run_turn(
            db=MagicMock(),
            tenant_id=1,
            customer_phone="9230",
            conversation_id=1,
            user_message="kuch bhi",
            language="roman_urdu",
            bot_flow={"verified": False, "step": "conversational"},
            store_client=MagicMock(),
            allowed_tools=tools_for_verification_state(verified=False, in_verification_flow=False),
        )

        assert result.used_fallback is True
        assert result.error is not None
        # Customer-visible text is the standard fallback, not a stack trace
        assert "agent" in result.reply_text.lower()


# ─────────────────────────────────────────────────────────────────────────────
# 2. Phone-number-as-order-ID guardrail (prompt rule)
# ─────────────────────────────────────────────────────────────────────────────
class TestPhoneAsOrderIdGuard:
    """The prompt now instructs the LLM that phone-shaped strings are not
    order IDs. We can't fully verify the LLM's behaviour without a real model,
    but we CAN verify the rule is present in the system prompt."""

    def test_order_id_format_rule_in_prompt(self) -> None:
        from langchain_bot.prompts import build_system_prompt_template

        sp = build_system_prompt_template()
        # The new guardrail line must be present.
        assert "Order ID format" in sp
        assert "5–7 digit" in sp or "5-7 digit" in sp
        # Must explicitly call out phone-shaped strings as NOT order IDs.
        assert "phone-shaped" in sp.lower() or "phone shaped" in sp.lower()
        # Must mention DO NOT call lookup_order with such input.
        assert "lookup_order" in sp

    def test_example_phone_numbers_are_called_out(self) -> None:
        from langchain_bot.prompts import build_system_prompt_template

        sp = build_system_prompt_template()
        # Concrete examples make the rule unambiguous for the LLM.
        # We accept any of: a Pakistan-format example, UAE example, or a generic 0-leading mention.
        assert any(
            marker in sp
            for marker in ("03474685920", "+971555516304", "leading `0`", "leading 0")
        )
