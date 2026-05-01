"""
Regression test for WhatsApp transcript 2026-05-01 11:48-11:49.

Customer (verified, mid-conversation):
  Bot:      "Aap ko orders ki CSV file chahiye? Bas mujhe yahan par
            request bhej dein, jaise 'last month ki orders CSV bhejo'
            ya '22 April se 30 April tak ki orders ki CSV chahiye'..."
  Customer: "22 April se 30 April"

The LLM picked `lookup_orders_by_range` instead of `generate_csv` and
listed 5 orders inline. The customer asked for a FILE, not an inline
list — they explicitly continued a CSV ask.

Fix: added a "CSV continuations" rule to the prompt that explicitly
tells the LLM "if your prior turn told the customer to send a CSV
request and they reply with just a date range, that IS the CSV ask —
call generate_csv, do NOT call lookup_orders_by_range".

Verified live: with this rule, the LLM picks
`generate_csv(kind="orders", date_from="2026-04-22", date_to="2026-04-30")`
on the same turn that previously picked lookup_orders_by_range.
"""
from __future__ import annotations

from pathlib import Path

import pytest


PROMPTS = (
    Path(__file__).resolve().parent.parent
    / "server" / "langchain_bot" / "prompts.py"
)


def _prompts() -> str:
    return PROMPTS.read_text(encoding="utf-8")


class TestCsvContinuationRulePresent:
    def test_continuation_rule_in_prompt(self) -> None:
        p = _prompts()
        assert "CSV continuations" in p, (
            "the CSV-continuation rule must be in the prompt — without "
            "it the LLM picks lookup_orders_by_range for bare date-range "
            "follow-ups (transcript 2026-05-01 11:48)"
        )

    def test_rule_explicitly_warns_against_lookup_orders_by_range(self) -> None:
        p = _prompts()
        # The rule must explicitly tell the LLM not to use the wrong tool.
        assert "Do NOT call `lookup_orders_by_range`" in p

    @pytest.mark.parametrize(
        "phrase",
        [
            # The rule lists concrete date-range examples the LLM might see
            "22 April se 30 April",
            "April 2026",
            "last month",
            "pichle hafte",
        ],
    )
    def test_rule_lists_concrete_examples(self, phrase: str) -> None:
        p = _prompts()
        assert phrase in p, (
            f"the CSV-continuation rule must list {phrase!r} as an example "
            "so the LLM recognises bare date-range continuations"
        )

    def test_rule_says_call_generate_csv(self) -> None:
        p = _prompts()
        # Within the continuation rule, must instruct the LLM to call the tool.
        i = p.find("CSV continuations")
        assert i > 0
        # Read until next bullet point
        end = p.find("\n- ", i + 50)
        block = p[i:end] if end > i else p[i: i + 1500]
        assert "generate_csv(kind=\"orders\"" in block
