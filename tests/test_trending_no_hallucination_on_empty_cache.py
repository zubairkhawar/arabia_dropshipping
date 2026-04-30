"""
Regression test for WhatsApp transcript 2026-04-30 12:14:

  Customer: "give the trending products of ksa"
  Bot:      Hallucinated 10 generic dropshipping categories
            (Smart Watches, Wireless Earbuds, Portable Juicers, …)

Root cause: when step="trending_showing_products" but the trending cache
was empty (e.g. session was reset between turns), the handler bailed to
ai_forward() with a hint. The general LLM with KB context, given a
trending request and no DB-backed products, hallucinated plausible
dropshipping items from training data.

Fix: when the cache is empty AND the message is itself a fresh trending
ask, re-enter the deterministic trending flow (which is DB-backed). If
an inline country is named, call _show_trending_for_country directly;
otherwise step back to trending_awaiting_country and ask. Never let
ai_forward see a "trending products" request — it will invent.

Also: the system prompt now explicitly forbids listing invented product
names so even if a request slips through, the LLM has a hard rule
against fabricating a numbered list.
"""
from __future__ import annotations

from pathlib import Path


def _service_text() -> str:
    src = (
        Path(__file__).resolve().parent.parent
        / "server" / "services" / "customer_bot_flow" / "service.py"
    )
    return src.read_text(encoding="utf-8")


def _prompt_text() -> str:
    src = (
        Path(__file__).resolve().parent.parent
        / "server" / "langchain_bot" / "prompts.py"
    )
    return src.read_text(encoding="utf-8")


class TestEmptyCacheTrendingHandler:
    def test_old_hint_string_removed(self) -> None:
        text = _service_text()
        # The hint that prompted the LLM to hallucinate must not be in code
        # any more. It used to live around line 5022 inside the
        # `step == "trending_showing_products"` branch when cache was empty.
        bad_hint = "Trending product list was not available in session"
        assert bad_hint not in text, (
            "the ai_forward hint that asked the LLM to 'help them choose a "
            "country for trending products' produced hallucinated lists — "
            "it must be removed"
        )

    def _empty_cache_block(self) -> str:
        """Return just the `if not cache:` body inside the
        `step == "trending_showing_products"` branch."""
        text = _service_text()
        anchor = 'if step == "trending_showing_products":'
        i = text.find(anchor)
        assert i > 0, "trending_showing_products step branch missing"
        # `if not cache:` is the empty-catalogue branch we rewrote.
        j = text.find("if not cache:", i)
        assert j > 0
        # Read until the next top-level `if _wants_trending_more` which is
        # the next sibling inside the same step branch.
        end = text.find("if _wants_trending_more(text)", j)
        assert end > 0
        return text[j:end]

    def test_empty_cache_re_enters_deterministic_flow(self) -> None:
        block = self._empty_cache_block()
        assert "_wants_trending_products(text)" in block
        assert "_show_trending_for_country(" in block

    def test_empty_cache_falls_back_to_country_prompt(self) -> None:
        """When cache is empty, no country in the message, and no tool, we
        should ask the customer which country — not hand off to ai_forward
        with a 'help them' hint."""
        block = self._empty_cache_block()
        assert 'MSGS["trending_ask_country"]' in block
        assert '"trending_awaiting_country"' in block


class TestPromptForbidsInventedProducts:
    def test_prompt_explicitly_blocks_invention(self) -> None:
        """The system prompt must explicitly forbid the LLM from listing
        invented product names. The training-data tropes the bot output in
        the transcript ('Smart Watches', 'Wireless Earbuds', etc.) must be
        listed by the prompt as forbidden examples."""
        p = _prompt_text()
        assert "NEVER list specific products yourself" in p
        # The forbidden-example phrases the model actually emitted.
        for trope in [
            "Smart Watches",
            "Wireless Earbuds",
            "Portable Juicers",
        ]:
            assert trope in p, (
                f"prompt should name {trope!r} as a forbidden invented "
                "product trope so the LLM recognises and refuses the pattern"
            )

    def test_prompt_says_no_invented_numbered_list(self) -> None:
        p = _prompt_text()
        assert "never an invented numbered list" in p, (
            "the rule must explicitly state the LLM cannot output an "
            "invented numbered list when no tool result is available"
        )
