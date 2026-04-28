"""
Integration tests for the LLM-first orchestrator with a mocked ChatOpenAI.

The mock substitutes ``langchain_openai.ChatOpenAI`` so the orchestrator
runs end-to-end without making a real OpenAI request. We assert:

  * the right tool gets called with the right validated args
  * tool ``ToolResult`` payloads come back as a tool message and the LLM
    gets to produce a final answer
  * signals (verification, csv, trending, escalation) are harvested
    correctly into the ``OrchestratorResult``
  * argument-validation rejection (hallucinated args) produces an error
    payload the LLM can recover from

These tests don't talk to OpenAI, the store API, the database (the few
DB calls are routed through a tiny stub), or Redis.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# Test doubles
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class _FakeAIMessage:
    """Mimic langchain_core.messages.AIMessage just enough for the orchestrator."""

    content: str = ""
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    response_metadata: Dict[str, Any] = field(default_factory=dict)


class _FakeBoundLLM:
    """The object returned by ``ChatOpenAI.bind_tools(...)``.

    ``ainvoke`` returns successive responses from ``self._script`` so a test
    can simulate a tool-use chain (first call: tool_calls; second call: final text).
    """

    def __init__(self, script: List[_FakeAIMessage]) -> None:
        self._script = list(script)
        self.ainvoke = AsyncMock(side_effect=self._next)

    async def _next(self, *_args, **_kwargs) -> _FakeAIMessage:
        if not self._script:
            return _FakeAIMessage(content="(empty)")
        return self._script.pop(0)


class _FakeChatOpenAI:
    """Mock for ``langchain_openai.ChatOpenAI``."""

    last_instance: Optional["_FakeChatOpenAI"] = None

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.script: List[_FakeAIMessage] = []
        _FakeChatOpenAI.last_instance = self

    def bind_tools(self, _tools: Any) -> _FakeBoundLLM:
        return _FakeBoundLLM(self.script)


def _stub_store_client() -> MagicMock:
    """Async-method-aware stub for StoreIntegrationClient.

    Every method we touch in the handlers is configured to return reasonable
    structured data. The tests assert *call args* into this stub; we don't
    care about the structure beyond what handlers serialize back to the LLM.
    """
    sc = MagicMock()
    sc.get_order_by_id = AsyncMock(return_value={"id": "137044", "status": "Delivered", "profit": 36})
    sc.get_order_by_number = AsyncMock(return_value=None)
    sc.get_order_tracking = AsyncMock(return_value={"tracking_id": "TRK-1", "status": "Delivered"})
    sc.get_order_invoice_mapping = AsyncMock(return_value={"invoice": {"id": "INV-1", "payable": 100}})
    sc.get_orders_all = AsyncMock(return_value=[{"id": str(i), "status": "Delivered"} for i in range(7)])
    sc.get_invoice_by_seller_id = AsyncMock(
        return_value=[
            {"id": "INV-1", "pay_status": "Yes", "payable": 100, "order_ids": ["a", "b"]},
            {"id": "INV-2", "pay_status": "No", "payable": 50, "order_ids": ["c"]},
        ]
    )
    return sc


@pytest.fixture
def patched_chat_openai(monkeypatch):
    """Replace ChatOpenAI with the fake AND stub the API-key getter the
    orchestrator gates on. Returns the fake class so tests can stage the
    script before run_turn() executes."""
    import langchain_openai
    from langchain_bot import orchestrator as _orch

    monkeypatch.setattr(langchain_openai, "ChatOpenAI", _FakeChatOpenAI)
    monkeypatch.setattr(_orch, "get_openai_api_key", lambda: "test-key-not-real")
    yield _FakeChatOpenAI


@pytest.fixture
def fake_db():
    return MagicMock()


@pytest.fixture
def fake_store():
    return _stub_store_client()


# ─────────────────────────────────────────────────────────────────────────────
# Helpers — build canned LLM responses
# ─────────────────────────────────────────────────────────────────────────────
def _msg_with_tool(name: str, args: Dict[str, Any], call_id: str = "tool_1") -> _FakeAIMessage:
    return _FakeAIMessage(
        content="",
        tool_calls=[{"name": name, "args": args, "id": call_id}],
        response_metadata={"token_usage": {"prompt_tokens": 100, "completion_tokens": 20}},
    )


def _msg_text(text: str) -> _FakeAIMessage:
    return _FakeAIMessage(
        content=text,
        tool_calls=[],
        response_metadata={"token_usage": {"prompt_tokens": 50, "completion_tokens": 30}},
    )


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────
class TestSpecificOrderLookup:
    """Verified customer asks for a specific order id (TCA)."""

    @pytest.mark.asyncio
    async def test_calls_lookup_order_with_validated_args(
        self, monkeypatch, patched_chat_openai, fake_db, fake_store
    ):
        from langchain_bot import orchestrator
        from langchain_bot.tools import tools_for_verification_state

        bot_flow = {"verified": True, "seller_id": 12630, "step": "conversational", "lang": "english"}

        # Stage: LLM picks lookup_order on turn 1, synthesizes final text on turn 2.
        _FakeChatOpenAI.last_instance = None
        # The fake is constructed inside run_turn; we can't pre-stage the script
        # on it, so we monkey-patch the constructor to install our script.
        original_init = _FakeChatOpenAI.__init__

        def init_with_script(self, *a, **kw):
            original_init(self, *a, **kw)
            self.script = [
                _msg_with_tool("lookup_order", {"order_id": "137044"}),
                _msg_text("Order #137044 was delivered. Profit 36 AED."),
            ]

        monkeypatch.setattr(_FakeChatOpenAI, "__init__", init_with_script)

        result = await orchestrator.run_turn(
            db=fake_db,
            tenant_id=1,
            customer_phone="923001234567",
            conversation_id=1,
            user_message="Mujhay order 137044 ki details btao",
            language="roman_urdu",
            bot_flow=bot_flow,
            store_client=fake_store,
            allowed_tools=tools_for_verification_state(verified=True, in_verification_flow=False),
        )

        assert "delivered" in result.reply_text.lower()
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0]["name"] == "lookup_order"
        assert result.tool_calls[0]["args"] == {"order_id": "137044"}
        # Handler called the store client with the order id (hash stripped).
        fake_store.get_order_by_id.assert_called_once()
        called_args = fake_store.get_order_by_id.call_args
        assert called_args.args[0] == "137044" or called_args.kwargs.get("order_id") == "137044" or "137044" in str(called_args)


class TestDateRangeOrders:
    """Verified customer asks for orders in a range (TCD)."""

    @pytest.mark.asyncio
    async def test_calls_lookup_orders_by_range(
        self, monkeypatch, patched_chat_openai, fake_db, fake_store
    ):
        from langchain_bot import orchestrator
        from langchain_bot.tools import tools_for_verification_state

        bot_flow = {"verified": True, "seller_id": 12630, "step": "conversational"}

        original_init = _FakeChatOpenAI.__init__

        def init_with_script(self, *a, **kw):
            original_init(self, *a, **kw)
            self.script = [
                _msg_with_tool(
                    "lookup_orders_by_range",
                    {
                        "date_from": "2026-03-01",
                        "date_to": "2026-04-30",
                        "label": "last 2 months",
                    },
                ),
                _msg_text("Found 7 orders between March and April 2026."),
            ]

        monkeypatch.setattr(_FakeChatOpenAI, "__init__", init_with_script)

        result = await orchestrator.run_turn(
            db=fake_db,
            tenant_id=1,
            customer_phone="923001234567",
            conversation_id=1,
            user_message="Mujhay last 2 months k orders dikhao",
            language="roman_urdu",
            bot_flow=bot_flow,
            store_client=fake_store,
            allowed_tools=tools_for_verification_state(verified=True, in_verification_flow=False),
        )

        assert "7" in result.reply_text or "march" in result.reply_text.lower()
        assert any(tc["name"] == "lookup_orders_by_range" for tc in result.tool_calls)
        fake_store.get_orders_all.assert_called_once()


class TestVerificationStartSignal:
    """Unverified customer asks for orders → LLM must call start_verification (TC3)."""

    @pytest.mark.asyncio
    async def test_start_verification_signal_extracted(
        self, monkeypatch, patched_chat_openai, fake_db, fake_store
    ):
        from langchain_bot import orchestrator
        from langchain_bot.tools import tools_for_verification_state

        bot_flow = {"verified": False, "step": "conversational"}

        original_init = _FakeChatOpenAI.__init__

        def init_with_script(self, *a, **kw):
            original_init(self, *a, **kw)
            self.script = [
                _msg_with_tool("start_verification", {"reason": "order_lookup"}),
                _msg_text("Pehle main aap ki verification karta hoon. Aap **new** ya **existing** customer hain? (1/2)"),
            ]

        monkeypatch.setattr(_FakeChatOpenAI, "__init__", init_with_script)

        result = await orchestrator.run_turn(
            db=fake_db,
            tenant_id=1,
            customer_phone="923001234567",
            conversation_id=1,
            user_message="Mujhay order details btao",
            language="roman_urdu",
            bot_flow=bot_flow,
            store_client=fake_store,
            allowed_tools=tools_for_verification_state(verified=False, in_verification_flow=False),
        )

        assert result.verification_signal is not None
        assert result.verification_signal["step"] == "start"
        assert "new" in result.reply_text.lower() or "existing" in result.reply_text.lower()


class TestEscalationSignal:
    """Customer asks for agent → LLM calls escalate_to_agent (TC11/12)."""

    @pytest.mark.asyncio
    async def test_escalation_signal_set(
        self, monkeypatch, patched_chat_openai, fake_db, fake_store
    ):
        from langchain_bot import orchestrator
        from langchain_bot.tools import tools_for_verification_state

        bot_flow = {"verified": False, "step": "conversational"}

        original_init = _FakeChatOpenAI.__init__

        def init_with_script(self, *a, **kw):
            original_init(self, *a, **kw)
            self.script = [
                _msg_with_tool("escalate_to_agent", {"reason": "customer_requested"}),
                _msg_text("Connecting you to a human agent."),
            ]

        monkeypatch.setattr(_FakeChatOpenAI, "__init__", init_with_script)

        result = await orchestrator.run_turn(
            db=fake_db,
            tenant_id=1,
            customer_phone="923001234567",
            conversation_id=1,
            user_message="connect me to agent",
            language="english",
            bot_flow=bot_flow,
            store_client=fake_store,
            allowed_tools=tools_for_verification_state(verified=False, in_verification_flow=False),
        )

        assert result.escalation_signal is True


class TestCsvSignal:
    """Verified customer asks for CSV → LLM calls generate_csv (TCG/TCL)."""

    @pytest.mark.asyncio
    async def test_csv_signal_passes_through(
        self, monkeypatch, patched_chat_openai, fake_db, fake_store
    ):
        from langchain_bot import orchestrator
        from langchain_bot.tools import tools_for_verification_state

        bot_flow = {"verified": True, "seller_id": 12630, "step": "conversational"}

        original_init = _FakeChatOpenAI.__init__

        def init_with_script(self, *a, **kw):
            original_init(self, *a, **kw)
            self.script = [
                _msg_with_tool(
                    "generate_csv",
                    {"kind": "orders", "date_from": "2026-01-01", "date_to": "2026-04-29"},
                ),
                _msg_text("CSV preparing."),
            ]

        monkeypatch.setattr(_FakeChatOpenAI, "__init__", init_with_script)

        result = await orchestrator.run_turn(
            db=fake_db,
            tenant_id=1,
            customer_phone="923001234567",
            conversation_id=1,
            user_message="Saare orders ki CSV bhejo",
            language="roman_urdu",
            bot_flow=bot_flow,
            store_client=fake_store,
            allowed_tools=tools_for_verification_state(verified=True, in_verification_flow=False),
        )

        assert result.csv_signal is not None
        assert result.csv_signal["kind"] == "orders"
        assert result.csv_signal["date_from"] == "2026-01-01"


class TestHallucinatedArgsRejected:
    """If the LLM produces invalid tool args, the handler returns ok=False with
    an ``invalid_args`` error — the orchestrator does not crash and the LLM
    gets a chance to retry."""

    @pytest.mark.asyncio
    async def test_invalid_args_produce_error_payload_not_crash(
        self, monkeypatch, patched_chat_openai, fake_db, fake_store
    ):
        from langchain_bot import orchestrator
        from langchain_bot.tools import tools_for_verification_state

        bot_flow = {"verified": True, "seller_id": 12630, "step": "conversational"}

        original_init = _FakeChatOpenAI.__init__

        def init_with_script(self, *a, **kw):
            original_init(self, *a, **kw)
            self.script = [
                _msg_with_tool(
                    "lookup_orders_by_range",
                    {"date_from": "yesterday", "date_to": "today"},  # invalid: not ISO
                ),
                _msg_text("Sorry, I had trouble with that range."),
            ]

        monkeypatch.setattr(_FakeChatOpenAI, "__init__", init_with_script)

        result = await orchestrator.run_turn(
            db=fake_db,
            tenant_id=1,
            customer_phone="923001234567",
            conversation_id=1,
            user_message="orders chahiye",
            language="english",
            bot_flow=bot_flow,
            store_client=fake_store,
            allowed_tools=tools_for_verification_state(verified=True, in_verification_flow=False),
        )

        # First tool result should be ok=False with invalid_args error — recorded
        # in tool_results, but the orchestrator continued and used the LLM's text.
        assert result.tool_results
        first = result.tool_results[0]["payload"]
        assert first["ok"] is False
        assert "invalid_args" in first["error"]
        # No store call should have happened.
        fake_store.get_orders_all.assert_not_called()
        assert "trouble" in result.reply_text.lower()


class TestNoToolCallShortPath:
    """KB-style question: LLM may answer without calling any tool. The orchestrator
    just returns the text — no tool dispatch, no signals."""

    @pytest.mark.asyncio
    async def test_no_tool_calls_returns_text_immediately(
        self, monkeypatch, patched_chat_openai, fake_db, fake_store
    ):
        from langchain_bot import orchestrator
        from langchain_bot.tools import tools_for_verification_state

        bot_flow = {"verified": False, "step": "conversational"}

        original_init = _FakeChatOpenAI.__init__

        def init_with_script(self, *a, **kw):
            original_init(self, *a, **kw)
            self.script = [
                _msg_text("Yes, Arabia Dropship has 98.4% on-time dispatch and 12K+ sellers."),
            ]

        monkeypatch.setattr(_FakeChatOpenAI, "__init__", init_with_script)

        result = await orchestrator.run_turn(
            db=fake_db,
            tenant_id=1,
            customer_phone="923001234567",
            conversation_id=1,
            user_message="kya arabia reliable hai",
            language="roman_urdu",
            bot_flow=bot_flow,
            store_client=fake_store,
            allowed_tools=tools_for_verification_state(verified=False, in_verification_flow=False),
        )

        assert "98.4%" in result.reply_text
        assert result.tool_calls == []
        assert result.escalation_signal is False
        assert result.verification_signal is None
        assert result.csv_signal is None
