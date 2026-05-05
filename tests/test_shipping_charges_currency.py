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


class TestDeterministicShippingTemplate:
    """server/services/customer_bot_flow/service.py has a deterministic
    FAQ template (asks_shipping branch) that pre-empts the LLM for any
    shipping-charges question. WhatsApp transcript 2026-05-05 20:39 hit
    this template — it said "Returned: 10 AED" for KSA in all three
    language variants (English / Arabic / Roman Urdu). The prompt fix
    alone wasn't enough because the template runs FIRST."""

    SERVICE = (
        Path(__file__).resolve().parent.parent
        / "server" / "services" / "customer_bot_flow" / "service.py"
    )

    def _service(self) -> str:
        return self.SERVICE.read_text(encoding="utf-8")

    def test_template_branch_uses_sar_for_ksa_english(self) -> None:
        text = self._service()
        # Find the asks_shipping branch and look at its English variant.
        i = text.find("if asks_shipping:")
        assert i > 0
        # English block runs through to the next 'if lang ==' or end.
        end = text.find("if lang == \"arabic\":", i)
        block = text[i:end] if end > i else text[i: i + 2000]
        # KSA Returned line must use SAR.
        assert "🇸🇦 KSA:" in block
        assert "  • Returned: 10 SAR\\n" in block, (
            "KSA returned charge in the English shipping template must "
            "be in SAR, not AED. The transcript 2026-05-05 20:39 caught "
            "the AED variant."
        )

    def test_template_branch_uses_sar_for_ksa_arabic(self) -> None:
        text = self._service()
        i = text.find('if lang == "arabic":', text.find("if asks_shipping:"))
        end = text.find('return (', i)
        end = text.find('return (', end + 1)  # second `return` = roman_urdu
        block = text[i:end] if end > i else text[i: i + 2000]
        # Arabic KSA returned must be in ريال (riyal), not دراهم (dirhams).
        assert "🇸🇦 السعودية" in block
        assert "10 ريال" in block, "Arabic KSA returned must use riyal"
        # The wrong "10 دراهم" (dirhams) must not appear in the KSA block.
        # We can't simply check absence of "10 دراهم" globally because
        # the UAE penalty / fulfillment templates legitimately use it.
        ksa_idx = block.find("🇸🇦 السعودية")
        # The KSA block ends at the next country flag.
        ksa_end = block.find("🇵🇰", ksa_idx)
        ksa_block = block[ksa_idx:ksa_end] if ksa_end > ksa_idx else block[ksa_idx:]
        assert "10 دراهم" not in ksa_block, (
            "Arabic KSA returned must not say '10 دراهم' (dirhams)"
        )

    def test_template_branch_uses_sar_for_ksa_roman_urdu(self) -> None:
        text = self._service()
        # Find the LAST return inside asks_shipping (roman_urdu fallback).
        i = text.find("if asks_shipping:")
        end = text.find("# ── Payment Day", i)
        block = text[i:end] if end > i else text[i: i + 5000]
        # Find the LAST "🇸🇦 KSA:" in this block — that's the roman_urdu one.
        last_ksa = block.rfind("🇸🇦 KSA:")
        assert last_ksa > 0
        # Read until the next country flag.
        ksa_end = block.find("🇵🇰", last_ksa)
        ksa_block = block[last_ksa:ksa_end] if ksa_end > last_ksa else block[last_ksa:]
        assert "  • Returned: 10 SAR\\n" in ksa_block
        assert "10 AED" not in ksa_block, (
            "Roman Urdu KSA returned charge must be in SAR, not AED — "
            "the WhatsApp transcript 2026-05-05 20:39 saw '10 AED' here."
        )
