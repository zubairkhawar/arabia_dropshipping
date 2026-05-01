"""
Regression test for WhatsApp transcript 2026-05-01 12:10–12:11.

Customer (after /reset, unverified):
  Customer: "meray store k aaj tak total kitnay orders hain"
  Bot:      "Aap ka data fetch karne mein abhi masla aa raha hai..."
                  ── WRONG: should have started verification ──

Customer: "mera store ki pehli invoice kis date ko ayi thi"
Bot:      "Apne account se jura hua email address bhejein."
                  ── CORRECT: invoice-shaped, bootstrap fired ──

  Customer: "mailto:Urbanmart097@gmail.com" → Bot asked mobile
  Customer: "03474685920" → bot replied:
    "Aap ka data fetch karne mein abhi masla aa raha hai..."
                  ── WRONG: verification succeeded but resume question
                     was routed through the legacy ai_forward path
                     which surfaces "Store API error" on transient
                     fetch_customer_context failures ──

Two fixes:
  1. Added aggregate / count phrasings to is_asking in
     _looks_like_order_status_question (kitne, kitni, kitna, kitnay,
     total, how many, count, kul, saare, ratio, percentage, average).
     Plus added _looks_like_analytics_question to the bootstrap
     detector set so "delivery ratio", "return ratio", "average
     profit per order" trigger verification too.
  2. Post-verification resume now goes through run_one_turn (the
     LLM-first orchestrator) instead of ai_forward (legacy). The
     orchestrator's tool path has per-tool retry; the legacy path's
     fetch_customer_context surfaces "Store API error" verbatim on
     any transient blip.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from services.customer_bot_flow.service import (
    _extract_standalone_email,
    _is_explicit_verification_consent,
    _is_likely_order_id_only,
    _looks_like_account_question,
    _looks_like_analytics_question,
    _looks_like_invoice_for_order,
    _looks_like_order_status_question,
)


def _bootstrap(msg: str) -> bool:
    """Mirror the production gate logic for an unverified flow."""
    return (
        _looks_like_order_status_question(msg)
        or _is_likely_order_id_only(msg)
        or _looks_like_account_question(msg)
        or _looks_like_invoice_for_order(msg)
        or _is_explicit_verification_consent(msg)
        or _looks_like_analytics_question(msg)
        or bool(_extract_standalone_email(msg))
    )


SERVICE = (
    Path(__file__).resolve().parent.parent
    / "server" / "services" / "customer_bot_flow" / "service.py"
)


class TestTranscriptMessagesNowCaught:
    """The exact messages from the 2026-05-01 12:10 transcript."""

    @pytest.mark.parametrize(
        "msg",
        [
            "meray store k aaj tak total kitnay orders hain",
            "mera store ki pehli invoice kis date ko ayi thi",
        ],
    )
    def test_transcript_message_triggers_bootstrap(self, msg: str) -> None:
        assert _bootstrap(msg), (
            f"{msg!r} from the 2026-05-01 transcript must trigger "
            "the bootstrap. Without it the LLM-first path runs but "
            "ACCOUNT_DATA tools are filtered out for unverified "
            "customers and the LLM falls back to a generic 'data fetch "
            "error' reply instead of starting verification."
        )


class TestAggregateAndCountPhrasingsCaught:
    """The new is_asking keywords + analytics_question membership in
    the bootstrap should catch a wide range of count/aggregate asks
    that previously slipped through."""

    @pytest.mark.parametrize(
        "msg",
        [
            # Total / count
            "total kitne orders hain",
            "kitni invoices bani hain",
            "kitnay orders deliver hue",
            "how many orders do I have",
            "total order count batao",
            "kul orders kitne",
            "saari invoices kitni hain",
            # Analytics / ratios
            "delivery ratio kya hai",
            "return ratio kitni hai",
            "mera average profit per order kya hai",
            "top selling product mera kaunsa hai",
            "top cities show karo",
            "profit by month batao",
        ],
    )
    def test_aggregate_phrasing_triggers_bootstrap(self, msg: str) -> None:
        assert _bootstrap(msg), (
            f"{msg!r} is an account-data question that requires "
            "verification — the bootstrap must fire so the deterministic "
            "state machine transitions to existing_awaiting_email."
        )


class TestServiceQuestionsDoNotTrigger:
    """Make sure we didn't make the bootstrap too eager. Service /
    KB questions must still bypass it and reach the LLM-first path."""

    @pytest.mark.parametrize(
        "msg",
        [
            # Service / FAQ
            "what are the shipping rates",
            "what is dropshipping",
            "fulfillment service kya hai",
            "payment kab hoti hai",
            "how does payment work",
            # Greetings
            "hi",
            "hello there",
            "salam",
            # Comparisons / KB
            "arabia dropship zambeel say kesay behtar hai",
            # Pure acks
            "thanks",
            "ok",
            "shukriya",
        ],
    )
    def test_service_question_does_not_trigger(self, msg: str) -> None:
        assert not _bootstrap(msg), (
            f"{msg!r} is a service / KB / greeting question — must "
            "NOT trigger verification. If it does, every customer "
            "gets pushed into the verification flow before they can "
            "ask a service question."
        )


class TestPostVerificationUsesLLMFirstOrchestrator:
    """When verification completes, the resume question must go
    through run_one_turn (modern tool path with per-tool retry),
    NOT ai_forward (legacy path that surfaces 'Store API error')."""

    def test_resume_path_calls_orchestrator(self) -> None:
        text = SERVICE.read_text(encoding="utf-8")
        # Find the post-verification Case C resume branch.
        i = text.find("Case C: pending non-order question")
        assert i > 0
        # Read until the next case (Case D).
        end = text.find("Case D:", i)
        block = text[i:end] if end > i else text[i: i + 3000]
        # Must invoke the orchestrator.
        assert "from langchain_bot.control_plane import run_one_turn" in block
        assert "_llm_first_run(" in block
        # And dispatch any csv_signal that comes back.
        assert "_dispatch_csv_signal(_lf.csv_signal" in block
        # Falls back to ai_forward only on orchestrator failure.
        assert 'ai_forward("[Customer question] " + resume_q' in block
