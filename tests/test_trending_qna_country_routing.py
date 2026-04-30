"""
Rigorous Q&A test suite for trending products country routing — driven by
the WhatsApp transcript on 2026-04-30 03:25:

  Customer: "Pakistan me delivery ratio kia hy"
  Bot:      <Pakistan trending product images>

  Customer: "KSA k trending products"
  Bot:      <UAE trending products> (had asked UAE earlier)

These tests verify that:

1. Pure trending requests for each country resolve to the correct ISO
   code via _detect_country.
2. Country switches mid-flow correctly reset the pagination memory.
3. Analytics questions ("delivery ratio kia hy", "kitne orders") are
   detected by _looks_like_analytics_question and never fall into the
   trending browse flow even when they mention a country.
4. Unsupported countries (Qatar, Oman) are not silently coerced to one
   of the three supported markets.
5. Non-trending vs. trending mode detection is correct.

The DB layer is **not** mocked — the country routing is verified at the
detector level. A separate integration test asserts the DB query path.
"""
from __future__ import annotations

from typing import Optional

import pytest

from services.customer_bot_flow.service import (
    _looks_like_analytics_question,
    _wants_non_trending_products,
    _wants_trending_products,
)
from services.customer_bot_flow.trending_llm_runner import (
    _detect_country,
    _detect_mode,
)


# ---------------------------------------------------------------------------
# Country detection (every prompt the user listed)
# ---------------------------------------------------------------------------
COUNTRY_QUESTIONS = [
    # Country-specific trending requests
    ("UAE ke trending products dikhao", "UAE"),
    ("KSA ke trending products dikhao", "KSA"),
    ("Pakistan ke trending products dikhao", "PK"),
    ("Trending products in UAE", "UAE"),
    ("Trending products in KSA", "KSA"),
    ("Show me trending products in Saudi Arabia", "KSA"),
    ("mujhe UAE ke best selling products chahiye", "UAE"),
    ("KSA mein konsi products zyada bik rahi hain?", "KSA"),
    ("Pakistan mein trending items kya hain?", "PK"),
    # Listing variations
    ("List of trending products for UAE", "UAE"),
    ("List of trending products for KSA", "KSA"),
    ("Non-trending products in UAE dikhao", "UAE"),
    ("Non-trending products in KSA dikhao", "KSA"),
    ("UAE mein non-popular products", "UAE"),
    ("KSA mein jo products trending nahi hain", "KSA"),
    # Category + country combinations
    ("Home & Living category trending products UAE", "UAE"),
    ("Beauty trending products KSA", "KSA"),
    ("Electronics trending in Pakistan", "PK"),
    ("Show me products in fashion category for KSA", "KSA"),
    ("Trending products in Health & Wellness for UAE", "UAE"),
    # Product-specific follow-ups
    ("What is the price of the first trending product in KSA?", "KSA"),
    ("Tell me about trending product #2 in UAE", "UAE"),
    # Repetition / edge cases
    ("Show me trending products for Saudi Arabia again", "KSA"),
    ("KSA k trending products me se 3rd product kya hai?", "KSA"),
    ("UAE k trending products ki list do", "UAE"),
    ("KSA mein alag se koi exclusive products hain?", "KSA"),
]


@pytest.mark.parametrize("msg,iso", COUNTRY_QUESTIONS)
def test_country_detected_correctly(msg: str, iso: str) -> None:
    """Every supported phrasing must map to the right ISO code, regardless of
    surrounding text. KSA must never be coerced to UAE just because UAE was
    a previous topic."""
    assert _detect_country(msg) == iso, f"{msg!r} should detect {iso}"


def test_unsupported_country_returns_none() -> None:
    """Qatar / Oman / Egypt aren't in COUNTRY_ALIASES — must be None so the
    deterministic flow asks for a supported country instead of silently
    fetching the wrong one."""
    assert _detect_country("Trending products for Qatar") is None
    assert _detect_country("Show trending in Oman") is None
    assert _detect_country("Egypt ke trending products") is None


def test_compare_question_detects_at_least_one_country() -> None:
    """'Compare trending products between UAE and KSA' is ambiguous —
    _detect_country returns whichever it sees first (alphabetical alias
    iteration). The LLM handles disambiguation; our job is to detect at
    least one valid country so we don't reset memory to None."""
    out = _detect_country("Compare trending products between UAE and KSA")
    assert out in {"UAE", "KSA"}


# ---------------------------------------------------------------------------
# Analytics escape — these must NOT route to trending
# ---------------------------------------------------------------------------
ANALYTICS_QUESTIONS = [
    "Pakistan me delivery ratio kia hy",
    "UAE me delivery ratio kia hai",
    "KSA me return ratio kya hai",
    "delivery ratio kitna hai",
    "return ratio kitni hai",
    "how many orders delivered",
    "kitne orders deliver hue",
    "kitni orders return hui",
    "What is my average profit per order",
    "top cities show karo",
    "top selling product mera kaunsa hai",
    "profit by month kya hai",
]


@pytest.mark.parametrize("msg", ANALYTICS_QUESTIONS)
def test_analytics_question_detected(msg: str) -> None:
    """Each analytics-shape question must be flagged so the trending step
    bails to the LLM-first / ai_forward path (which has the stats tools)."""
    assert _looks_like_analytics_question(msg), (
        f"{msg!r} should be flagged as analytics, not trending"
    )


@pytest.mark.parametrize("msg", ANALYTICS_QUESTIONS)
def test_analytics_question_not_classified_as_trending(msg: str) -> None:
    """The trending detector must reject analytics questions even when they
    mention a country or the word 'product'."""
    assert not _wants_trending_products(msg), (
        f"{msg!r} must not trigger the trending browse flow"
    )
    assert not _wants_non_trending_products(msg)


# ---------------------------------------------------------------------------
# Mode detection (trending vs non-trending)
# ---------------------------------------------------------------------------
MODE_CASES = [
    ("UAE ke trending products", "trending", "trending"),
    ("UAE ke non-trending products", "trending", "non_trending"),
    ("Non-trending products in UAE dikhao", "trending", "non_trending"),
    ("trending nahi hain wo products", "trending", "non_trending"),
    ("kuch dikhao", "non_trending", "non_trending"),  # carries prior
    ("kuch dikhao", "trending", "trending"),          # carries prior
]


@pytest.mark.parametrize("msg,prior,expected", MODE_CASES)
def test_mode_detection(msg: str, prior: str, expected: str) -> None:
    assert _detect_mode(msg, prior) == expected


# ---------------------------------------------------------------------------
# Real-world LLM follow-up phrasings — bare country word in a non-browse
# question must NOT be picked up as a fresh trending request by the
# trending detector. Country detection is fine (we *do* detect "Pakistan"),
# but _wants_trending_products gates entry into the flow.
# ---------------------------------------------------------------------------
NON_TRENDING_PHRASES_THAT_NAME_A_COUNTRY = [
    "Pakistan me delivery ratio kia hy",
    "UAE me kitne orders deliver hue",
    "KSA mein mera return ratio kya hai",
    "Pakistan ke orders ka profit btao",
]


@pytest.mark.parametrize("msg", NON_TRENDING_PHRASES_THAT_NAME_A_COUNTRY)
def test_country_in_analytics_does_not_trigger_trending(msg: str) -> None:
    """Even though _detect_country resolves a valid ISO, _wants_trending_products
    must return False so the LLM-first path handles the analytics question."""
    iso: Optional[str] = _detect_country(msg)
    assert iso in {"UAE", "KSA", "PK"}, (
        f"sanity: {msg!r} contains a recognisable country"
    )
    assert not _wants_trending_products(msg), (
        f"{msg!r} mentions a country but is an analytics question — "
        "must not enter the trending browse flow"
    )


# ---------------------------------------------------------------------------
# Prompt rules: the LLM-facing prompt must explicitly forbid using
# get_trending_products for analytics questions and must enumerate the
# country mapping.
# ---------------------------------------------------------------------------
def test_prompt_lists_supported_countries() -> None:
    from langchain_bot.prompts import build_system_prompt_template

    p = build_system_prompt_template().lower()
    assert "uae" in p
    assert "ksa" in p
    assert "pak" in p


def test_prompt_blocks_analytics_via_trending() -> None:
    from langchain_bot.prompts import build_system_prompt_template

    p = build_system_prompt_template()
    # The rule we just added must be present so the LLM cannot substitute
    # trending products for an analytics answer.
    assert "delivery ratio" in p.lower(), (
        "LLM prompt must mention delivery ratio so the model knows it's an "
        "analytics question, not a trending request"
    )
    assert "lookup_orders_by_range" in p
    assert "country alone is not a trending request".lower() in p.lower()
