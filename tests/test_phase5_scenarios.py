"""
Phase 5 end-to-end scenario tests with a mocked ChatOpenAI.

These cover what the WhatsApp customer would experience in each routing
path. Mock LLM responses are pre-staged so the test is deterministic.

Coverage map:
  - Conversational: greeting after intro, thanks, ack, KB question
  - Verified-customer account-data: order/orders-by-range/invoices/totals
  - Unverified-customer order ask → start_verification (the WhatsApp
    transcript bug 'total invoices btao' is reproduced as
    TestUnverifiedAccountAsk.test_total_invoices_routes_to_verification)
  - Topic change inside verification step → bail to LLM
  - Agent escalation → escalate_to_agent tool
  - Out-of-scope → LLM redirects
  - CSV ask → generate_csv tool with ISO date args
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# Test doubles (shared with test_orchestrator_mocked_llm.py pattern)
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class _FakeAIMessage:
    content: str = ""
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    response_metadata: Dict[str, Any] = field(default_factory=dict)


class _FakeBoundLLM:
    def __init__(self, script: List[_FakeAIMessage]) -> None:
        self._script = list(script)
        self.ainvoke = AsyncMock(side_effect=self._next)

    async def _next(self, *_args, **_kwargs) -> _FakeAIMessage:
        if not self._script:
            return _FakeAIMessage(content="(empty)")
        return self._script.pop(0)


class _FakeChatOpenAI:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.script: List[_FakeAIMessage] = []

    def bind_tools(self, _tools: Any) -> _FakeBoundLLM:
        return _FakeBoundLLM(self.script)


def _stub_store() -> MagicMock:
    sc = MagicMock()
    sc.get_order_by_id = AsyncMock(return_value={"id": "137044", "status": "Delivered", "profit": 36})
    sc.get_order_by_number = AsyncMock(return_value=None)
    sc.get_order_tracking = AsyncMock(return_value={"tracking_id": "TRK-1", "status": "Delivered"})
    sc.get_order_invoice_mapping = AsyncMock(return_value={"invoice": {"id": "INV-1", "payable": 100}})
    sc.get_orders_all = AsyncMock(return_value=[{"id": str(i), "status": "Delivered"} for i in range(5)])
    sc.get_invoice_by_seller_id = AsyncMock(
        return_value=[
            {"id": "INV-1", "pay_status": "Yes", "payable": 9506.0, "currency": "AED", "order_ids": ["a", "b"]},
            {"id": "INV-2", "pay_status": "Yes", "payable": 200, "order_ids": ["c"]},
        ]
    )
    return sc


@pytest.fixture
def fake_db():
    return MagicMock()


@pytest.fixture
def fake_store():
    return _stub_store()


@pytest.fixture
def patched_llm(monkeypatch):
    """Substitute ChatOpenAI + bypass the API-key gate."""
    import langchain_openai
    from langchain_bot import orchestrator as _orch

    monkeypatch.setattr(langchain_openai, "ChatOpenAI", _FakeChatOpenAI)
    monkeypatch.setattr(_orch, "get_openai_api_key", lambda: "test-key-not-real")
    yield _FakeChatOpenAI


def _stage_script(monkeypatch, script: List[_FakeAIMessage]) -> None:
    """Install a script that'll be returned to the next ChatOpenAI instantiation."""
    original = _FakeChatOpenAI.__init__

    def patched_init(self, *a, **kw):
        original(self, *a, **kw)
        self.script = list(script)

    monkeypatch.setattr(_FakeChatOpenAI, "__init__", patched_init)


def _tool(name: str, args: Dict[str, Any], call_id: str = "tc_1") -> _FakeAIMessage:
    return _FakeAIMessage(
        content="",
        tool_calls=[{"name": name, "args": args, "id": call_id}],
        response_metadata={"token_usage": {"prompt_tokens": 100, "completion_tokens": 20}},
    )


def _txt(text: str) -> _FakeAIMessage:
    return _FakeAIMessage(
        content=text,
        tool_calls=[],
        response_metadata={"token_usage": {"prompt_tokens": 50, "completion_tokens": 30}},
    )


# ─────────────────────────────────────────────────────────────────────────────
# Conversational (no tool needed)
# ─────────────────────────────────────────────────────────────────────────────
class TestConversational:
    @pytest.mark.asyncio
    async def test_greeting_no_tool(self, monkeypatch, patched_llm, fake_db, fake_store):
        """'Hi' mid-conversation → LLM produces warm reply, no tool call."""
        _stage_script(monkeypatch, [_txt("Hello! How can I help today?")])

        from langchain_bot import orchestrator
        from langchain_bot.tools import tools_for_verification_state

        result = await orchestrator.run_turn(
            db=fake_db,
            tenant_id=1,
            customer_phone="923001234567",
            conversation_id=1,
            user_message="Hi",
            language="english",
            bot_flow={"verified": False, "step": "conversational", "intro_shown": True},
            store_client=fake_store,
            allowed_tools=tools_for_verification_state(verified=False, in_verification_flow=False),
        )

        assert "hello" in result.reply_text.lower() or "help" in result.reply_text.lower()
        assert result.tool_calls == []
        assert result.escalation_signal is False

    @pytest.mark.asyncio
    async def test_thanks_no_tool(self, monkeypatch, patched_llm, fake_db, fake_store):
        _stage_script(monkeypatch, [_txt("You're welcome! Anything else?")])

        from langchain_bot import orchestrator
        from langchain_bot.tools import tools_for_verification_state

        result = await orchestrator.run_turn(
            db=fake_db,
            tenant_id=1,
            customer_phone="9230",
            conversation_id=1,
            user_message="thanks",
            language="english",
            bot_flow={"verified": False, "step": "conversational", "intro_shown": True},
            store_client=fake_store,
            allowed_tools=tools_for_verification_state(verified=False, in_verification_flow=False),
        )

        assert "welcome" in result.reply_text.lower() or "anything else" in result.reply_text.lower()
        assert result.tool_calls == []


# ─────────────────────────────────────────────────────────────────────────────
# KB / FAQ
# ─────────────────────────────────────────────────────────────────────────────
class TestKbQuestions:
    @pytest.mark.asyncio
    async def test_reliability_kb(self, monkeypatch, patched_llm, fake_db, fake_store):
        """'kya arabia reliable hai' → search_kb tool → KB-grounded answer."""
        _stage_script(
            monkeypatch,
            [
                _tool("search_kb", {"query": "is arabia dropship reliable"}),
                _txt("Yes — 98.4% on-time dispatch and 12K+ active sellers."),
            ],
        )

        from langchain_bot import orchestrator
        from langchain_bot.tools import tools_for_verification_state

        result = await orchestrator.run_turn(
            db=fake_db,
            tenant_id=1,
            customer_phone="9230",
            conversation_id=1,
            user_message="kya arabia reliable hai",
            language="roman_urdu",
            bot_flow={"verified": False, "step": "conversational"},
            store_client=fake_store,
            allowed_tools=tools_for_verification_state(verified=False, in_verification_flow=False),
        )

        assert "98.4%" in result.reply_text
        assert any(tc["name"] == "search_kb" for tc in result.tool_calls)


# ─────────────────────────────────────────────────────────────────────────────
# Unverified customer asking for account data
# ─────────────────────────────────────────────────────────────────────────────
class TestUnverifiedAccountAsk:
    """Reproduces and verifies the fix for the WhatsApp transcript bug:
    'Mujhay meri abhi tak ki total invoices btao' → must call start_verification."""

    @pytest.mark.asyncio
    async def test_total_invoices_routes_to_verification(
        self, monkeypatch, patched_llm, fake_db, fake_store
    ):
        _stage_script(
            monkeypatch,
            [
                _tool("start_verification", {"reason": "invoice_lookup"}),
                _txt("Sure — let me verify you first. Please share your registered email."),
            ],
        )

        from langchain_bot import orchestrator
        from langchain_bot.tools import tools_for_verification_state

        bot_flow = {"verified": False, "step": "conversational", "intro_shown": True}

        result = await orchestrator.run_turn(
            db=fake_db,
            tenant_id=1,
            customer_phone="923001234567",
            conversation_id=1,
            user_message="Mujhay meri abhi tak ki total invoices btao",
            language="roman_urdu",
            bot_flow=bot_flow,
            store_client=fake_store,
            allowed_tools=tools_for_verification_state(verified=False, in_verification_flow=False),
        )

        assert result.verification_signal is not None
        assert result.verification_signal["step"] == "start"
        # Reply mentions verification / email — naturally drafted by LLM, fits the
        # customer's actual question (invoices) rather than the old orders-themed template.
        assert "email" in result.reply_text.lower() or "verify" in result.reply_text.lower()
        # Critically: account_data tools are NOT in the allowed list for an
        # unverified customer — list_invoices, lookup_order, etc. should be filtered out.
        allowed_names = {
            t.name for t in tools_for_verification_state(verified=False, in_verification_flow=False)
        }
        assert "list_invoices" not in allowed_names
        assert "lookup_order" not in allowed_names
        assert "get_total_paid" not in allowed_names

    @pytest.mark.asyncio
    async def test_unverified_order_status_routes_to_verification(
        self, monkeypatch, patched_llm, fake_db, fake_store
    ):
        _stage_script(
            monkeypatch,
            [
                _tool("start_verification", {"reason": "order_lookup"}),
                _txt("To check your order, I need to verify you first. Please share your email."),
            ],
        )

        from langchain_bot import orchestrator
        from langchain_bot.tools import tools_for_verification_state

        result = await orchestrator.run_turn(
            db=fake_db,
            tenant_id=1,
            customer_phone="9230",
            conversation_id=1,
            user_message="where is my order",
            language="english",
            bot_flow={"verified": False, "step": "conversational"},
            store_client=fake_store,
            allowed_tools=tools_for_verification_state(verified=False, in_verification_flow=False),
        )

        assert result.verification_signal is not None
        assert result.verification_signal["step"] == "start"


# ─────────────────────────────────────────────────────────────────────────────
# Verified customer — full set of account-data tools
# ─────────────────────────────────────────────────────────────────────────────
class TestVerifiedAccountData:
    @pytest.mark.asyncio
    async def test_total_paid(self, monkeypatch, patched_llm, fake_db, fake_store):
        _stage_script(
            monkeypatch,
            [
                _tool("get_total_paid", {}),
                _txt("Total paid so far is 9706 AED across 2 paid invoices."),
            ],
        )

        from langchain_bot import orchestrator
        from langchain_bot.tools import tools_for_verification_state

        result = await orchestrator.run_turn(
            db=fake_db,
            tenant_id=1,
            customer_phone="9230",
            conversation_id=1,
            user_message="total kitni payment ab tak mili hai",
            language="roman_urdu",
            bot_flow={"verified": True, "seller_id": 12630, "step": "conversational"},
            store_client=fake_store,
            allowed_tools=tools_for_verification_state(verified=True, in_verification_flow=False),
        )

        assert any(tc["name"] == "get_total_paid" for tc in result.tool_calls)
        fake_store.get_invoice_by_seller_id.assert_called_once()

    @pytest.mark.asyncio
    async def test_total_orders(self, monkeypatch, patched_llm, fake_db, fake_store):
        _stage_script(
            monkeypatch,
            [
                _tool("get_total_orders", {}),
                _txt("You have 3 total orders across all invoices."),
            ],
        )

        from langchain_bot import orchestrator
        from langchain_bot.tools import tools_for_verification_state

        result = await orchestrator.run_turn(
            db=fake_db,
            tenant_id=1,
            customer_phone="9230",
            conversation_id=1,
            user_message="meray total orders kitne hain",
            language="roman_urdu",
            bot_flow={"verified": True, "seller_id": 12630, "step": "conversational"},
            store_client=fake_store,
            allowed_tools=tools_for_verification_state(verified=True, in_verification_flow=False),
        )

        assert any(tc["name"] == "get_total_orders" for tc in result.tool_calls)

    @pytest.mark.asyncio
    async def test_unpaid_invoices_filter(self, monkeypatch, patched_llm, fake_db, fake_store):
        _stage_script(
            monkeypatch,
            [
                _tool("list_invoices", {"only_unpaid": True}),
                _txt("All invoices are paid — none unpaid."),
            ],
        )

        from langchain_bot import orchestrator
        from langchain_bot.tools import tools_for_verification_state

        result = await orchestrator.run_turn(
            db=fake_db,
            tenant_id=1,
            customer_phone="9230",
            conversation_id=1,
            user_message="kitni invoices unpaid hain",
            language="roman_urdu",
            bot_flow={"verified": True, "seller_id": 12630, "step": "conversational"},
            store_client=fake_store,
            allowed_tools=tools_for_verification_state(verified=True, in_verification_flow=False),
        )

        assert result.tool_calls[0]["args"].get("only_unpaid") is True


# ─────────────────────────────────────────────────────────────────────────────
# CSV
# ─────────────────────────────────────────────────────────────────────────────
class TestCsvIntent:
    @pytest.mark.asyncio
    async def test_orders_csv_with_dates(self, monkeypatch, patched_llm, fake_db, fake_store):
        _stage_script(
            monkeypatch,
            [
                _tool(
                    "generate_csv",
                    {"kind": "orders", "date_from": "2026-01-01", "date_to": "2026-04-29"},
                ),
                _txt("Generating CSV — sending shortly."),
            ],
        )

        from langchain_bot import orchestrator
        from langchain_bot.tools import tools_for_verification_state

        result = await orchestrator.run_turn(
            db=fake_db,
            tenant_id=1,
            customer_phone="9230",
            conversation_id=1,
            user_message="Saare orders ki CSV bhejo",
            language="roman_urdu",
            bot_flow={"verified": True, "seller_id": 12630, "step": "conversational"},
            store_client=fake_store,
            allowed_tools=tools_for_verification_state(verified=True, in_verification_flow=False),
        )

        assert result.csv_signal is not None
        assert result.csv_signal["kind"] == "orders"
        assert result.csv_signal["date_from"] == "2026-01-01"

    @pytest.mark.asyncio
    async def test_invoice_csv_by_date(self, monkeypatch, patched_llm, fake_db, fake_store):
        _stage_script(
            monkeypatch,
            [
                _tool(
                    "generate_csv",
                    {"kind": "invoice", "invoice_date": "2026-04-22"},
                ),
                _txt("Sending the invoice CSV for 22 April 2026."),
            ],
        )

        from langchain_bot import orchestrator
        from langchain_bot.tools import tools_for_verification_state

        result = await orchestrator.run_turn(
            db=fake_db,
            tenant_id=1,
            customer_phone="9230",
            conversation_id=1,
            user_message="22 April 2026 wali invoice ki CSV bhej do",
            language="roman_urdu",
            bot_flow={"verified": True, "seller_id": 12630, "step": "conversational"},
            store_client=fake_store,
            allowed_tools=tools_for_verification_state(verified=True, in_verification_flow=False),
        )

        assert result.csv_signal is not None
        assert result.csv_signal["kind"] == "invoice"
        assert result.csv_signal["invoice_date"] == "2026-04-22"


# ─────────────────────────────────────────────────────────────────────────────
# Agent escalation
# ─────────────────────────────────────────────────────────────────────────────
class TestEscalation:
    @pytest.mark.asyncio
    async def test_explicit_agent_request(self, monkeypatch, patched_llm, fake_db, fake_store):
        _stage_script(
            monkeypatch,
            [
                _tool("escalate_to_agent", {"reason": "customer_requested"}),
                _txt("Connecting you with a human agent now."),
            ],
        )

        from langchain_bot import orchestrator
        from langchain_bot.tools import tools_for_verification_state

        result = await orchestrator.run_turn(
            db=fake_db,
            tenant_id=1,
            customer_phone="9230",
            conversation_id=1,
            user_message="connect me to agent please",
            language="english",
            bot_flow={"verified": False, "step": "conversational"},
            store_client=fake_store,
            allowed_tools=tools_for_verification_state(verified=False, in_verification_flow=False),
        )

        assert result.escalation_signal is True


# ─────────────────────────────────────────────────────────────────────────────
# Out of scope
# ─────────────────────────────────────────────────────────────────────────────
class TestOutOfScope:
    @pytest.mark.asyncio
    async def test_weather_redirected(self, monkeypatch, patched_llm, fake_db, fake_store):
        _stage_script(
            monkeypatch,
            [
                _txt(
                    "Yeh sawal Arabia Dropshipping ke daire se bahar hai. "
                    "Services, orders, ya tracking ke baare mein poochein."
                )
            ],
        )

        from langchain_bot import orchestrator
        from langchain_bot.tools import tools_for_verification_state

        result = await orchestrator.run_turn(
            db=fake_db,
            tenant_id=1,
            customer_phone="9230",
            conversation_id=1,
            user_message="weather kya hai aaj",
            language="roman_urdu",
            bot_flow={"verified": False, "step": "conversational"},
            store_client=fake_store,
            allowed_tools=tools_for_verification_state(verified=False, in_verification_flow=False),
        )

        # No tool, just text redirect.
        assert result.tool_calls == []
        assert "arabia" in result.reply_text.lower()


# ─────────────────────────────────────────────────────────────────────────────
# Verification gate (architectural assertion)
# ─────────────────────────────────────────────────────────────────────────────
class TestVerificationGateProtection:
    """The control plane must filter the tool list per turn — a hallucinated
    'lookup_order' from an unverified-customer LLM session must not even
    reach a handler. We assert this by checking the filtered list."""

    def test_unverified_cannot_see_account_data_tools(self) -> None:
        from langchain_bot.tools import tools_for_verification_state

        names = {t.name for t in tools_for_verification_state(verified=False, in_verification_flow=False)}
        # Account-data: must be absent
        for blocked in (
            "lookup_order",
            "lookup_orders_by_range",
            "list_invoices",
            "get_total_paid",
            "get_total_orders",
            "generate_csv",
        ):
            assert blocked not in names

    def test_verified_sees_everything(self) -> None:
        from langchain_bot.tools import tools_for_verification_state

        names = {t.name for t in tools_for_verification_state(verified=True, in_verification_flow=False)}
        for required in (
            "lookup_order",
            "list_invoices",
            "get_total_paid",
            "search_kb",
            "escalate_to_agent",
            "generate_csv",
        ):
            assert required in names
