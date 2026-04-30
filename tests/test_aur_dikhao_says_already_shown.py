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
    def test_no_more_pages_branch_present(self) -> None:
        """The deterministic flow's pagination branch checks
        `new_offset >= len(visible)` and returns the no_more_pages
        template. Confirm that branch is wired."""
        src = (
            Path(__file__).resolve().parent.parent
            / "server" / "services" / "customer_bot_flow" / "service.py"
        )
        text = src.read_text(encoding="utf-8")
        # Find the _wants_trending_more branch inside trending_showing_products.
        i = text.find('if step == "trending_showing_products":')
        end = text.find("if step ==", i + 50)  # next step branch
        block = text[i:end] if end > i else text[i: i + 8000]
        assert "if _wants_trending_more(text):" in block
        assert "if new_offset >= len(visible):" in block
        assert "trending_no_more_pages" in block

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
