"""
Reproduce the three failures from WhatsApp transcript 2026-05-01 11:46-11:49:

  1. "meray store k aaj tak total kitnay orders hain" → "Store API error"
  2. "mera store ki pehli invoice kis date ko ayi thi" → "Store API error"
  3. "22 April se 30 April" (after CSV context) → bot said "file tayar
     karwa raha hoon" but transcript shows no document attachment.

Hits gpt-4.1 + Arabia store API live with seller_id=12630 (Urban Mart).
Prints the LLM's tool calls + the orchestrator's signals so we can see
exactly where things broke.
"""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / "server" / ".env")
except Exception:
    pass


SELLER_ID = "12630"  # Urban Mart


async def run_turn(
    msg: str,
    *,
    history_block: str = "",
    label: str,
) -> Dict[str, Any]:
    from langchain_bot.control_plane import run_one_turn
    from services.store_integration_service.client import StoreIntegrationClient

    store = StoreIntegrationClient()
    flow = {
        "verified": True,
        "seller_id": SELLER_ID,
        "step": "conversational",
        "intro_shown": True,
        "lang": "roman_urdu",
    }
    extra: Dict[str, str] = {}
    if history_block:
        extra["conversation_history"] = history_block

    print(f"\n{'─' * 72}")
    print(f"[{label}]  Q: {msg}")
    print(f"{'─' * 72}")
    t0 = time.monotonic()
    try:
        r = await run_one_turn(
            db=MagicMock(),
            tenant_id=1,
            customer_phone="03474685920",
            conversation_id=1,
            user_message=msg,
            language="roman_urdu",
            bot_flow=dict(flow),
            store_client=store,
            agent_assigned=False,
            customer_email="Urbanmart097@gmail.com",
            extra_context_blocks=extra or None,
        )
    except Exception as exc:  # noqa: BLE001
        ms = int((time.monotonic() - t0) * 1000)
        print(f"  ms={ms}  EXCEPTION {type(exc).__name__}: {exc!s}")
        return {"error": str(exc), "ms": ms}

    ms = int((time.monotonic() - t0) * 1000)
    tools = [tc.get("name") for tc in (r.tool_calls or [])]
    tool_args = [tc.get("args") for tc in (r.tool_calls or [])]
    reply = (r.reply_text or "").strip()
    print(f"  ms={ms}")
    print(f"  tools called: {tools}")
    for i, args in enumerate(tool_args):
        print(f"    arg #{i}: {args}")
    if r.csv_signal:
        print(f"  csv_signal: {r.csv_signal}")
    if r.verification_signal:
        print(f"  verification_signal: {r.verification_signal}")
    if r.fell_back:
        print(f"  fell_back: {r.fallback_reason}")
    snippet = reply[:300].replace("\n", " ")
    print(f"  REPLY: {snippet}")

    # Inspect raw tool RESULTS — this is where the "Store API error" is
    # coming from if the tool itself fails.
    if hasattr(r, "tool_results"):
        for i, tr in enumerate(r.tool_results or []):
            ok = getattr(tr, "ok", True)
            data = getattr(tr, "data", None)
            err = getattr(tr, "error", None)
            print(f"    tool result #{i}: ok={ok} error={err!r}")
            if isinstance(data, dict):
                # Print key/value summary, truncate long lists.
                summary = {
                    k: (
                        f"<list len={len(v)}>" if isinstance(v, list) and len(v) > 3
                        else v
                    )
                    for k, v in list(data.items())[:8]
                }
                print(f"    tool result #{i} data: {summary}")

    return {
        "ms": ms,
        "tools": tools,
        "args": tool_args,
        "reply": reply,
        "csv_signal": r.csv_signal,
        "fell_back": r.fell_back,
    }


async def main() -> None:
    print("Debugging transcript 2026-05-01 11:46–11:49")
    print("seller_id=12630 (Urban Mart) — verified=True")

    # ── Failure #1: total orders ────────────────────────────────────
    await run_turn(
        "meray store k aaj tak total kitnay orders hain",
        label="Total orders (Roman Urdu)",
    )
    await asyncio.sleep(15)

    # ── Failure #2: first invoice date ──────────────────────────────
    await run_turn(
        "mera store ki pehli invoice kis date ko ayi thi",
        label="First invoice date (Roman Urdu)",
    )
    await asyncio.sleep(15)

    # ── Failure #3a: CSV date-range follow-up WITH history ──────────
    history = (
        "Customer: Orders ki CSV kaise milegi?\n"
        "Bot: Aap ko orders ki CSV file chahiye? Bas mujhe yahan par "
        "request bhej dein, jaise \"last month ki orders CSV bhejo\" "
        "ya \"22 April se 30 April tak ki orders ki CSV chahiye\", "
        "main file generate karwa dunga.\n"
    )
    await run_turn(
        "22 April se 30 April",
        history_block=history,
        label="CSV date range (WITH history)",
    )
    await asyncio.sleep(15)

    # ── Failure #3b: SAME message but WITHOUT history. This is the
    # likely production case — if the conversation history isn't
    # being loaded into the orchestrator (Redis was unavailable in
    # this run), the LLM sees a bare date range with no prior CSV
    # context and might not call generate_csv at all.
    await run_turn(
        "22 April se 30 April",
        label="CSV date range (NO history — likely prod case)",
    )


if __name__ == "__main__":
    asyncio.run(main())
