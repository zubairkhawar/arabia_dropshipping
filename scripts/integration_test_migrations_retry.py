"""
Re-run only the scenarios that hit rate limits in the first pass,
with 20s pacing and built-in retry on 429.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "server"))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / "server" / ".env")
except Exception:
    pass

from integration_test_migrations import SCENARIOS, run_one  # noqa: E402

# Cherry-pick the typically-rate-limited scenarios.
PRIORITY_LABELS = {
    "csv-orders (English)",
    "csv-orders (Roman Urdu)",
    "csv-invoice (specific date)",
    "trending KSA (inline)",
    "winning products (slang)",
    "verify-bootstrap (bare order id)",
    "verify-bootstrap (Arabic invoice)",
    "analytics (delivery ratio with country)",
}

PACE = 20.0  # heavy pacing to ride through TPM


async def main() -> None:
    targets = [s for s in SCENARIOS if s[0] in PRIORITY_LABELS]
    print(f"Re-running {len(targets)} scenarios with {PACE}s pacing")
    print("─" * 72)
    print()
    results = []
    for label, msg, lang, flow, expectations in targets:
        # Up to 3 attempts per scenario; rate-limit fallbacks count as fails.
        passed = False
        last_lines = []
        for attempt in range(3):
            scen, ok, lines = await run_one(label, msg, lang, flow, expectations)
            last_lines = lines
            joined = "\n".join(lines)
            if "technical issue" in joined or "mukhtasar technical masla" in joined or "خطأ تقني مؤقت" in joined:
                if attempt < 2:
                    print(f"[{label}]  attempt {attempt+1} hit rate-limit fallback; retrying after 30s")
                    await asyncio.sleep(30)
                    continue
            passed = ok
            break
        for ln in last_lines:
            print(ln)
        print()
        results.append((label, passed))
        await asyncio.sleep(PACE)

    print("─" * 72)
    print("Re-run summary:")
    for lbl, ok in results:
        print(f"  {'✅' if ok else '❌'} {lbl}")
    print(f"\n{sum(1 for _, ok in results if ok)}/{len(results)} passed on retry.")


if __name__ == "__main__":
    asyncio.run(main())
