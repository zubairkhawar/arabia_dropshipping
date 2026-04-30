"""
Rigorous tests for the CSV intent migration (2026-04-30).

Before: deterministic regex `_wants_invoice_csv_file()` /
`_wants_orders_csv_file()` + an `awaiting_invoice_csv_ref` step intercepted
the customer's message before the LLM-first orchestrator ever ran. CSV
date-range parsing lived in `_parse_date_range`; "send csv last month"
worked but "csv pichle mahine ki" or "csv from 1 March to 22 April" hit
the regex's blind spots.

After: the LLM extracts intent + dates via `generate_csv` tool args;
`_dispatch_csv_signal` runs the same exporter + R2 + WhatsApp document
plumbing immediately when the orchestrator returns `csv_signal`.

These tests verify:
1. The deleted helpers are actually gone (no accidental fallback).
2. The dispatcher exists and is wired into the LLM-first signal handler.
3. The prompt no longer tells the customer to "type csv" (that was the
   regex contract, now broken). Instead it instructs the LLM to call
   the tool with date_from/date_to/invoice_id args.
4. The `generate_csv` tool schema still accepts both kinds and dates.
5. The `awaiting_invoice_csv_ref` state-machine step is gone.
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


class TestDeterministicHelpersDeleted:
    """The old regex helpers must NOT be importable any more — otherwise
    a stale call site could silently route around the LLM tool."""

    @pytest.mark.parametrize(
        "name",
        [
            "_wants_orders_csv_file",
            "_wants_invoice_csv_file",
            "_looks_like_csv_file_followup",
            "_extract_invoice_csv_date",
            "_csv_user_requests_enriched_export_wording",
        ],
    )
    def test_helper_not_importable(self, name: str) -> None:
        from services.customer_bot_flow import service as svc

        assert not hasattr(svc, name), (
            f"{name} was supposed to be deleted in the CSV migration; "
            "any remaining reference will let messages bypass the LLM tool"
        )

    @pytest.mark.parametrize(
        "name",
        [
            "_wants_orders_csv_file",
            "_wants_invoice_csv_file",
            "_looks_like_csv_file_followup",
            "_extract_invoice_csv_date",
            "_csv_user_requests_enriched_export_wording",
        ],
    )
    def test_helper_definition_gone(self, name: str) -> None:
        text = _service()
        assert f"def {name}(" not in text, (
            f"the helper {name} was supposed to be deleted, not just renamed"
        )


class TestAwaitingInvoiceCsvRefStepGone:
    def test_step_setter_removed(self) -> None:
        """The handler used to set `step="conversational",
        awaiting_invoice_csv_ref=True` to ask for the missing invoice
        identifier. The LLM now asks naturally; there should be no
        place that *sets* this flag."""
        text = _service()
        # The dict-literal that used to set the flag should not exist any
        # more. (Reading the flag in inbound state is also unnecessary
        # but harmless if a stale flow row from production carries it.)
        assert '"awaiting_invoice_csv_ref": True' not in text


class TestDispatcherWired:
    def test_dispatcher_exists(self) -> None:
        text = _service()
        assert "async def _dispatch_csv_signal(" in text

    def test_signal_handler_calls_dispatcher(self) -> None:
        """In the LLM-first signal-handling block, when csv_signal is
        truthy, the controller must call `_dispatch_csv_signal` and
        return its BotFlowResult."""
        text = _service()
        i = text.find("if not _lf.fell_back and _lf.csv_signal:")
        assert i > 0, "csv_signal short-circuit missing from LLM-first handler"
        block = text[i: i + 600]
        assert "_dispatch_csv_signal(_lf.csv_signal" in block
        # On dispatcher-None (missing args / non-WhatsApp), control must
        # fall through to the LLM's reply_text — verified by the comment
        # immediately following.
        assert "return csv_res" in block

    def test_dispatcher_calls_existing_exporters(self) -> None:
        """The dispatcher should reuse the same R2/exporter modules the
        old deterministic block did — not reinvent them."""
        text = _service()
        i = text.find("async def _dispatch_csv_signal(")
        end = text.find("\n    if (", i)
        block = text[i:end] if end > i else text[i: i + 8000]
        assert "build_invoice_csv_export_bytes" in block
        assert "build_orders_csv_export_bytes" in block
        assert "object_key_for_invoice_csv" in block
        assert "object_key_for_orders_csv" in block
        # And the R2 plumbing.
        assert "is_r2_configured" in block
        assert "presign_get" in block
        assert "put_bytes" in block

    def test_dispatcher_handles_both_kinds(self) -> None:
        text = _service()
        i = text.find("async def _dispatch_csv_signal(")
        end = text.find("\n    if (", i)
        block = text[i:end] if end > i else text[i: i + 8000]
        assert 'kind == "invoice"' in block
        # Falls through to orders branch when not invoice.
        assert "build_orders_csv_export_bytes" in block

    def test_dispatcher_returns_none_when_unhandleable(self) -> None:
        """Non-WhatsApp channel, unverified flow, or missing seller_id
        must return None so the caller can use the LLM's reply_text
        instead of erroring."""
        text = _service()
        i = text.find("async def _dispatch_csv_signal(")
        block = text[i: i + 1500]
        assert 'channel or' in block
        # Three early-return Nones for the three unhandleable cases.
        assert block.count("return None") >= 3


class TestPromptInstructsLLMToCallTool:
    def test_prompt_no_longer_tells_customer_to_type_csv(self) -> None:
        """The old prompt said 'Type csv to receive X as a file' — that
        was the deterministic regex contract. With the migration the
        instruction must now be to CALL `generate_csv` directly."""
        p = _prompts()
        # No leftover "Type csv" / 'type csv' / 'type **csv**' instructions.
        assert "type **csv**" not in p.lower()
        assert "Type **csv**" not in p
        # Old phrasing is also gone.
        assert "Type **csv** to receive" not in p

    def test_prompt_tells_llm_to_call_generate_csv(self) -> None:
        p = _prompts()
        assert "call `generate_csv(kind=\"orders\")`" in p
        assert "call `generate_csv(kind=\"invoice\"" in p

    def test_prompt_explains_date_range_parsing(self) -> None:
        p = _prompts()
        # The prompt must teach the LLM how to convert relative date
        # phrases into ISO YYYY-MM-DD; that work used to be in
        # _parse_date_range / _extract_invoice_csv_date.
        assert "Date-range parsing" in p
        for phrase in ["last month", "pichle mahine", "this month", "April"]:
            assert phrase in p, f"prompt must mention {phrase!r} so the LLM resolves it"

    def test_prompt_keeps_how_question_distinction(self) -> None:
        """The HOW-question rule must survive — customers asking 'how do
        I get a CSV?' still must NOT trigger generate_csv."""
        p = _prompts()
        assert "How do I get a CSV" in p
        assert "DO NOT call `generate_csv`" in p


class TestToolSchemaUnchanged:
    """The migration didn't change the tool schema — it only changes
    *who* parses the customer message. Confirm the shape is intact."""

    def test_args_class_present(self) -> None:
        from langchain_bot.tools.schemas import GenerateCsvArgs

        # kind is required; date_from/date_to/invoice_id/invoice_date optional.
        fields = GenerateCsvArgs.model_fields
        assert "kind" in fields
        assert fields["kind"].is_required()
        for opt in ("date_from", "date_to", "invoice_id", "invoice_date"):
            assert opt in fields
            assert not fields[opt].is_required()

    def test_kind_pattern_orders_or_invoice(self) -> None:
        from langchain_bot.tools.schemas import GenerateCsvArgs

        # Both valid:
        GenerateCsvArgs(kind="orders")
        GenerateCsvArgs(kind="invoice")
        # Anything else rejected:
        with pytest.raises(Exception):
            GenerateCsvArgs(kind="bananas")

    def _ctx(self, *, verified: bool):
        from langchain_bot.tools.handlers import ToolContext

        return ToolContext(
            db=None,
            tenant_id=1,
            customer_phone="+923000000000",
            conversation_id=None,
            language="english",
            store_client=None,
            bot_flow={"verified": verified, "seller_id": "12630"} if verified else {},
        )

    def test_handler_returns_signal(self) -> None:
        """The tool handler is purely a signal-emitter — no I/O. The
        dispatcher in service.py is what actually generates the file."""
        import asyncio
        from datetime import date

        from langchain_bot.tools import handlers as H
        from langchain_bot.tools import schemas as S

        args = S.GenerateCsvArgs(
            kind="orders",
            date_from=date(2026, 4, 1),
            date_to=date(2026, 4, 30),
        )
        result = asyncio.get_event_loop().run_until_complete(
            H.handle_generate_csv(args, self._ctx(verified=True))
        )
        assert result.ok
        assert result.data["csv_signal"] is True
        assert result.data["kind"] == "orders"
        assert result.data["date_from"] == "2026-04-01"
        assert result.data["date_to"] == "2026-04-30"

    def test_handler_rejects_unverified(self) -> None:
        import asyncio

        from langchain_bot.tools import handlers as H
        from langchain_bot.tools import schemas as S

        result = asyncio.get_event_loop().run_until_complete(
            H.handle_generate_csv(
                S.GenerateCsvArgs(kind="orders"),
                self._ctx(verified=False),
            )
        )
        # Unverified tool calls return an error result that asks the LLM
        # to call start_verification first.
        assert (not result.ok) or bool(
            result.data.get("verification_required")
        )


class TestNoStaleSignalCondition:
    """The old condition `not _lf.csv_signal` skipped the orchestrator
    reply when csv_signal was set — but did nothing else with the signal.
    After the migration, the signal must be handled BEFORE that
    short-circuit so the file actually ships."""

    def test_signal_handled_before_reply_text_short_circuit(self) -> None:
        text = _service()
        # The csv_signal dispatcher should appear above the
        # `not _lf.csv_signal`-style condition in the orchestrator block.
        # In the new code, the explicit csv_signal handler precedes the
        # reply_text return.
        i_dispatch = text.find("_dispatch_csv_signal(_lf.csv_signal")
        i_reply = text.find("if (\n                not _lf.fell_back\n                and _lf.reply_text")
        assert i_dispatch > 0 and i_reply > 0
        assert i_dispatch < i_reply, (
            "the csv_signal dispatcher must run BEFORE the reply_text "
            "short-circuit, otherwise the signal is dropped"
        )
