"""
Run a curated 200-question battery through the LLM-first orchestrator and
record every reply to a Markdown report.

Each question is sent to ``control_plane.run_one_turn`` with a verified
ToolContext (Urban Mart, seller_id=12630). The script captures:
  - the customer message
  - the bot's reply text
  - which tools the LLM called
  - latency in ms
  - any error / fallback signal

Output: docs/200_question_report.md (overwritten on each run)

Run from repo root:
    python3 scripts/run_200_questions.py
"""
from __future__ import annotations

import asyncio
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Tuple
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / "server" / ".env")
except Exception:
    pass


SELLER_ID = "12630"


# ─────────────────────────────────────────────────────────────────────────────
# 200 questions, grouped by topic
# ─────────────────────────────────────────────────────────────────────────────
QUESTIONS: List[Tuple[str, List[str]]] = [
    ("Dropshipping (general)", [
        "What is dropshipping?",
        "How does dropshipping work with Arabia?",
        "Can I start dropshipping without inventory?",
        "Do I need to buy products upfront?",
        "What are the profit margins in dropshipping?",
        "Is dropshipping legal in UAE?",
        "Can I sell on my own Shopify store?",
        "How do I list products from Arabia on my site?",
        "Do you offer product training?",
        "What is the minimum order value?",
        "Can I try dropshipping for free?",
        "Do you have a starter guide?",
        "How long before I see profit?",
        "Can I switch from another dropshipping platform?",
        "Do you integrate with WooCommerce?",
        "What is the success rate of dropshippers on Arabia?",
        "How do I handle returns as a dropshipper?",
        "Are there any hidden fees?",
        "Can I sell branded products?",
        "What kind of products sell best?",
    ]),
    ("Fulfillment", [
        "What is fulfillment service?",
        "How much does fulfillment cost?",
        "What is the per-order fulfillment fee in UAE?",
        "Do you offer fulfillment in KSA?",
        "Is warehousing free?",
        "How do I send my inventory to your warehouse?",
        "Can I use my own packaging?",
        "What is the fulfillment process?",
        "How long does fulfillment take?",
        "Do you integrate with my store for fulfillment?",
        "Can I track fulfillment status?",
        "What happens if an item is out of stock?",
        "Do you handle returns for fulfillment?",
        "What is the address of your UAE warehouse?",
        "Can I visit the warehouse?",
        "Is there a minimum monthly volume for fulfillment?",
        "How do I get started with fulfillment?",
        "Do you offer cross-border fulfillment?",
        "What is the difference between fulfillment and dropshipping?",
        "Can I send my own products to be fulfilled?",
    ]),
    ("3PL Courier Services", [
        "What is 3PL service?",
        "How do I get a 3PL courier account?",
        "What are your 3PL rates?",
        "Do you offer discounted shipping rates?",
        "Which courier partners do you use?",
        "Can I use 3PL for my existing inventory?",
        "How to apply for 3PL?",
        "What documents are needed for 3PL?",
        "Is there a setup fee for 3PL?",
        "Do you handle COD for 3PL?",
        "Can I get real-time tracking for 3PL shipments?",
        "What is the delivery time for 3PL?",
        "Does 3PL include labeling and packing?",
        "Can I use my own courier account?",
        "What is the minimum order volume for 3PL?",
        "Do you offer 3PL in Pakistan?",
        "How do I check my 3PL balance?",
        "What happens if a package is lost?",
        "Can I integrate 3PL with my ERP?",
        "Is 3PL cheaper than self-shipping?",
    ]),
    ("WhatsApp Order Confirmation", [
        "What is WhatsApp order confirmation?",
        "How many confirmation attempts do you make?",
        "What happens if the customer doesn't answer?",
        "Can I see the confirmation proof?",
        "How much does the service cost in UAE?",
        "How much in KSA?",
        "Is there a charge for cancelled orders?",
        "Do you offer confirmation in Pakistan?",
        "How do I view the screenshot proof?",
        "Can I request a custom confirmation message?",
        "What if the customer confirms after the third attempt?",
        "Can I cancel confirmation after order placed?",
        "Is the confirmation done by phone call?",
        "How long does each attempt take?",
        "Do you share the customer's reply?",
        "Can I test the confirmation flow?",
        "Is this service mandatory for all orders?",
        "Can I opt out of WhatsApp confirmation?",
        "What if the customer's WhatsApp is not working?",
        "How is the proof stored?",
    ]),
    ("Agency Partnership Program", [
        "What is the agency partnership program?",
        "How do I become an agency partner?",
        "How much commission do I earn?",
        "Is there a limit on sellers I can onboard?",
        "How do I track my commissions?",
        "How are commissions paid?",
        "Do I get a unique onboarding link?",
        "Can I onboard sellers from any country?",
        "Is there a registration fee?",
        "What is the difference between agency and affiliate?",
        "How do I access the agency dashboard?",
        "How often are commissions updated?",
        "Can I have sub-agents?",
        "What support do you provide to agencies?",
        "How do I market my onboarding link?",
        "Can I see which sellers are active?",
        "What happens if a seller stops using Arabia?",
        "Do I earn on both dropshipping and fulfillment orders?",
        "Is there a minimum payout for commissions?",
        "How do I apply for the agency program?",
    ]),
    ("Profit Calculator", [
        "What is the profit calculator?",
        "Where can I find the profit calculator?",
        "How do I use the profit calculator?",
        "Can I calculate profit for any product?",
        "Does the calculator include shipping costs?",
        "Can I simulate different selling prices?",
        "What is delivery ratio in the calculator?",
        "Is the calculator free?",
        "Can I save calculations?",
        "Does it work for KSA and UAE currencies?",
        "Can I calculate margin percentage?",
        "How accurate is the profit calculator?",
        "Can I export calculation results?",
        "Is there a mobile version?",
        "Do I need to log in to use it?",
        "Can I calculate profit for bulk orders?",
        "Does it account for COD fees?",
        "Can I compare multiple products?",
        "Is the calculator updated with current rates?",
        "Can I share my calculation with support?",
    ]),
    ("Payments", [
        "How do I get paid?",
        "What is the payment cycle?",
        "On which day are payments processed?",
        "Which countries do you support for payouts?",
        "Can I get paid in crypto?",
        "How long does bank transfer take?",
        "What is the minimum payout amount?",
        "Do you deduct any taxes?",
        "What is the COD tax in KSA?",
        "Can I change my bank account?",
        "How do I check my payment status?",
        "What if my payment is delayed?",
        "Do you pay in AED or USD?",
        "Can I receive payments in Pakistan?",
        "Is there a fee for international transfer?",
        "How do I provide my bank details?",
        "Can I get paid weekly instead of bi-weekly?",
        "What happens if my payment fails?",
        "Do you support PayPal?",
        "How are penalties deducted from payouts?",
    ]),
    ("Orders / Store Setup", [
        "How do I place a manual order?",
        "How do I upload bulk orders?",
        "Can I sync orders from Shopify?",
        "What is the store creation service?",
        "Is there a fee for store creation?",
        "How long does store setup take?",
        "Can I get a custom domain?",
        "Do you provide product import assistance?",
        "How to connect my existing store?",
        "What platforms can I integrate with?",
        "Do you offer a free trial for store setup?",
        "Can I cancel store creation service?",
        "What is included in store creation package?",
        "Do I get training after store setup?",
        "Can I add my own logo and branding?",
        "How do I test my store before going live?",
        "What support do you provide for store issues?",
        "Can I migrate my existing products?",
        "Is there a money-back guarantee?",
        "Can I upgrade my store plan later?",
    ]),
    ("Local & China Sourcing", [
        "What is product sourcing?",
        "How does local sourcing work in UAE/KSA?",
        "Can I source products without investment?",
        "What is the difference between dropshipping sourcing and wholesale?",
        "How does China sourcing work?",
        "Do I need to invest capital for China sourcing?",
        "How long does China sourcing take?",
        "Can I order samples before bulk?",
        "What is the minimum order quantity for sourcing?",
        "Can you source from Alibaba?",
        "Do you handle shipping from China?",
        "Are there import duties?",
        "Can I use your fulfillment for sourced products?",
        "How do I request a sourcing quote?",
        "Can I source branded products?",
        "What if the sourced product is defective?",
        "Do you provide quality inspection?",
        "Can I track the sourcing process?",
        "Is there a service fee for sourcing?",
        "How do I get started with sourcing?",
    ]),
    ("Store Creation & Marketing Services", [
        "What are your marketing services?",
        "How much does marketing service cost per month?",
        "What platforms do you advertise on?",
        "Can you run TikTok ads for my store?",
        "Do you guarantee sales from marketing?",
        "Can I get marketing only without store creation?",
        "How long does it take to see results?",
        "Do I need to provide ad creatives?",
        "Can I pause marketing service anytime?",
        "What is included in the store creation + marketing package?",
        "Do you do SEO for my store?",
        "Can you manage Facebook ads?",
        "What metrics do you report?",
        "Is there a contract for marketing?",
        "Can I choose target audience?",
        "Do you offer email marketing?",
        "What is the success rate of your campaigns?",
        "Can I request a marketing strategy call?",
        "Do you have case studies of successful stores?",
        "How do I sign up for marketing services?",
    ]),
]


async def run() -> None:
    from langchain_bot.control_plane import run_one_turn
    from services.store_integration_service.client import StoreIntegrationClient

    store = StoreIntegrationClient()

    out_path = ROOT / "docs" / "200_question_report.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    bot_flow = {
        "verified": True,
        "seller_id": SELLER_ID,
        "step": "conversational",
        "intro_shown": True,
        "customer_kind": "existing",
        "lang": "english",
    }

    total = sum(len(qs) for _, qs in QUESTIONS)
    done = 0
    t0 = time.monotonic()

    with out_path.open("w", encoding="utf-8") as f:
        f.write("# 200-question bot evaluation\n\n")
        f.write(f"_Generated against the live LLM-first orchestrator with seller_id={SELLER_ID}._\n\n")
        f.write(f"_Note: KB content varies by tenant. The local env may have no KB uploaded — production answers will include richer detail when the admin panel has the Arabia KB indexed._\n\n")
        f.write("---\n\n")

        for category, questions in QUESTIONS:
            print(f"\n=== {category} ({len(questions)} questions) ===")
            f.write(f"## {category}\n\n")
            for q in questions:
                done += 1
                t = time.monotonic()
                try:
                    result = await run_one_turn(
                        db=MagicMock(),
                        tenant_id=1,
                        customer_phone="03474685920",
                        conversation_id=1,
                        user_message=q,
                        language="english",
                        bot_flow=dict(bot_flow),
                        store_client=store,
                        agent_assigned=False,
                        customer_email="Urbanmart097@gmail.com",
                    )
                    latency = int((time.monotonic() - t) * 1000)
                    reply = (result.reply_text or "").strip()
                    tool_names = [tc.get("name") for tc in (result.tool_calls or [])]
                    fell_back = result.fell_back
                    reason = result.fallback_reason or ""
                except Exception as exc:  # noqa: BLE001
                    latency = int((time.monotonic() - t) * 1000)
                    reply = f"[ERROR] {type(exc).__name__}: {exc!s}"[:300]
                    tool_names = []
                    fell_back = True
                    reason = "exception"

                # Compact one-line console line so progress is visible.
                print(f"  [{done:3d}/{total}] {latency:>4}ms  tools={tool_names}  Q: {q[:60]}")

                f.write(f"### Q{done}. {q}\n\n")
                f.write(f"- **Latency**: {latency} ms")
                if tool_names:
                    f.write(f" | **Tools called**: `{', '.join(tool_names)}`")
                if fell_back:
                    f.write(f" | **Fell back**: `{reason}`")
                f.write("\n\n")
                f.write("**Bot reply:**\n\n")
                if reply:
                    # Quote the reply.
                    for line in reply.splitlines():
                        f.write(f"> {line}\n")
                else:
                    f.write("> _(empty reply)_\n")
                f.write("\n---\n\n")
                f.flush()
                # Light pacing to be polite to the OpenAI API.
                await asyncio.sleep(0.15)

        elapsed = time.monotonic() - t0
        f.write(f"\n_Generation finished in {elapsed:.1f} s._\n")

    print(f"\nDone. Report saved to {out_path}")
    print(f"Wall time: {time.monotonic() - t0:.1f} s")


if __name__ == "__main__":
    asyncio.run(run())
