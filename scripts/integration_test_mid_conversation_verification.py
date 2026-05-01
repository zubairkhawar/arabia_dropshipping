"""
Mid-conversation verification trigger test.

Simulates a real multi-turn conversation:
  Turn 1: customer asks about Arabia services         → KB / LLM-first answers
  Turn 2: customer asks about shipping rates          → KB / LLM-first answers
  Turn 3: customer asks about payment day             → KB / LLM-first answers
  Turn 4: customer asks "where is my order #177089"   → BOOTSTRAP must fire,
                                                         step → existing_awaiting_email,
                                                         bot asks for email
  Turn 5: customer asks "invoice btao April ki"       → BOOTSTRAP must fire
  Turn 6: customer asks "haan verify kar do"          → BOOTSTRAP must fire

The script tests two things:
  A) The deterministic bootstrap regex: every order/account turn
     above MUST trigger `needs_verification_bootstrap=True`.
  B) The LLM-first orchestrator: service-question turns get a real
     KB-grounded answer (no fall-back, sensible reply).

Without the bootstrap, the LLM might (per the 2026-05-01 transcript)
ask a clarifying question or hallucinate a verification result on
turn 4 — both are regressions this script catches.
"""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path
from typing import Any, Dict, Tuple
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / "server" / ".env")
except Exception:
    pass

PACE = 12.0  # 30K TPM gpt-4.1 — keep below ceiling


# ─────────────────────────────────────────────────────────────────────────────
# A) Bootstrap regex layer — pure-Python, no LLM, fast.
# ─────────────────────────────────────────────────────────────────────────────


def test_bootstrap_layer() -> Tuple[int, int]:
    """Mirror the production gate logic for each turn and check the
    bootstrap-trigger expectation."""
    from services.customer_bot_flow.service import (
        _extract_standalone_email,
        _is_explicit_verification_consent,
        _is_likely_order_id_only,
        _looks_like_account_question,
        _looks_like_invoice_for_order,
        _looks_like_order_status_question,
    )

    def bootstrap(msg: str, *, verified: bool = False) -> bool:
        """Reproduce the production gate: only fires on step=conversational
        + unverified + any of the order/account intent regexes."""
        if verified:
            return False
        return (
            _looks_like_order_status_question(msg)
            or _is_likely_order_id_only(msg)
            or _looks_like_account_question(msg)
            or _looks_like_invoice_for_order(msg)
            or _is_explicit_verification_consent(msg)
            or bool(_extract_standalone_email(msg))
        )

    print("─" * 72)
    print("A) Bootstrap-regex layer (pure Python, no LLM)")
    print("─" * 72)

    # Each tuple: (label, message, expected_trigger).
    cases = [
        # ── KB / service questions: bootstrap MUST stay quiet ──
        ("service-q (English)",   "what is dropshipping",                  False),
        ("service-q (English #2)", "what are arabia's main services",      False),
        ("service-q (Roman Urdu)", "fulfillment service kya hai",          False),
        ("service-q (rates)",     "shipping rates kya hain",               False),
        ("service-q (payment day)", "payment kab hoti hai",                False),
        ("service-q (comparison)", "arabia dropship zambeel say kesay behtar hai", False),
        ("greeting",              "hi there",                              False),

        # ── Order / account intent: bootstrap MUST fire ──
        ("order-status (English)", "where is my order #177089",            True),
        ("order-status (Roman Urdu)", "mera order ki status btao",         True),
        ("order-status (Pakistani)", "mujhy orders k baray mein jnaa hai", True),
        ("invoice (Roman Urdu)",   "invoice btao April ki",                True),
        ("invoice (English)",      "show me my invoices",                  True),
        ("invoice (Arabic)",       "أين فاتورتي",                          True),
        ("bare order id",          "157955",                               True),
        ("explicit consent",       "haan verify kar do",                   True),
        ("explicit consent #2",    "han kro verification",                 True),
        ("bare email",             "Urbanmart097@gmail.com",               True),
    ]

    passed = 0
    for label, msg, expected in cases:
        actual = bootstrap(msg)
        ok = actual == expected
        if ok:
            passed += 1
        marker = "✅" if ok else "❌"
        print(f"  {marker} [{label:<28s}] {msg!r:<55s} → bootstrap={actual} (expected {expected})")
    print(f"\n  Bootstrap layer: {passed}/{len(cases)} passed")
    return passed, len(cases)


# ─────────────────────────────────────────────────────────────────────────────
# B) LLM-first orchestrator — for the service-question turns, verify the
#    LLM produces a real KB-grounded answer.
# ─────────────────────────────────────────────────────────────────────────────


async def test_llm_first_layer() -> Tuple[int, int]:
    from langchain_bot.control_plane import run_one_turn
    from services.store_integration_service.client import StoreIntegrationClient

    store = StoreIntegrationClient()

    # Service-question turns where bootstrap stays quiet — LLM-first runs.
    cases = [
        ("service-q (services list)", "what are arabia's main services", "english", "dropshipping"),
        ("service-q (shipping)", "what are the shipping rates for UAE", "english", "AED"),
        ("service-q (payment day Urdu)", "payment kab hoti hai", "roman_urdu", "wednesday"),
        ("service-q (zambeel comparison)", "arabia dropship zambeel say kesay behtar hai", "roman_urdu", "arabia"),
    ]

    print("─" * 72)
    print("B) LLM-first orchestrator (for service questions; ~12s each)")
    print("─" * 72)

    flow = {
        "verified": False,
        "seller_id": None,
        "step": "conversational",
        "intro_shown": True,
        "customer_kind": None,
        "lang": "english",
    }

    passed = 0
    for label, msg, lang, expected_substring in cases:
        flow["lang"] = lang
        t0 = time.monotonic()
        try:
            r = await run_one_turn(
                db=MagicMock(),
                tenant_id=1,
                customer_phone="+923000000000",
                conversation_id=1,
                user_message=msg,
                language=lang,
                bot_flow=dict(flow),
                store_client=store,
                agent_assigned=False,
                customer_email=None,
            )
            ms = int((time.monotonic() - t0) * 1000)
            reply = (r.reply_text or "").strip()
            fell = r.fell_back
        except Exception as exc:  # noqa: BLE001
            ms = int((time.monotonic() - t0) * 1000)
            reply = f"[ERROR] {type(exc).__name__}: {exc!s}"[:200]
            fell = True

        # Check: reply must NOT be a verification-asking line, must NOT be
        # "Mujhe aapke account mein yeh order nahi mila" (the bug from
        # 2026-04-30 21:06), and SHOULD include the expected substring.
        ok_kb = expected_substring.lower() in reply.lower()
        ok_no_verify_drift = not any(
            bad in reply for bad in (
                "verification kar leta hoon",
                "verify you first",
                "yeh order nahi mila",
                "verification process start ho gaya",
            )
        )
        ok = ok_kb and ok_no_verify_drift and not fell

        if ok:
            passed += 1
        marker = "✅" if ok else "❌"
        print(f"\n  {marker} [{label}]  ms={ms}{'  [FB]' if fell else ''}")
        print(f"     Q: {msg}")
        snippet = reply[:200].replace("\n", " ")
        print(f"     A: {snippet}")
        if not ok:
            if not ok_kb:
                print(f"     ✗ expected substring {expected_substring!r} not in reply")
            if not ok_no_verify_drift:
                print("     ✗ reply drifted into verification dialogue (should NOT for service questions)")

        await asyncio.sleep(PACE)

    print(f"\n  LLM-first layer: {passed}/{len(cases)} passed")
    return passed, len(cases)


# ─────────────────────────────────────────────────────────────────────────────
# C) End-to-end conversation flow simulation. We ASSERT that on order
#    turns the bootstrap would short-circuit BEFORE the LLM runs (so the
#    deterministic state machine owns the verification entry).
# ─────────────────────────────────────────────────────────────────────────────


def test_conversation_flow_simulation() -> Tuple[int, int]:
    """Walk through a full conversation timeline. At each turn, assert
    whether the bootstrap layer would have fired — which determines
    whether the LLM-first path runs (False = run LLM) or the
    deterministic verification step transition runs (True)."""
    from services.customer_bot_flow.service import (
        _extract_standalone_email,
        _is_explicit_verification_consent,
        _is_likely_order_id_only,
        _looks_like_account_question,
        _looks_like_invoice_for_order,
        _looks_like_order_status_question,
    )

    def bootstrap(msg: str) -> bool:
        return (
            _looks_like_order_status_question(msg)
            or _is_likely_order_id_only(msg)
            or _looks_like_account_question(msg)
            or _looks_like_invoice_for_order(msg)
            or _is_explicit_verification_consent(msg)
            or bool(_extract_standalone_email(msg))
        )

    print("─" * 72)
    print("C) Conversation timeline — verify routing per turn")
    print("─" * 72)

    timeline = [
        ("hi",                                                   "LLM",           "greeting → conversational LLM reply"),
        ("what is dropshipping?",                                "LLM",           "service Q → KB"),
        ("what are arabia's main services",                      "LLM",           "service Q → KB"),
        ("how do payments work",                                 "LLM",           "service Q → KB"),
        ("arabia dropship zambeel say kesay behtar hai",         "LLM",           "comparison Q → KB"),
        ("mujhy orders k baray mein jnaa hai",                   "BOOTSTRAP",     "ORDER intent — verify entry"),
        # After the bootstrap fires, the customer is in step=existing_awaiting_email.
        # The bootstrap test only applies at step=conversational, but logically
        # the next several turns are inside the verification state machine.
        # We just verify the trigger semantics here.
        ("show me my invoices",                                  "BOOTSTRAP",     "INVOICE intent — verify entry"),
        ("haan verify kar do",                                   "BOOTSTRAP",     "explicit consent"),
        ("Urbanmart097@gmail.com",                               "BOOTSTRAP",     "bare email"),
        ("157955",                                               "BOOTSTRAP",     "bare order id"),
    ]

    passed = 0
    for msg, expected_route, why in timeline:
        actual = "BOOTSTRAP" if bootstrap(msg) else "LLM"
        ok = actual == expected_route
        if ok:
            passed += 1
        marker = "✅" if ok else "❌"
        print(f"  {marker} {msg!r:<55s} → {actual:<10s} ({why})")
    print(f"\n  Conversation routing: {passed}/{len(timeline)} correctly routed")
    return passed, len(timeline)


async def main() -> None:
    print("Mid-conversation verification trigger — live integration test")
    print()

    # A: Pure-Python bootstrap — fast.
    a_pass, a_total = test_bootstrap_layer()

    # C: Pure-Python conversation timeline — fast.
    c_pass, c_total = test_conversation_flow_simulation()

    # B: Live LLM call — slow + costly (gpt-4.1 with KB).
    b_pass, b_total = await test_llm_first_layer()

    print()
    print("═" * 72)
    print("Summary")
    print("═" * 72)
    print(f"  A. Bootstrap-regex layer:     {a_pass}/{a_total}")
    print(f"  B. LLM-first orchestrator:    {b_pass}/{b_total}")
    print(f"  C. Conversation routing:      {c_pass}/{c_total}")
    total = a_pass + b_pass + c_pass
    grand = a_total + b_total + c_total
    print(f"  ────────────────────────────")
    print(f"  Total:                        {total}/{grand}")


if __name__ == "__main__":
    asyncio.run(main())
