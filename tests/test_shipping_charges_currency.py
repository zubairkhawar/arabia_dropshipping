"""
Regression test for WhatsApp transcript 2026-05-05 20:28.

Customer asked KSA shipping charges. Bot replied:
  KSA: Delivered 25 SAR · Returned 10 AED · 3% COD tax

The user had updated the KB to "Returned: 10 SAR" but the bot
ignored the KB and used the hardcoded CRITICAL FACTS in
server/langchain_bot/prompts.py — which had "10 AED" wrong in
three places. The prompt explicitly tells the LLM "Don't call
search_kb for hardcoded facts already in CRITICAL FACTS — those
are authoritative", so the LLM correctly trusts the prompt over
the KB. The fix was to correct the hardcoded value.

KSA always uses SAR. AED appearing in any KSA shipping line is a bug.
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


class TestKSAUsesSAR:
    """KSA shipping charges in the system prompt must always be in SAR.
    AED in any KSA shipping line is a regression."""

    def test_ksa_critical_facts_uses_sar_not_aed(self) -> None:
        text = _prompts()
        # Find the "Shipping KSA" line and ensure return is in SAR.
        i = text.find("Shipping KSA:")
        assert i > 0
        line_end = text.find("\n", i)
        line = text[i:line_end]
        assert "Returned 10 SAR" in line, (
            f"KSA shipping line is wrong. Found: {line!r}. "
            "KSA always uses SAR — AED here would surface to customers."
        )
        assert "10 AED" not in line

    def test_returned_orders_rule_uses_sar_for_ksa(self) -> None:
        text = _prompts()
        # The TONE rule "For returned orders: use return charge..."
        i = text.find("For **returned orders**:")
        assert i > 0
        line_end = text.find("\n", i)
        line = text[i:line_end]
        assert "10 SAR KSA" in line, (
            f"returned-orders rule is wrong. Found: {line!r}"
        )
        assert "10 AED KSA" not in line

    def test_single_order_detail_rule_uses_sar_for_ksa(self) -> None:
        text = _prompts()
        # The SINGLE ORDER DETAIL section's "Returned orders" rule.
        i = text.find("Returned orders: 5 AED UAE")
        assert i > 0
        line_end = text.find("\n", i)
        line = text[i:line_end]
        assert "10 SAR KSA" in line, (
            f"single-order returned-orders rule is wrong. Found: {line!r}"
        )

    @pytest.mark.parametrize(
        "wrong_phrase",
        [
            "Returned 10 AED",
            "10 AED KSA",
            "KSA: 10 AED",
            "KSA, 10 AED",
        ],
    )
    def test_wrong_phrasings_absent(self, wrong_phrase: str) -> None:
        """Catch any future drift back to AED for KSA returns."""
        text = _prompts()
        # Note: "5 AED UAE / 10 SAR KSA" must remain — only check
        # phrasings where AED is paired with KSA explicitly.
        assert wrong_phrase not in text, (
            f"{wrong_phrase!r} reintroduces the AED/SAR mix-up. KSA → SAR."
        )

    def test_other_currency_facts_unchanged(self) -> None:
        """Sanity: we didn't accidentally break the UAE / Pakistan rates."""
        text = _prompts()
        assert "Shipping UAE: Delivered 18 AED · Returned 5 AED" in text
        assert "TCS 250 PKR" in text
        assert "Other couriers (Leopard/Postex/Trax) 200 PKR" in text
