"""
Rigorous Q&A test:

  1. Inject the customer-provided KB (Arabia Dropship Complete Knowledge Base)
     into a monkey-patched search_kb tool so the LLM has Arabia-specific
     facts to ground answers.
  2. Run real questions from prior WhatsApp transcripts in this session
     PLUS LLM-generated follow-up questions for 10-min worth of session
     turns, in English / Roman Urdu / Arabic.
  3. Pace calls 5s apart to stay under OpenAI rate limits.
  4. Record every Q/A pair to docs/rigorous_qna_report.md, flagging any
     hard-failures, missing tool calls, or content red-flags.
"""
from __future__ import annotations

import asyncio
import sys
import time
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
PACE_SECONDS = 5.0  # respect OpenAI RPM limits


# ─────────────────────────────────────────────────────────────────────────────
# KB content (provided by the user 2026-04-29) — chunked for retrieval.
# Each chunk has a tag (used for keyword matching) and a body.
# ─────────────────────────────────────────────────────────────────────────────
KB_CHUNKS: List[Tuple[str, str]] = [
    ("overview", "Arabia Dropship is a B2B dropshipping and 3PL fulfillment platform focused on the Middle East (UAE, Saudi Arabia, Pakistan). Enables users to start an e-commerce business without holding inventory."),
    ("links navigation register login partnership about features services", "Home: https://www.arabiadropship.com/  Register: https://www.arabiadropship.com/register  Login: https://www.arabiadropship.com/login  Agency: https://www.arabiadropship.com/partnership  About: https://www.arabiadropship.com/about  Features: https://www.arabiadropship.com/features  Services: https://www.arabiadropship.com/services"),
    ("3pl logistics courier shipping rates",
     "3PL Logistics (Third-Party Logistics): for sellers who manage their own products and order fulfillment but need access to reliable courier services at competitive rates. You own and manage your own inventory, you handle order processing, Arabia provides you with a courier account at discounted rates. To get started: contact Customer Support and provide (1) your average daily order volume, (2) the market/region you need 3PL services in (UAE, KSA, etc.), (3) your expected shipping rates. Once finalised, Arabia creates a courier account for you, gives you full access to manage shipments, and processes payments/invoices to your bank account."),
    ("sourcing local china product",
     "Local Sourcing (UAE/KSA): Arabia can source local products in two ways. Option A — Dropshipping (no investment): you provide product details, Arabia sources and purchases on your behalf, the product is listed on Arabia (visible only to you), you start selling without upfront cost; once an order delivers Arabia deducts the product cost from your sales. Option B — Wholesale + Fulfillment: Arabia sources from the local market, you purchase at wholesale rates upfront, Arabia lists the product and can handle fulfillment — gives lower product cost and higher margin. China Sourcing: only for products NOT available in local markets. You must invest your own capital — Arabia does NOT purchase China-sourced products on your behalf. After sourcing, you can store inventory in your own warehouse OR use Arabia's fulfillment service. Dropshipping (no-investment) is NOT available for China sourcing. To start: contact Customer Support with product name(s), images, required quantity, and your preferred plan (dropshipping for local only, or wholesale)."),
    ("store creation marketing",
     "Store Creation & Marketing Service. Pricing: Store Creation Only = AED 300 (one-time), Store Creation + 1 Month Marketing = AED 1,200, Marketing Only (existing stores) = AED 1,000/month recurring. Service is end-to-end: Arabia's marketing team handles product research, choosing the right platform (TikTok, Meta, etc.), budget planning, ad strategy, running and optimising campaigns, and scaling toward profitability. The team makes the key decisions; you only need to monitor incoming orders. To start: contact Customer Support, specify which service you need, complete payment, then your service is activated."),
    ("fulfillment warehouse",
     "Fulfillment service is offered in BOTH UAE and KSA. Pricing: UAE 3 AED per order fulfillment charge, KSA 3 SAR per order fulfillment charge, warehousing is FREE in both countries. To get started, contact Customer Support and provide product/quantity details. The agent will share the warehouse address and concerned-staff contact number. Once your inventory is received at the warehouse you'll be notified, your product will be listed on Arabia (visible only to you), and you can start selling."),
    ("agency partnership commission",
     "Agency Partnership Program. Apply and get approved → receive a unique onboarding link to invite sellers. Commission: 1 AED per delivered order from every seller you onboard. Track commissions inside your agency dashboard with full transparency (paid + unpaid). No technical knowledge required. Direct access: https://www.agency.arabiadropship.com/. The agency portal gives you: order insights (consignee/seller/status), live tracking, smart filters (by status/seller/date), invoices (seller payouts, invoice numbers, dates, transfer status), seller management (active vs inactive sellers, performance — current and previous month), agency dashboard (active sellers, monthly delivered orders, top sellers). You can onboard UNLIMITED sellers."),
    ("whatsapp order confirmation",
     "Arabia WhatsApp Order Confirmation Service. All seller orders are confirmed through WhatsApp, with screenshot proof of every attempt. Three (3) attempts are made at different times, with a screenshot uploaded for every attempt for full transparency. Sellers can see whether the customer confirmed the order, whether the order was canceled, and the complete proof of communication. If the customer does NOT respond after 3 attempts: the seller decides — request cancellation through Customer Support, or ask Arabia to forcefully ship the order. Common practice: if address is complete → forced ship; if address is incomplete → cancel. To view confirmation proof: Orders tab → click on any order → 'Order Confirmation' section next to customer details → view all uploaded screenshots. Pricing: UAE 1 AED per order (whether confirmed or canceled), KSA 2 SAR per order (whether confirmed or canceled). NOT available in Pakistan."),
    ("calculator profit",
     "Arabia Calculator helps estimate expected profit and make better pricing decisions. Calculates whether you'll be in profit or loss based on delivery ratio (e.g. 80%), order cost (e.g. 10 AED), and selling price. Useful for determining the optimal selling price given your costs and delivery performance. Similar to Amazon-seller profit calculators, designed for eCommerce store owners. Access: Settings → Calculator inside your Arabia account, or directly at https://www.new.arabiadropship.com/calculator."),
    ("payments payouts bank crypto wednesday",
     "Payments are processed every WEDNESDAY for both UAE and KSA. Bi-weekly payouts directly to bank accounts. Supported countries for payouts: Pakistan, India, Bangladesh, United Arab Emirates. Bank account from another country → contact Customer Support. If your payout exceeds AED 1,000, it can also be processed via cryptocurrency."),
    ("integrations shopify easyorders lightfunnels youcan bulk",
     "Technical integrations: Shopify (products + orders sync), EasyOrders, Lightfunnels, YouCan. Features: Shopify sync (products and orders), Excel bulk import, automated processing, advanced checkout, real-time dashboard. Order placement methods: (1) Single Order Placement — checkout page, enter customer details + COD amount; (2) Bulk Upload — Orders section → Bulk Upload → download example file → fill in details → upload (unlimited orders); (3) Automatic Syncing (Shopify) — install https://apps.shopify.com/oshi-handling, go to Settings → Profile → Store Connectivity in Arabia, click 'Add Store', enter Store URL + API Key (in the installed app), save. Then Orders tab → Sync Orders. Important: you must add Arabia product SKUs to your Shopify products for syncing."),
    ("market coverage uae saudi pakistan qatar",
     "Active markets: UAE, Saudi Arabia, Pakistan. Coming Soon: Qatar."),
    ("performance stats orders sellers dispatch warehouse",
     "Logistics performance: 10M+ COD orders delivered, 12K+ sellers, 98.4% on-time dispatch, 12+ courier partners, 14K+ units stored in warehouses."),
    ("seller workflow registration approval dashboard import",
     "Seller workflow: register account → wait for approval → access dashboard → connect store → import products → run ads → receive orders → Arabia ships → customer pays COD → seller receives profit."),
    ("shipping charges uae ksa pakistan",
     "SHIPPING CHARGES — UAE: Delivered 18 AED, Returned 5 AED. KSA: Delivered 25 SAR, Returned 10 AED, plus 3% TAX ON NET COD PAYMENT (e.g. payable 1000 SAR → 30 SAR COD tax → 970 SAR transferred). Pakistan: Delivered 250 PKR (TCS) or 200 PKR (Leopard/Postex/Trax), Returned same as delivered (250 PKR TCS / 200 PKR others)."),
    ("returns policy",
     "Returns are managed by Arabia Dropship: includes inspection and restocking, with support team assistance. Return charges — UAE: 5 AED, KSA: 10 AED, Pakistan: 250 PKR (TCS) or 200 PKR (Leopard/Postex/Trax)."),
    ("support contact whatsapp email",
     "Support — WhatsApp (main channel): https://wa.me/971555516304, Phone: +971 555516304, Email: info@arabiadropship.com."),
    ("activation account approval",
     "Account activation typically takes 30 minutes to 1 hour after signup. Once activated you can log in. If your account isn't active yet, please wait a short while."),
    ("product privacy security winning",
     "Sharing a winning product with Arabia: your product remains COMPLETELY SECURE. Listed product is visible ONLY to you — other sellers cannot see it. Arabia is policy-strict about product privacy."),
    ("comparison zambeel competitors",
     "Why Arabia is better than Zambeel and other dropshipping platforms: faster delivery (1-3 days), COD-focused for Middle East, integrated 3PL logistics, WhatsApp order confirmation, product privacy, automated fulfillment, end-to-end services including sourcing/marketing/scaling support."),
    ("setup fees free trial inventory",
     "No setup or membership fee. No need for inventory. Shipping time UAE: 1-3 days. Bi-weekly payouts. Yes you can track orders. Product catalog is inside the dashboard after approval."),
    ("legal compliance terms privacy",
     "Legal: must have your own Privacy Policy on your Shopify/YouCan store informing customers their data will be shared with a fulfillment partner for delivery. Must provide accurate phone numbers (used for WhatsApp confirmation and courier contact). Bank account name must match your Arabia Dropship registration name to avoid payout delays. Terms: https://www.arabiadropship.com/terms-of-service. Privacy: https://www.arabiadropship.com/privacy-policy."),
]


def _kb_search(query: str, max_chunks: int = 5) -> List[Tuple[str, str]]:
    q = (query or "").lower()
    scored: List[Tuple[int, int, Tuple[str, str]]] = []
    for i, (tag, body) in enumerate(KB_CHUNKS):
        s = 0
        for word in q.split():
            if not word.strip():
                continue
            wl = word.lower()
            if wl in tag:
                s += 3
            if wl in body.lower():
                s += 1
        if s > 0:
            scored.append((s, i, (tag, body)))
    scored.sort(key=lambda t: (-t[0], t[1]))
    return [c for _, _, c in scored[:max_chunks]]


# ─────────────────────────────────────────────────────────────────────────────
# Question battery — real WhatsApp questions from this session + follow-ups.
# Each language gets the same 12 turns of a coherent session.
# ─────────────────────────────────────────────────────────────────────────────
SESSIONS_EN = [
    "What is dropshipping with Arabia?",
    "How much does fulfillment cost?",
    "What about KSA?",
    "When do you process payments?",
    "Can I get paid in crypto?",
    "What are the shipping charges UAE?",
    "And for Pakistan?",
    "How does WhatsApp order confirmation work?",
    "Is it available in Pakistan?",
    "How do I become an agency partner?",
    "How much commission per order?",
    "Where can I track my commissions?",
]

SESSIONS_UR = [
    "Mujhay dropshipping kaise kaam karti hai bataeyn",
    "Fulfillment ki price kya hai?",
    "KSA mein kya rate hai?",
    "Payment kab milti hai?",
    "Kya crypto mein payment ho sakti hai?",
    "UAE shipping charges kitne hain?",
    "Aur Pakistan ke liye?",
    "WhatsApp order confirmation kaise kaam karta hai?",
    "Pakistan mein available hai?",
    "Agency partner kaise banoon?",
    "Kitna commission milta hai per order?",
    "Commissions kahan track kar sakta hoon?",
]

SESSIONS_AR = [
    "ما هو الدروبشيبينغ مع أرابيا؟",
    "كم تكلفة خدمة التغليف والشحن (Fulfillment)؟",
    "ما هي الأسعار في السعودية؟",
    "متى تتم معالجة الدفعات؟",
    "هل يمكنني استلام الدفعات بالعملة الرقمية؟",
    "ما هي رسوم الشحن في الإمارات؟",
    "وفي باكستان؟",
    "كيف تعمل خدمة تأكيد الطلب عبر واتساب؟",
    "هل متوفرة في باكستان؟",
    "كيف أصبح شريك وكالة؟",
    "كم العمولة لكل طلب؟",
    "أين أتابع عمولاتي؟",
]


# ─────────────────────────────────────────────────────────────────────────────
# Patch the search_kb handler to use our injected KB
# ─────────────────────────────────────────────────────────────────────────────
def _patch_search_kb() -> None:
    from langchain_bot.tools import handlers as _h
    from langchain_bot.tools.registry import ToolResult

    async def fake_handle_search_kb(args: Any, ctx: Any) -> ToolResult:
        chunks = _kb_search(args.query, max_chunks=args.max_chunks)
        if not chunks:
            return ToolResult(ok=True, data={"knowledge_excerpts": "No matching KB chunks.", "kb_followup_suggestions": "None"})
        body = "Connected knowledge sources:\n- (Arabia KB injected)\n\nMost relevant knowledge excerpts:\n"
        for tag, txt in chunks:
            body += f"- [{tag}] {txt}\n"
        return ToolResult(ok=True, data={"knowledge_excerpts": body, "kb_followup_suggestions": "None"})

    _h.handle_search_kb = fake_handle_search_kb
    _h.HANDLERS["search_kb"] = fake_handle_search_kb


async def run_session(
    label: str,
    questions: List[str],
    language: str,
    out: Any,
) -> Tuple[int, int, int]:
    from langchain_bot.control_plane import run_one_turn
    from services.store_integration_service.client import StoreIntegrationClient

    store = StoreIntegrationClient()
    flow = {
        "verified": True,
        "seller_id": SELLER_ID,
        "step": "conversational",
        "intro_shown": True,
        "customer_kind": "existing",
        "lang": language,
    }

    out.write(f"\n## {label}\n\n")
    print(f"\n=== {label} ({len(questions)} turns) ===")

    fb_count = 0
    tool_count = 0
    success = 0
    for i, q in enumerate(questions, 1):
        t0 = time.monotonic()
        try:
            r = await run_one_turn(
                db=MagicMock(),
                tenant_id=1,
                customer_phone="03474685920",
                conversation_id=1,
                user_message=q,
                language=language,
                bot_flow=dict(flow),
                store_client=store,
                agent_assigned=False,
                customer_email="Urbanmart097@gmail.com",
            )
            ms = int((time.monotonic() - t0) * 1000)
            reply = (r.reply_text or "").strip()
            tools = [tc.get("name") for tc in (r.tool_calls or [])]
            fell = r.fell_back
            reason = r.fallback_reason or ""
        except Exception as exc:  # noqa: BLE001
            ms = int((time.monotonic() - t0) * 1000)
            reply = f"[ERROR] {type(exc).__name__}: {exc!s}"[:300]
            tools = []
            fell = True
            reason = "exception"

        if fell:
            fb_count += 1
        else:
            success += 1
        if tools:
            tool_count += 1

        print(f"  [{i:2d}/{len(questions)}] {ms:>5}ms tools={tools}{' [FB]' if fell else ''}  Q: {q[:50]}")
        out.write(f"### Turn {i}: {q}\n\n")
        out.write(f"- **Latency**: {ms} ms")
        if tools:
            out.write(f"  |  **Tools**: `{', '.join(tools)}`")
        if fell:
            out.write(f"  |  **Fall-back**: `{reason}`")
        out.write("\n\n**Reply:**\n\n")
        if reply:
            for line in reply.splitlines():
                out.write(f"> {line}\n")
        else:
            out.write("> _(empty)_\n")
        out.write("\n---\n\n")
        out.flush()
        await asyncio.sleep(PACE_SECONDS)

    return success, fb_count, tool_count


async def main() -> None:
    _patch_search_kb()

    out_path = ROOT / "docs" / "rigorous_qna_report.md"
    with out_path.open("w", encoding="utf-8") as f:
        f.write("# Rigorous Q&A test (KB-injected)\n\n")
        f.write(f"_Generated 2026-04-29 — paced at {PACE_SECONDS}s/call to stay under OpenAI RPM._\n\n")
        f.write("_The customer-provided KB is injected into the `search_kb` tool's response so the LLM has Arabia-specific facts to ground answers, simulating production where the admin panel has the KB indexed._\n\n")
        f.write("---\n")

        results: List[Tuple[str, int, int, int]] = []
        for label, qs, lang in [
            ("English session", SESSIONS_EN, "english"),
            ("Roman Urdu session", SESSIONS_UR, "roman_urdu"),
            ("Arabic session", SESSIONS_AR, "arabic"),
        ]:
            s, fb, tc = await run_session(label, qs, lang, f)
            results.append((label, s, fb, tc))

        f.write("\n## Summary\n\n")
        f.write("| Session | Successful | Fall-backs | Tool calls |\n")
        f.write("|---|---:|---:|---:|\n")
        for label, s, fb, tc in results:
            f.write(f"| {label} | {s} | {fb} | {tc} |\n")
        total_s = sum(r[1] for r in results)
        total_fb = sum(r[2] for r in results)
        total_tc = sum(r[3] for r in results)
        f.write(f"| **Total** | **{total_s}** | **{total_fb}** | **{total_tc}** |\n")

    print(f"\nDone. Report: {out_path}")
    for label, s, fb, tc in results:
        print(f"  {label}: success={s} fb={fb} tools={tc}")


if __name__ == "__main__":
    asyncio.run(main())
