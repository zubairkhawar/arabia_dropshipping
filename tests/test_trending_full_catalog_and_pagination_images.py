"""
Regression tests for WhatsApp transcript 2026-04-30 15:25.

Customer feedback: "trending/winning means all the trending products"
and "when I said aur dikhao it gave products but not the pictures."

Two separate issues:

1. Page size of 5 was too small. Bumped to 50 so a typical catalog
   ships in one batch with images.
2. The LLM-runner path didn't mirror the rendered catalogue into the
   deterministic cache, so the next turn's "Aur dikhao" landed in the
   empty-cache branch and was forwarded to ai_forward — which
   hallucinated "next 5" products WITHOUT images. The runner now writes
   `trending_products_all` and `trending_products_cache` back into the
   flow, and the empty-cache branch refetches from the DB whenever the
   message looks like pagination AND a country is already in flow.
"""
from __future__ import annotations

from pathlib import Path


def _service_text() -> str:
    src = (
        Path(__file__).resolve().parent.parent
        / "server" / "services" / "customer_bot_flow" / "service.py"
    )
    return src.read_text(encoding="utf-8")


def _runner_text() -> str:
    src = (
        Path(__file__).resolve().parent.parent
        / "server" / "services" / "customer_bot_flow" / "trending_llm_runner.py"
    )
    return src.read_text(encoding="utf-8")


class TestPageSizeBumped:
    def test_deterministic_page_size_is_50(self) -> None:
        from services.customer_bot_flow.service import TRENDING_PAGE_SIZE

        assert TRENDING_PAGE_SIZE == 50, (
            "deterministic trending pagination must default to 50 per page; "
            "smaller values force the customer through Aur-dikhao churn"
        )

    def test_llm_runner_page_size_is_50(self) -> None:
        from services.customer_bot_flow.trending_llm_runner import (
            TRENDING_LLM_PAGE_SIZE,
        )

        assert TRENDING_LLM_PAGE_SIZE == 50

    def test_llm_context_holds_full_catalog(self) -> None:
        """The LLM must SEE all up-to-50 products in context, otherwise it
        can't render them. Bumped MAX_PRODUCTS_IN_CONTEXT to 60."""
        from services.customer_bot_flow.trending_llm_runner import (
            TRENDING_LLM_MAX_PRODUCTS_IN_CONTEXT,
            TRENDING_LLM_PAGE_SIZE,
        )

        assert TRENDING_LLM_MAX_PRODUCTS_IN_CONTEXT >= TRENDING_LLM_PAGE_SIZE


class TestRunnerMirrorsCatalogIntoFlowCache:
    def test_build_botflowresult_writes_products_all(self) -> None:
        """After the LLM runner renders, the flow must carry
        `trending_products_all` so the next turn's pagination ("Aur dikhao")
        can read from the cache instead of falling through to ai_forward."""
        text = _service_text()
        i = text.find("def _build_botflowresult_from_llm")
        assert i > 0
        # Read until the next sibling fn definition rather than a
        # fixed-size window — the body has grown.
        end = text.find("\n    def ", i + 50)
        block = text[i:end] if end > i else text[i:]
        # We refetch and store the full catalogue.
        assert 'nf["trending_products_all"]' in block
        assert "list_active_trending_for_country(" in block
        assert "list_active_non_trending_for_country(" in block
        # And mirror the LLM's shown_ids into the cache so the next turn
        # knows what's already been rendered.
        assert 'nf["trending_products_cache"]' in block

    def test_runner_system_prompt_no_longer_caps_at_5(self) -> None:
        """The runner's system prompt previously said 'show up to 5 unseen
        products'. After this change it must instead say 'show ALL unseen
        products' (up to 50 per turn)."""
        text = _runner_text()
        # The old "5 unseen" wording must be gone.
        assert "up to 5 unseen products" not in text, (
            "system prompt still capped at 5 — customer expects the full "
            "trending list in one batch"
        )
        # And the new wording must be present.
        assert "show ALL unseen products" in text


class TestEmptyCacheRefetchesOnAurDikhao:
    def test_empty_cache_refetches_when_country_known(self) -> None:
        """When step="trending_showing_products" and the cache is empty but
        the flow already carries a known trending_country, "Aur dikhao"
        must trigger a fresh DB fetch via _show_trending_for_country —
        NOT bail to ai_forward (which used to hallucinate the next page)."""
        text = _service_text()
        anchor = 'if step == "trending_showing_products":'
        i = text.find(anchor)
        assert i > 0
        # Find the empty-cache branch and read up to the next sibling.
        j = text.find("if not cache:", i)
        end = text.find("if _wants_trending_more(text)", j)
        block = text[j:end]
        assert "_wants_trending_more(text)" in block, (
            "empty-cache branch must check for pagination intent so we can "
            "refetch the catalogue instead of bailing to ai_forward"
        )
        # And we must refetch via the deterministic flow, which is DB-backed.
        assert "_show_trending_for_country(" in block
        # The known-country guard prevents fetching with a bogus code.
        assert '"UAE", "KSA", "PK"' in block or "'UAE', 'KSA', 'PK'" in block
