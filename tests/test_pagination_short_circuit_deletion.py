"""
Tests for the pagination short-circuit deletion (2026-04-30).

Before: a 100+ LOC regex layer (`_TRENDING_MORE_TOKEN_PHRASES`,
`_TRENDING_MORE_PHRASES`, `_wants_trending_more()`) bypassed the LLM
trending runner whenever the customer's message looked like
pagination ("aur dikhao" / "show more" / "المزيد"). The pagination
branch then advanced trending_offset by TRENDING_PAGE_SIZE and
re-rendered the next page from the cache.

After: the LLM trending runner handles pagination via its own prompt
rule 4 + memory.shown_ids tracking. With page-size 50, typical
catalogues land on the first page in their entirety, so "aur dikhao"
becomes "I've already shown you all the trending products" — naturally
delivered by the runner.

These tests verify the deletion is complete:
1. The regex constants are gone.
2. The helper function is gone and not importable.
3. The deterministic pagination block in trending_showing_products
   is gone.
4. The pagination short-circuit (`_is_pagination_only`) is gone.
5. The empty-cache refetch still works (degraded-mode safety net).
6. The `_select_trending_product_from_list` no longer references the
   deleted helper.
"""
from __future__ import annotations

from pathlib import Path

import pytest


SERVICE = (
    Path(__file__).resolve().parent.parent
    / "server" / "services" / "customer_bot_flow" / "service.py"
)


def _service() -> str:
    return SERVICE.read_text(encoding="utf-8")


class TestRegexConstantsDeleted:
    @pytest.mark.parametrize(
        "name",
        [
            "_TRENDING_MORE_TOKEN_PHRASES",
            "_TRENDING_MORE_PHRASES",
            "_wants_trending_more",
        ],
    )
    def test_symbol_not_importable(self, name: str) -> None:
        from services.customer_bot_flow import service as svc

        assert not hasattr(svc, name), (
            f"{name} was supposed to be deleted in the pagination "
            "short-circuit migration"
        )

    def test_definitions_gone(self) -> None:
        text = _service()
        # Allow comment mentions but no actual definitions or assignments.
        assert "_TRENDING_MORE_TOKEN_PHRASES: tuple[" not in text
        assert "_TRENDING_MORE_PHRASES: tuple[" not in text
        assert "def _wants_trending_more(" not in text


class TestPaginationBranchGoneFromHandler:
    def test_no_is_pagination_only_flag(self) -> None:
        text = _service()
        # The short-circuit flag must be gone.
        assert "_is_pagination_only" not in text

    def test_runner_unconditional_in_step_handler(self) -> None:
        text = _service()
        i = text.find('if step == "trending_showing_products":')
        end = text.find("if step ==", i + 50)
        block = text[i:end] if end > i else text[i: i + 8000]
        # Single, unconditional runner call.
        assert "llm_res = await _try_trending_llm()" in block
        # No conditional like `... if _is_pagination_only else ...`
        assert "_is_pagination_only else" not in block

    def test_deterministic_pagination_block_gone(self) -> None:
        """The 80-line block that advanced trending_offset, rebuilt the
        page, and attached new WhatsApp images is gone. We check by
        absence of the unique markers it carried."""
        text = _service()
        i = text.find('if step == "trending_showing_products":')
        end = text.find("if step ==", i + 50)
        block = text[i:end] if end > i else text[i: i + 8000]
        # The most distinctive line was the offset advance:
        assert "new_offset = offset + TRENDING_PAGE_SIZE" not in block
        # And the more-batch body builder:
        assert "is_more_batch=True" not in block


class TestEmptyCacheRefetchStillWorks:
    """Belt-and-braces: when the runner returns None (degraded mode)
    and the cache is empty, we still refetch from the DB rather than
    bailing to ai_forward (which would hallucinate). This safety net
    is the property the user cared about: 'send all the products from
    the db'."""

    def test_empty_cache_refetches_from_db_with_known_country(self) -> None:
        text = _service()
        i = text.find('if step == "trending_showing_products":')
        end = text.find("if step ==", i + 50)
        block = text[i:end] if end > i else text[i: i + 8000]
        # The empty-cache branch must call _show_trending_for_country
        # when trending_country is set.
        assert "if not cache:" in block
        assert "_show_trending_for_country(" in block
        # Country guard: only refetch for supported markets.
        assert '"UAE", "KSA", "PK"' in block or "'UAE', 'KSA', 'PK'" in block


class TestSelectTrendingProductGuardRemoved:
    """`_select_trending_product_from_list` used to call
    `_wants_trending_more(query)` to filter "show more" out of product
    name matching. With the helper deleted, that call site must be
    cleaned up too."""

    def test_no_call_in_select_helper(self) -> None:
        text = _service()
        i = text.find("def _select_trending_product_from_list(")
        end = text.find("\n\ndef ", i)
        block = text[i:end] if end > i else text[i: i + 4000]
        # No code call to the deleted helper in this function body.
        # (Commented mentions don't fail this — we look for the call
        # pattern only.)
        for ln in block.splitlines():
            if "_wants_trending_more" in ln and not ln.lstrip().startswith("#"):
                pytest.fail(f"non-comment reference still present: {ln.strip()!r}")


class TestRunnerPromptStillCoversPagination:
    """The migration relies on the LLM runner's system prompt to
    handle 'aur dikhao'. Confirm the contract is still spelled out."""

    def test_prompt_says_already_shown_all(self) -> None:
        runner = (
            Path(__file__).resolve().parent.parent
            / "server" / "services" / "customer_bot_flow"
            / "trending_llm_runner.py"
        )
        text = runner.read_text(encoding="utf-8")
        # Rule 4 explicitly handles "show more" / "aur dikhao".
        assert "Show more" in text or "show more" in text
        assert "already shown you all" in text or "already shown" in text
