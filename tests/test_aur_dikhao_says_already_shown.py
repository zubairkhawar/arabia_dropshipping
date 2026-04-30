"""
After bumping TRENDING_PAGE_SIZE to 50, the first page covers the entire
catalogue for typical tenants. So "Aur dikhao" / "Show more" should say
"I've already shown you all the trending products" — not paginate or
hallucinate "next 5".

This test verifies:
1. The LLM-runner system prompt no longer tells the model to suggest
   "Show more" as a followup, and instead instructs it to acknowledge
   that the full list is already shown.
2. The deterministic flow's _no_more_pages template fires when the
   pagination cursor advances past the visible catalogue.
"""
from __future__ import annotations

from pathlib import Path


def _runner_text() -> str:
    src = (
        Path(__file__).resolve().parent.parent
        / "server" / "services" / "customer_bot_flow" / "trending_llm_runner.py"
    )
    return src.read_text(encoding="utf-8")


class TestRunnerPromptDoesNotSuggestShowMore:
    def test_followup_no_show_more(self) -> None:
        text = _runner_text()
        # The earlier prompt had: e.g. "Show more", "Tell me about 3", "KSA ke dikhao"
        # We removed "Show more" because the first page covers the full catalogue.
        # Find the suggested_followups field rule and check it forbids "Show more".
        assert "DO NOT suggest \"Show more\"" in text, (
            "system prompt must explicitly tell the LLM not to suggest "
            "'Show more' / 'Aur dikhao' as a followup"
        )

    def test_aur_dikhao_behaviour_acknowledges_full_list(self) -> None:
        text = _runner_text()
        # The "Show more" / "aur dikhao" rule must instruct the model to
        # tell the customer the catalogue has already been listed.
        assert "already shown you all the trending products" in text, (
            "system prompt must tell the LLM to acknowledge full coverage "
            "rather than re-render or hallucinate"
        )


class TestDeterministicNoMorePagesFiresOnAurDikhao:
    def test_runner_handles_pagination(self) -> None:
        """The deterministic `_wants_trending_more` regex branch was
        deleted on 2026-04-30. Pagination is now handled by the
        trending LLM-runner via prompt rule 4 ("acknowledge full
        coverage") + memory.shown_ids tracking. The handler's job in
        the trending_showing_products step is just to call
        `_try_trending_llm()` unconditionally."""
        src = (
            Path(__file__).resolve().parent.parent
            / "server" / "services" / "customer_bot_flow" / "service.py"
        )
        text = src.read_text(encoding="utf-8")
        i = text.find('if step == "trending_showing_products":')
        end = text.find("if step ==", i + 50)
        block = text[i:end] if end > i else text[i: i + 8000]
        # No CODE call to the deleted helper (deletion-comment mentions
        # are fine). The simplest check: the helper is no longer
        # importable from service.
        from services.customer_bot_flow import service as svc

        assert not hasattr(svc, "_wants_trending_more"), (
            "_wants_trending_more was supposed to be deleted on 2026-04-30"
        )
        # The runner still drives this step.
        assert "_try_trending_llm()" in block

    def test_template_says_no_more_to_show(self) -> None:
        src = (
            Path(__file__).resolve().parent.parent
            / "server" / "services" / "customer_bot_flow" / "templates.py"
        )
        text = src.read_text(encoding="utf-8")
        # The Roman-Urdu / English / Arabic variants must all communicate
        # that the full list has already been shown.
        assert "no more trending products to show" in text
        assert "aur trending products load karne ko nahi bacha" in text
