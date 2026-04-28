# LLM-first bot rollout — operations guide

This document is the runbook for switching the bot from **legacy** (state-machine-first) to **llm_first** (orchestrator + tool-use). It covers what's already shipped, what to do next, the kill-switch procedure, and the KPIs to watch.

## What's already shipped (commit `88310da`+)

**Phase 0 — foundation**
- `BOT_MODE` config flag, default `legacy`. Per-tenant override via `BOT_MODE_LLM_FIRST_TENANTS=1,7,12`.
- Per-customer + per-tenant daily token tracking in Redis with auto-expiry.
- Per-customer daily token soft cap (`LLM_DAILY_TOKEN_CAP_PER_CUSTOMER`, default 50K) — over-cap turns fall back to legacy until UTC rollover.
- Estimated-cost-USD logging per LLM call for finance dashboards.
- `LLM_MAX_TOOL_CALLS_PER_TURN` cap (default 2) for latency-budget safety.

**Phase 1 — tool registry** (`server/langchain_bot/tools/`)
- 14 tools categorised as `PUBLIC | VERIFICATION | ACCOUNT_DATA`.
- Pydantic schemas with `extra="forbid"` so hallucinated args fail fast.
- Handlers wrap the existing services (`store_client`, `kb`); no business-logic duplication.

**Phase 2 — orchestrator** (`server/langchain_bot/orchestrator.py`)
- `ChatOpenAI.bind_tools()` with the per-turn allowed subset.
- Tool-use loop with hard cap; graceful fallback on LLM failure.
- Token + latency captured for the cost tracker.

**Phase 3 — control plane** (`server/langchain_bot/control_plane.py`)
- Routing decision that returns explicit fall-back reasons (logged).
- Verification gate: removes account-data tools from the LLM's options when unverified — the LLM cannot see them, let alone call them.
- Handoff lock: agent_assigned → instant fallback (no LLM call).
- PII redaction: customer's own email/phone are masked in outbound text. Arabia support contacts are not redacted.

**Phase 4.1 — strangler-fig wiring** (`service.py`)
- Inserted the LLM-first attempt before the existing `ai_forward()` call in the conversational branch.
- When fall-back occurs, behaviour is unchanged (the legacy bot still runs).
- Verification-start signal advances `flow.step` to `existing_awaiting_email` so the next turn lands on the deterministic OTP exchange.

**Phase 5 — template policy** (`tests/test_templates_protocol_policy.py`)
- Lint test that fails CI if a new template lands without being added to `PROTOCOL_WHITELIST` with a one-line reason.
- Stale whitelist entries are also flagged so the list stays accurate.

## Rollout sequence (what to do once deployed)

### Step 1 — verify deploy is dark
After `git push`, Render builds and ships. Default `BOT_MODE=legacy`, so:
- All customers should still hit the legacy state machine.
- Logs should show no `llm_call ...` lines tagged with the orchestrator (tool calls = 0).
- Test suite must report **111+ passed**.

### Step 2 — internal QA (one tenant, one phone)
1. On Render, set `BOT_MODE_LLM_FIRST_TENANTS=<your tenant id>` (or set `BOT_MODE=llm_first` if you have only one tenant).
2. Send the TC1–L test plan from your own WhatsApp number.
3. Watch logs in real time:
   - `control_plane: routing to llm_first ...` should appear.
   - `llm_call model=gpt-4.1 in=... out=... cost_usd=...` should appear.
   - Estimated cost per turn should be **< $0.01** for KB / acks / greetings; **< $0.05** for verification + lookup chains.
4. Required behaviours to verify:
   - Greetings, acks, "thanks" all reply naturally.
   - "kya arabia reliable hai" → KB-grounded answer (search_kb tool fires).
   - "mujhy order details btao" (unverified) → bot asks new/existing (start_verification tool fires).
   - Verification flow then proceeds via legacy email→OTP→mobile script.
   - "saari orders csv bhej do" (verified) → `csv_signal=True` path falls through to legacy CSV pipeline.

### Step 3 — soft launch (5% of customers)
1. Pick one or two low-volume tenants. Add them to `BOT_MODE_LLM_FIRST_TENANTS`.
2. Monitor for 5–7 days. KPIs (see below) must be within thresholds before widening.

### Step 4 — broaden rollout
- After a clean week, add another batch of tenants.
- Once all tenants are flagged, flip `BOT_MODE=llm_first` and remove `BOT_MODE_LLM_FIRST_TENANTS`.

### Step 5 — clean up legacy
Only after a clean month of 100% llm_first:
- Remove the `ai_forward()` fallback path from `service.py` line ~4239 (the path after the `try: ... except: ...`).
- Migrate the remaining handlers (sourcing, trending renderer rewrite, handoff messaging) per the migration order below.
- Drop unused templates after their callsites are gone (use the `test_templates_protocol_policy.py` whitelist to trim).

## KPIs to watch (set up dashboards before Step 2)

| Metric | Target | Where it comes from |
|---|---|---|
| Cost per turn (p50) | < $0.005 | `llm_call ... cost_usd=...` log lines |
| Cost per turn (p95) | < $0.02 | same |
| Daily OpenAI spend | < $20/day baseline; < $50/day under launch | aggregate of cost_usd |
| Latency p95 (LLM-first turns) | < 5s | `llm_call ... latency_ms=...` log lines |
| Tool-cap hits per day | < 1% of turns | `tool-call cap hit` warning lines |
| Verification gate violations | **0** | should never happen — assert in tests; alert on log line `account_data tool ... requires verified` |
| Fall-back rate (legacy taking over) | < 30% expected (verification + handoff steps trigger fallback) | `falling back to legacy (...)` debug lines |
| LLM hard-failure rate | < 0.5% | `OpenAI chat call failed ...` error lines |
| Customer-visible apology-only replies | 0 (TC8 regression) | sample manually, plus alert on text "masla aa gaya" in outbound |

## Kill-switch procedure

If anything goes wrong:

1. **Most surgical**: remove the bad tenant id from `BOT_MODE_LLM_FIRST_TENANTS` in Render env. Render auto-redeploys → that tenant returns to legacy on next turn.
2. **Per-customer kill**: drop the `LLM_DAILY_TOKEN_CAP_PER_CUSTOMER` to a tiny number (e.g. `1`). Every llm_first turn falls back instantly.
3. **Global kill**: set `BOT_MODE=legacy` and clear `BOT_MODE_LLM_FIRST_TENANTS`. Render redeploy → entire fleet on legacy.
4. **Code rollback**: `git revert 88310da..HEAD` (or whatever the last legacy-only commit was) → push → Render redeploy.

The legacy state machine is fully intact — these are all reversible config changes.

## Migration order for remaining handlers (post-rollout)

These are *not* part of Phase 4.1. Migrate one at a time, behind the same flag, after llm_first is stable for conversational/acks/KB:

1. **Order lookup by id (TCA, TCH)** — replace `_extract_order_id_from_message` heuristics with the `lookup_order` tool. LLM extracts the order id from the message, calls the tool, formats the reply.
2. **Date-range orders (TCD)** — replace `_parse_date_range` with the `lookup_orders_by_range` tool. LLM parses the date phrase ("last 2 months", "March se April") into ISO dates.
3. **Invoices (TCC, TCK)** — replace invoice flow with `list_invoices` + `get_total_paid` tools.
4. **Total order count (TCB)** — replace with `get_total_orders` tool.
5. **Generate CSV (TCG, TCL)** — replace the ~150 lines of CSV intent detection in `service.py` with the `generate_csv` tool. The actual CSV-build/R2-upload pipeline stays.
6. **Trending renderer** — *don't* migrate. Keep it deterministic; the LLM only triggers it via `get_trending_products` tool.
7. **Sourcing flow** — *don't* migrate. State machine handles structured data collection.
8. **Verification flow** — *don't* migrate. OTP exchange stays scripted forever.

After 1–5, `service.py` should drop from ~5400 lines to **~2000–2500 lines** (verification + trending + sourcing + handoff + thin LLM-first dispatcher).

## What's deliberately not in this plan

- **Switching LLM provider**: tool-use is OpenAI-specific in this implementation. Anthropic/Bedrock would require adapter work in `orchestrator.py`. Out of scope.
- **Streaming responses**: LLM replies are returned all at once. WhatsApp doesn't need streaming.
- **Per-tenant prompt customization**: the system prompt in `prompts.py` is global. If different tenants need different rules later, add a `tenant_id`-keyed prompt fragment loader.
- **Vector / embedding KB retrieval**: `kb_use_embeddings` flag exists but the orchestrator currently uses the same token-overlap retrieval as the legacy bot. Worth revisiting after rollout.

## Rollback validation checklist

After any rollback, before declaring all-clear:

- [ ] `BOT_MODE=legacy` confirmed in `Render env` (or per-tenant override empty)
- [ ] First WhatsApp message after rollback sees a legacy reply (no `routing to llm_first` log)
- [ ] Test suite still passes (`pytest --no-header`)
- [ ] No new `OpenAI chat call failed` lines in last 5 minutes of logs
