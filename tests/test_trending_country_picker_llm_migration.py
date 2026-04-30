"""
Rigorous tests for the trending country-picker migration (2026-04-30).

Before: every "show me trending" request that didn't name a country
landed on a deterministic 1️⃣2️⃣3️⃣ emoji menu (`MSGS["trending_ask_country"]`)
parsed by `_parse_trending_country_reply`. The customer had to either
reply with a digit or type a country alias matching the regex's
narrow alias list.

After: the trending LLM-runner asks naturally ("Which market — UAE,
KSA, or Pakistan?") and resolves the customer's reply via
`_detect_country` (a wider alias set including Arabic, Roman Urdu,
plus the digits "1"/"2"/"3" for backwards compat). The deterministic
1/2/3 menu template is gone and `_parse_trending_country_reply` is
deleted.

These tests verify:
1. The deterministic helper is gone and not importable.
2. Every call site uses `_detect_trending_country` (re-exported from
   trending_llm_runner).
3. The LLM-runner system prompt no longer instructs the model to
   emit the 1️⃣ 2️⃣ 3️⃣ digit menu.
4. The deterministic fallback templates (`trending_ask_country`,
   `trending_country_retry`) are natural language, no digit menu.
5. `_detect_country` STILL maps "1"/"2"/"3" to ISO codes (so
   customers who learned the old menu still work).
6. Every country phrasing in the user's rigorous Q&A list resolves
   to the right ISO code.
7. Country isolation in the DB query is preserved (KSA query never
   leaks UAE products) — the previously-existing
   test_trending_db_country_isolation.py still passes.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from services.customer_bot_flow.trending_llm_runner import (
    _detect_country,
)


SERVICE = (
    Path(__file__).resolve().parent.parent
    / "server" / "services" / "customer_bot_flow" / "service.py"
)
RUNNER = (
    Path(__file__).resolve().parent.parent
    / "server" / "services" / "customer_bot_flow" / "trending_llm_runner.py"
)
TEMPLATES = (
    Path(__file__).resolve().parent.parent
    / "server" / "services" / "customer_bot_flow" / "templates.py"
)


def _service() -> str:
    return SERVICE.read_text(encoding="utf-8")


def _runner() -> str:
    return RUNNER.read_text(encoding="utf-8")


def _templates() -> str:
    return TEMPLATES.read_text(encoding="utf-8")


class TestDeterministicParserDeleted:
    def test_parse_trending_country_reply_definition_gone(self) -> None:
        text = _service()
        assert "def _parse_trending_country_reply(" not in text

    def test_no_call_sites_left(self) -> None:
        text = _service()
        # Only the deletion-comment may mention the name.
        for ln in text.splitlines():
            if "_parse_trending_country_reply" in ln and not ln.lstrip().startswith("#"):
                pytest.fail(f"non-comment reference still exists: {ln!r}")

    def test_replacement_imported(self) -> None:
        from services.customer_bot_flow import service as svc

        # `_detect_trending_country` is re-exported from the runner.
        assert hasattr(svc, "_detect_trending_country")


class TestRunnerPromptNoLongerPushesDigitMenu:
    def test_prompt_does_not_demand_emoji_menu(self) -> None:
        text = _runner()
        # The old contract was: 'Offer the three countries as "1️⃣ KSA   2️⃣ UAE   3️⃣ Pakistan"'.
        # That EXACT line must be gone — otherwise the LLM keeps emitting digits.
        assert '1️⃣ KSA   2️⃣ UAE   3️⃣ Pakistan' not in text
        assert "Offer the three countries as" not in text

    def test_prompt_says_no_digit_menu(self) -> None:
        text = _runner()
        # Updated rule must explicitly forbid the digit menu.
        assert "Do **NOT** emit a \"1️⃣ 2️⃣ 3️⃣\" digit" in text or \
               "Do NOT emit a \"1️⃣ 2️⃣ 3️⃣\" digit" in text

    def test_prompt_provides_natural_example(self) -> None:
        text = _runner()
        # Concrete example helps the LLM stick to the natural phrasing.
        assert "UAE, Saudi Arabia (KSA), or Pakistan" in text


class TestTemplatesNoLongerListDigits:
    def test_ask_country_template_natural(self) -> None:
        from services.customer_bot_flow.templates import BOT_FLOW_TEMPLATES

        en = BOT_FLOW_TEMPLATES["trending_ask_country"]["english"]
        # No 1️⃣ 2️⃣ 3️⃣ emoji digits.
        for d in ("1️⃣", "2️⃣", "3️⃣"):
            assert d not in en, (
                f"trending_ask_country still contains {d!r} — the deterministic "
                "menu was supposed to be replaced with a natural-language ask"
            )
        # Must still mention all three markets.
        assert "UAE" in en and "KSA" in en and "Pakistan" in en

    def test_ask_country_template_all_languages(self) -> None:
        from services.customer_bot_flow.templates import BOT_FLOW_TEMPLATES

        for lang in ("english", "arabic", "roman_urdu"):
            tpl = BOT_FLOW_TEMPLATES["trending_ask_country"][lang]
            for d in ("1️⃣", "2️⃣", "3️⃣"):
                assert d not in tpl, f"{lang} ask-country template kept digit menu"

    def test_retry_template_natural(self) -> None:
        from services.customer_bot_flow.templates import BOT_FLOW_TEMPLATES

        en = BOT_FLOW_TEMPLATES["trending_country_retry"]["english"]
        # No "1 = KSA" mappings any more.
        assert "1 = KSA" not in en
        assert "2 = UAE" not in en
        assert "UAE" in en and "KSA" in en and "Pakistan" in en


class TestCountryDetectionStillCoversAllPhrasings:
    """The user's rigorous Q&A list. Every phrasing must resolve to the
    right ISO code through _detect_country."""

    @pytest.mark.parametrize(
        "msg,iso",
        [
            # User-listed exact phrasings
            ("UAE", "UAE"),
            ("KSA", "KSA"),
            ("Pakistan", "PK"),
            ("Saudi Arabia", "KSA"),
            ("saudi", "KSA"),
            ("United Arab Emirates", "UAE"),
            ("Emirates", "UAE"),
            # Roman Urdu / mixed
            ("UAE ke trending products", "UAE"),
            ("KSA k products", "KSA"),
            ("pakistan ke trending", "PK"),
            ("ksa ke trending products dikhao", "KSA"),
            # Short forms
            ("uae", "UAE"),
            ("ksa", "KSA"),
            ("pk", "PK"),
            # Arabic
            ("السعودية", "KSA"),
            ("الإمارات", "UAE"),
            ("باكستان", "PK"),
            # Backwards-compat digit menu (customers who learned the old contract)
            ("1", "KSA"),
            ("2", "UAE"),
            ("3", "PK"),
        ],
    )
    def test_detect_country(self, msg: str, iso: str) -> None:
        out = _detect_country(msg)
        assert out == iso, f"{msg!r} should resolve to {iso!r} (got {out!r})"

    def test_unsupported_country_returns_none(self) -> None:
        """Qatar, Oman, Egypt — explicitly NOT supported. Must not be
        coerced to one of the three."""
        for unsupported in [
            "Qatar",
            "Oman",
            "Egypt",
            "qatar mein trending products",
            "show oman trending",
        ]:
            assert _detect_country(unsupported) is None, (
                f"{unsupported!r} must not match a supported country"
            )

    def test_random_text_returns_none(self) -> None:
        for noise in ["hello", "what is dropshipping", "send me a csv", "@@@"]:
            assert _detect_country(noise) is None


class TestStepHandlerStillWorksWithRunnerOnly:
    """The deterministic step is kept as a state marker, but its handler
    is supposed to delegate fully to the LLM runner. Verify the wiring."""

    def test_handler_calls_llm_runner(self) -> None:
        text = _service()
        # The trending_awaiting_country branch must invoke _try_trending_llm.
        i = text.find('if step == "trending_awaiting_country":')
        assert i > 0
        end = text.find("\n    if step ==", i + 50)
        block = text[i:end] if end > i else text[i: i + 3000]
        assert "_try_trending_llm()" in block

    def test_handler_uses_detect_trending_country(self) -> None:
        text = _service()
        i = text.find('if step == "trending_awaiting_country":')
        end = text.find("\n    if step ==", i + 50)
        block = text[i:end] if end > i else text[i: i + 3000]
        assert "_detect_trending_country(text)" in block, (
            "the handler must use the LLM-runner-aligned _detect_country, "
            "not the deleted _parse_trending_country_reply"
        )


class TestDBCountryIsolationStillHolds:
    """The DB-backed product fetch still isolates products by country.
    This is the property the user cared about: "it should give all the
    products from the db". The existing
    test_trending_db_country_isolation.py covers the property in depth;
    here we just sanity-check the imports still wire up."""

    def test_bot_query_imports_unchanged(self) -> None:
        from services.trending_products_service.bot_query import (
            list_active_non_trending_for_country,
            list_active_trending_for_country,
        )

        # Both must still accept (db, tenant_id, country) and apply the
        # is_active + is_trending + country filter.
        import inspect

        sig = inspect.signature(list_active_trending_for_country)
        assert {"db", "tenant_id", "country"}.issubset(sig.parameters)

    def test_show_trending_for_country_still_uses_db(self) -> None:
        text = _service()
        i = text.find("def _show_trending_for_country(")
        end = text.find("\n    async def _try_trending_llm", i)
        block = text[i:end] if end > i else text[i: i + 6000]
        # DB-backed list functions must still be called.
        assert "list_active_trending_for_country(db, tenant_id, cc)" in block
        assert "list_active_non_trending_for_country(db, tenant_id, cc)" in block
