"""
End-to-end integration test for the five LLM migrations done this session:

  1. CSV intent → generate_csv tool
  2. Customer-type menu deletion → LLM routes implicitly
  3. Trending country picker → LLM asks naturally
  4. Pagination short-circuit deletion → runner handles "aur dikhao"
  5. Verification bootstrap → LLM calls start_verification

Sends real messages through `langchain_bot.control_plane.run_one_turn`
(the LLM-first orchestrator) and prints the bot's response, the tools
the LLM called, and whether each migration's expected behaviour fired.

This is a one-off live runner. It hits OpenAI (so costs $0.01–0.10
per run) and the Arabia store API. Run from server/ with .env loaded.
"""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / "server" / ".env")
except Exception:
    pass


SELLER_ID = "12630"  # Urban Mart
# 30K TPM limit on gpt-4.1; one turn here uses ~3K-5K tokens, so we pace
# at 12s to stay well under and ride out short bursts.
PACE_SECONDS = 12.0


# ─────────────────────────────────────────────────────────────────────────────
# Test scenarios — each entry is (label, message, expected_signals).
# expected_signals is a dict of properties to assert on the orchestrator
# result; missing properties mean "don't care".
#
# Possible signals:
#   - tool_called: tool name we expect the LLM to invoke
#   - csv_signal: True if generate_csv tool should fire
#   - verification_signal: True if start_verification should fire
#   - trending_signal: True if get_trending_products should fire
#   - reply_contains: substring expected in the reply text (case-insensitive)
#   - reply_not_contains: substring that must NOT appear in the reply
# ─────────────────────────────────────────────────────────────────────────────
SCENARIOS: List[Tuple[str, str, str, Dict[str, Any], Dict[str, Any]]] = [
    # ──── Verification bootstrap migration ────────────────────────────────
    # An unverified customer asking about an order MUST trigger
    # start_verification (no regex safety net any more).
    (
        "verify-bootstrap (English)",
        "where is my order #177089",
        "english",
        {"verified": False, "seller_id": None, "customer_kind": None},
        {"verification_signal": True, "tool_called": "start_verification"},
    ),
    (
        "verify-bootstrap (Roman Urdu)",
        "mera order ki status btao",
        "roman_urdu",
        {"verified": False, "seller_id": None, "customer_kind": None},
        {"verification_signal": True, "tool_called": "start_verification"},
    ),
    (
        "verify-bootstrap (bare order id)",
        "157955",
        "english",
        {"verified": False, "seller_id": None, "customer_kind": None},
        {"verification_signal": True, "tool_called": "start_verification"},
    ),
    (
        "verify-bootstrap (Arabic invoice)",
        "أين فاتورتي",
        "arabic",
        {"verified": False, "seller_id": None, "customer_kind": None},
        {"verification_signal": True, "tool_called": "start_verification"},
    ),

    # ──── New-customer / dropshipping question — should NOT verify ────────
    (
        "new-customer FAQ (no verify)",
        "what is dropshipping",
        "english",
        {"verified": False, "seller_id": None, "customer_kind": None},
        # No verification signal expected. KB / search_kb is fine.
        {"verification_signal": False},
    ),
    (
        "fulfillment FAQ (Roman Urdu)",
        "fulfillment service kya hai",
        "roman_urdu",
        {"verified": False, "seller_id": None, "customer_kind": None},
        {"verification_signal": False},
    ),

    # ──── CSV migration ────────────────────────────────────────────────────
    # Verified customer asks for CSV — LLM should call generate_csv.
    (
        "csv-orders (English)",
        "send me a csv of my orders for the last month",
        "english",
        {"verified": True, "seller_id": SELLER_ID, "customer_kind": "existing"},
        {"csv_signal": True, "tool_called": "generate_csv"},
    ),
    (
        "csv-orders (Roman Urdu)",
        "saare orders ki csv bhejo",
        "roman_urdu",
        {"verified": True, "seller_id": SELLER_ID, "customer_kind": "existing"},
        {"csv_signal": True, "tool_called": "generate_csv"},
    ),
    (
        "csv-invoice (specific date)",
        "invoice CSV for 22 April 2026",
        "english",
        {"verified": True, "seller_id": SELLER_ID, "customer_kind": "existing"},
        {"csv_signal": True, "tool_called": "generate_csv"},
    ),
    # HOW question — must NOT trigger generate_csv.
    (
        "csv-how-question",
        "How do I get a CSV of my orders?",
        "english",
        {"verified": True, "seller_id": SELLER_ID, "customer_kind": "existing"},
        {"csv_signal": False},
    ),

    # ──── Trending country picker ─────────────────────────────────────────
    # Customer asks for trending without naming a country → LLM should
    # call get_trending_products with the right country (from message)
    # OR ask which country naturally (no 1/2/3 menu).
    (
        "trending (no country named)",
        "show me trending products",
        "english",
        {"verified": True, "seller_id": SELLER_ID, "customer_kind": "existing"},
        # Either: signal fires (LLM picked default), or LLM asks for country.
        # Either way: no "1️⃣" / "2️⃣" / "3️⃣" digits.
        {"reply_not_contains": "1️⃣"},
    ),
    (
        "trending KSA (inline)",
        "KSA ke trending products dikhao",
        "roman_urdu",
        {"verified": True, "seller_id": SELLER_ID, "customer_kind": "existing"},
        {"trending_signal": True, "tool_called": "get_trending_products"},
    ),
    (
        "winning products (slang)",
        "winning products dikhao Pakistan ke",
        "roman_urdu",
        {"verified": True, "seller_id": SELLER_ID, "customer_kind": "existing"},
        {"trending_signal": True, "tool_called": "get_trending_products"},
    ),

    # ──── Analytics question (NOT trending) ────────────────────────────────
    # Pakistan + delivery ratio — must not be trending.
    (
        "analytics (delivery ratio with country)",
        "Pakistan me delivery ratio kya hai",
        "roman_urdu",
        {"verified": True, "seller_id": SELLER_ID, "customer_kind": "existing"},
        # No trending; should call lookup_orders_by_range or get_total_orders.
        {"trending_signal": False},
    ),

    # ──── KB question ───────────────────────────────────────────────────────
    (
        "kb (services list)",
        "what are arabia's main services",
        "english",
        {"verified": False, "seller_id": None, "customer_kind": None},
        {"reply_contains": "dropshipping"},
    ),
]


# ─────────────────────────────────────────────────────────────────────────────
# Runner
# ─────────────────────────────────────────────────────────────────────────────


def _check(label: str, ok: bool) -> str:
    return f"  {'✅' if ok else '❌'} {label}"


async def run_one(
    label: str,
    msg: str,
    language: str,
    flow: Dict[str, Any],
    expectations: Dict[str, Any],
) -> Tuple[str, bool, List[str]]:
    """Run one scenario; return (label, passed, lines_to_print)."""

    from langchain_bot.control_plane import run_one_turn
    from services.store_integration_service.client import StoreIntegrationClient

    store = StoreIntegrationClient()
    t0 = time.monotonic()
    try:
        r = await run_one_turn(
            db=MagicMock(),
            tenant_id=1,
            customer_phone="03474685920",
            conversation_id=1,
            user_message=msg,
            language=language,
            bot_flow=dict(flow),
            store_client=store,
            agent_assigned=False,
            customer_email="Urbanmart097@gmail.com",
        )
    except Exception as exc:  # noqa: BLE001
        ms = int((time.monotonic() - t0) * 1000)
        return (
            label,
            False,
            [
                f"[{label}]  ms={ms}  ❌ EXCEPTION",
                f"  Q: {msg}",
                f"  ERR: {type(exc).__name__}: {exc!s}"[:200],
            ],
        )

    ms = int((time.monotonic() - t0) * 1000)
    reply = (r.reply_text or "").strip()
    tools_called = [tc.get("name") for tc in (r.tool_calls or [])]
    csv_sig = r.csv_signal is not None
    ver_sig = r.verification_signal is not None
    trd_sig = r.trending_signal is not None
    fell = r.fell_back

    lines = [
        f"[{label}]  ms={ms}  tools={tools_called}{'  [FB]' if fell else ''}",
        f"  Q: {msg}",
    ]
    if reply:
        snippet = reply[:240].replace("\n", " ")
        lines.append(f"  A: {snippet}")
    else:
        lines.append("  A: (empty)")
    if csv_sig:
        lines.append(f"  csv_signal: {r.csv_signal}")
    if ver_sig:
        lines.append(f"  verification_signal: {r.verification_signal}")
    if trd_sig:
        lines.append(f"  trending_signal: {r.trending_signal}")

    # Run expectations
    passed = True
    if "tool_called" in expectations:
        want = expectations["tool_called"]
        ok = want in tools_called
        passed = passed and ok
        lines.append(_check(f"tool_called == {want!r}", ok))
    if "csv_signal" in expectations:
        ok = csv_sig == bool(expectations["csv_signal"])
        passed = passed and ok
        lines.append(_check(f"csv_signal == {bool(expectations['csv_signal'])}", ok))
    if "verification_signal" in expectations:
        ok = ver_sig == bool(expectations["verification_signal"])
        passed = passed and ok
        lines.append(
            _check(
                f"verification_signal == {bool(expectations['verification_signal'])}",
                ok,
            )
        )
    if "trending_signal" in expectations:
        ok = trd_sig == bool(expectations["trending_signal"])
        passed = passed and ok
        lines.append(
            _check(f"trending_signal == {bool(expectations['trending_signal'])}", ok)
        )
    if "reply_contains" in expectations:
        needle = str(expectations["reply_contains"]).lower()
        ok = needle in reply.lower()
        passed = passed and ok
        lines.append(_check(f"reply contains {needle!r}", ok))
    if "reply_not_contains" in expectations:
        needle = str(expectations["reply_not_contains"])
        ok = needle not in reply
        passed = passed and ok
        lines.append(_check(f"reply does NOT contain {needle!r}", ok))

    return (label, passed, lines)


async def main() -> None:
    print("Migration integration test")
    print("─" * 72)
    print(
        "Sending real messages through run_one_turn (LLM-first orchestrator). "
        "This will hit OpenAI + Arabia store API."
    )
    print()

    results: List[Tuple[str, bool]] = []
    for label, msg, lang, flow, expectations in SCENARIOS:
        try:
            scenario_label, passed, lines = await run_one(
                label, msg, lang, flow, expectations
            )
        except Exception as exc:  # noqa: BLE001
            scenario_label, passed = label, False
            lines = [f"[{label}]  ❌ FATAL: {type(exc).__name__}: {exc!s}"]
        for ln in lines:
            print(ln)
        print()
        results.append((scenario_label, passed))
        await asyncio.sleep(PACE_SECONDS)

    # Summary
    print("─" * 72)
    print("Summary:")
    passed_n = sum(1 for _, ok in results if ok)
    for lbl, ok in results:
        print(f"  {'✅' if ok else '❌'} {lbl}")
    print(f"\n{passed_n}/{len(results)} scenarios passed.")


if __name__ == "__main__":
    asyncio.run(main())
