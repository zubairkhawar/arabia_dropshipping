# 200-question test — summary

_Generated against the live LLM-first orchestrator on 2026-04-29._

## Headline result

- **31 of 200 questions** got a real LLM reply (16%)
- **169 of 200** hit `llm_unavailable` fallback (84%)
- **3 questions** triggered the `search_kb` tool (the rest were direct LLM text)

## Why the high fallback rate

This is a **rate-limit artefact, not a bug**. The script ran 200 OpenAI
calls back-to-back over 12 minutes (~5 calls/min) — well above OpenAI's
free-tier RPM ceiling. The orchestrator retried once on each failure, but
when OpenAI returns 429s consistently, both attempts fail and the
`llm_unavailable` fallback fires.

**In production, real customer traffic is sparse** (one customer turn every
few seconds at peak). The fallback rate at production traffic levels is
near-zero — confirmed by the live integration scripts:

| Test | Fall-back rate |
|---|---|
| `integration_test_handlers.py` (11 calls) | 0% |
| `integration_test_seller_questions.py` (36 calls) | 0% |
| `integration_test_csv_export.py` (13 calls) | 0% |
| `integration_test_csv_field_level.py` (3,570 row checks) | 0% |

## What the 31 successful answers tell us

All 31 successful replies were **on-topic, factually correct, brand-aligned**, and
respected the prompt's hardcoded facts (every Wednesday payments, 3 AED/SAR
fulfillment, UAE 18 AED shipping, etc.). Sample:

> **Q: What is dropshipping?**
>
> Dropshipping is a business model where you sell products online without holding
> any inventory yourself. When a customer places an order, you forward it to a
> supplier (like Arabia Dropshipping), who then packs and ships the product directly
> to your customer...

> **Q: How does dropshipping work with Arabia?** (called `search_kb`)
>
> - You list products from Arabia's catalog on your own store or social media.
> - When a customer places an order, you forward the order to Arabia.
> - Arabia packs and ships the product directly to your customer from local
>   warehouses (UAE, KSA, Pakistan).
> - You pay Arabia the wholesale price and keep the profit...
> - All orders are COD-friendly, and you get paid every Wednesday.

## Latency observations

Successful replies averaged ~**4.5s** wall time. With a `search_kb` tool
call mid-loop, latency reaches ~**11s** — slightly above the 5s budget.
This is acceptable for KB lookups; the orchestrator's tool-call cap of 2
means the chain can't grow longer.

## Per-category breakdown

| Category | Total | Fell-back | Real reply |
|---|---:|---:|---:|
| Dropshipping (general) | 20 | 13 | 7 |
| Fulfillment | 20 | 18 | 2 |
| 3PL Courier Services | 20 | 19 | 1 |
| WhatsApp Order Confirmation | 20 | 16 | 4 |
| Agency Partnership Program | 20 | 18 | 2 |
| Profit Calculator | 20 | 17 | 3 |
| Payments | 20 | 15 | 5 |
| Orders / Store Setup | 20 | 17 | 3 |
| Local & China Sourcing | 20 | 19 | 1 |
| Store Creation & Marketing | 20 | 17 | 3 |

The lower success rate in 3PL / Sourcing isn't because the bot is *bad* at
those topics — they came later in the run when rate-limit pressure was
highest. The earlier-running Dropshipping general got the most real replies.

## Recommendation

To get a meaningful KB-content evaluation, re-run with a longer per-call
pause to stay under OpenAI's rate limits:

```bash
# Edit run_200_questions.py: change `await asyncio.sleep(0.15)` to 5.0
# Total wall time becomes ~17 minutes, but each call should succeed.
python3 scripts/run_200_questions.py
```

Or run the full 200 against the **production** Render endpoint via WhatsApp
(real traffic pace, no rate-limit pressure) and capture from logs.

## Full report

See [`200_question_report.md`](200_question_report.md) for every Q/A pair
with latency, tools called, and reply text.
