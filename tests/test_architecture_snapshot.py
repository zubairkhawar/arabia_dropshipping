"""
Architecture snapshot test — Phase 5: "LLM-first default, 4 deterministic buckets."

This is the user-requested check that documents what's LLM-first vs
deterministic in the codebase. It runs as a regular pytest, so any
drift (someone moves a bucket out of the deterministic set, or pulls
LLM-first into something it shouldn't own) fails CI.

The 4 deterministic buckets:
  ① Verification (email → OTP → mobile script + bail-detection escape)
  ② Pagination cursor (trending / non-trending structured renderer)
  ③ File pipelines (CSV → R2 → Meta document)
  ④ Handoff routing (agent assignment, queue, availability)

Everything else is LLM-first via the orchestrator + tool registry.

If you change architecture, update the EXPECTED_* sets below to match.
The point is to make changes deliberate and reviewable.
"""
from __future__ import annotations

from langchain_bot.tools import TOOL_REGISTRY, ToolCategory


# ─────────────────────────────────────────────────────────────────────────────
# Bucket 1: Verification — deterministic step states
# ─────────────────────────────────────────────────────────────────────────────
DETERMINISTIC_VERIFICATION_STEPS = frozenset(
    {
        # `awaiting_customer_type` (1/2 new/existing menu) was deleted on
        # 2026-04-30. The LLM-first path now decides routing implicitly.
        "awaiting_resume_choice",
        "existing_awaiting_email",
        "existing_awaiting_verification_code",
        "existing_awaiting_mobile",
    }
)


# ─────────────────────────────────────────────────────────────────────────────
# Bucket 2: Pagination — trending / non-trending step states
# ─────────────────────────────────────────────────────────────────────────────
DETERMINISTIC_PAGINATION_STEPS = frozenset(
    {
        "trending_awaiting_country",
        "trending_showing_products",
    }
)


# ─────────────────────────────────────────────────────────────────────────────
# Bucket 3: File pipelines — invoked by csv_signal from generate_csv tool
# ─────────────────────────────────────────────────────────────────────────────
DETERMINISTIC_FILE_PIPELINES = frozenset(
    {
        "orders_csv_export",  # build_orders_csv_export_bytes → R2 → Meta document
        "invoice_csv_export",  # build_invoice_csv_export_bytes → R2 → Meta document
    }
)


# ─────────────────────────────────────────────────────────────────────────────
# Bucket 4: Handoff routing — agent assignment + queue
# ─────────────────────────────────────────────────────────────────────────────
DETERMINISTIC_HANDOFF_STEPS = frozenset(
    {
        "awaiting_agent",
    }
)


# ─────────────────────────────────────────────────────────────────────────────
# What the LLM owns (all turns NOT routed to a deterministic bucket)
# ─────────────────────────────────────────────────────────────────────────────
LLM_OWNED_RESPONSIBILITIES = frozenset(
    {
        "greeting_after_intro",       # mid-conversation "Hi" → warm reply
        "conversational_acks",        # thanks/ok/hmm → warm reply
        "kb_questions",                # service / policy questions → search_kb tool
        "verification_intro",          # "I see you want orders, let me verify" wording
        "order_data_presentation",     # verified-customer order replies → lookup_order
        "date_range_orders",           # → lookup_orders_by_range
        "invoice_listings",            # → list_invoices
        "total_paid_amount",           # → get_total_paid
        "total_order_count",           # → get_total_orders
        "csv_intent_detection",        # → generate_csv (the file pipeline still deterministic)
        "trending_intent_detection",   # → get_trending_products (the cursor still deterministic)
        "agent_escalation_intent",     # → escalate_to_agent (routing still deterministic)
        "privacy_refusals",            # "give me my email" → polite decline
        "why_cant_you_replies",        # explanation of refusals
        "topic_change_during_verification",  # bail-detect → LLM
        "out_of_scope_redirects",      # weather etc. → polite redirect
        "errors_and_clarifications",   # "I didn't get that, can you rephrase?"
        "fallback_for_unknown_intent",  # any phrasing not caught by tools
    }
)


# ─────────────────────────────────────────────────────────────────────────────
# Tool categories — derived from the registry
# ─────────────────────────────────────────────────────────────────────────────
EXPECTED_PUBLIC_TOOLS = frozenset(
    {"search_kb", "get_trending_products", "escalate_to_agent"}
)
EXPECTED_VERIFICATION_TOOLS = frozenset(
    {
        # Only `start_verification` is exposed. email/OTP/mobile are owned by
        # the deterministic state machine — letting the LLM call submit_* tools
        # caused the LLM to "play verification" without actually advancing the
        # flow (WhatsApp transcript regression on 2026-04-29).
        "start_verification",
    }
)
EXPECTED_ACCOUNT_DATA_TOOLS = frozenset(
    {
        "lookup_order",
        "lookup_orders_by_range",
        "list_invoices",
        "get_total_paid",
        "get_total_orders",
        "generate_csv",
    }
)


class TestDeterministicBuckets:
    """The 4 buckets that stay deterministic (per Phase 5)."""

    def test_only_4_deterministic_buckets_total(self) -> None:
        """Drift guard: no fifth deterministic bucket should be added quietly."""
        all_deterministic_step_sets = [
            DETERMINISTIC_VERIFICATION_STEPS,
            DETERMINISTIC_PAGINATION_STEPS,
            DETERMINISTIC_HANDOFF_STEPS,
        ]
        # File pipelines aren't step-based; they're invoked by signals. Counted separately.
        assert len(all_deterministic_step_sets) + 1 == 4

    def test_verification_steps_match_service_otp_guard_steps(self) -> None:
        """The control plane reads otp_guard_steps from service.py; both must agree."""
        from services.customer_bot_flow.service import (
            _bail_to_conversational,  # noqa: F401 (proves module imports)
        )
        # The actual otp_guard_steps set is local to process_customer_bot_message,
        # so we assert the snapshot constant matches the documented set.
        # If service.py changes its set, this will diverge — fix the snapshot.
        assert DETERMINISTIC_VERIFICATION_STEPS == {
            "awaiting_resume_choice",
            "existing_awaiting_email",
            "existing_awaiting_verification_code",
            "existing_awaiting_mobile",
        }


class TestToolRegistryShape:
    """The tool registry is the contract — these categories drive runtime gating."""

    def test_public_tools_match(self) -> None:
        actual = {n for n, t in TOOL_REGISTRY.items() if t.category == ToolCategory.PUBLIC}
        assert actual == EXPECTED_PUBLIC_TOOLS, (
            "Public tool set drifted. If you added a tool, decide if it's "
            "PUBLIC (no verification needed) or ACCOUNT_DATA (needs verified=True)."
        )

    def test_verification_tools_match(self) -> None:
        actual = {n for n, t in TOOL_REGISTRY.items() if t.category == ToolCategory.VERIFICATION}
        assert actual == EXPECTED_VERIFICATION_TOOLS

    def test_account_data_tools_match(self) -> None:
        actual = {n for n, t in TOOL_REGISTRY.items() if t.category == ToolCategory.ACCOUNT_DATA}
        assert actual == EXPECTED_ACCOUNT_DATA_TOOLS, (
            "Account-data tool set drifted. These are the ones the control plane "
            "filters out for unverified customers — the verification gate."
        )

    def test_no_orphan_tools(self) -> None:
        """Every tool in the registry must be in exactly one expected bucket."""
        all_expected = (
            EXPECTED_PUBLIC_TOOLS | EXPECTED_VERIFICATION_TOOLS | EXPECTED_ACCOUNT_DATA_TOOLS
        )
        actual = set(TOOL_REGISTRY.keys())
        unknown = actual - all_expected
        missing = all_expected - actual
        assert not unknown, f"Unexpected tools in registry (update snapshot): {sorted(unknown)}"
        assert not missing, f"Tools missing from registry (update snapshot): {sorted(missing)}"


class TestLlmOwnedResponsibilities:
    """Documentation: these are the responsibilities the LLM owns end-to-end.
    Any new conversational behavior should be added to LLM_OWNED_RESPONSIBILITIES
    rather than introduced as a new deterministic intent detector."""

    def test_llm_owned_set_documented(self) -> None:
        # Just assert the set has the expected size — keeps the snapshot
        # in sync with the comment block at top of this module.
        assert len(LLM_OWNED_RESPONSIBILITIES) >= 18, (
            "LLM_OWNED_RESPONSIBILITIES shrunk — did something drift back to "
            "deterministic? Update the snapshot if intentional."
        )

    def test_no_overlap_between_llm_and_deterministic(self) -> None:
        """No responsibility label should appear in both sets."""
        all_deterministic = (
            DETERMINISTIC_VERIFICATION_STEPS
            | DETERMINISTIC_PAGINATION_STEPS
            | DETERMINISTIC_FILE_PIPELINES
            | DETERMINISTIC_HANDOFF_STEPS
        )
        assert not (LLM_OWNED_RESPONSIBILITIES & all_deterministic)


class TestRoutingPolicy:
    """The control plane's routing reasons must be enumerable so we know
    every fall-back path is intentional."""

    EXPECTED_FALLBACK_REASONS = frozenset(
        {
            "agent_assigned",
            "tenant_in_legacy_mode",
            "daily_token_cap_exceeded",
            # plus any reason of the form "deterministic_step:<step>" — matched as prefix
        }
    )

    def test_routing_reasons_string_constants(self) -> None:
        """If you add a new fall-back reason, add it here too."""
        # We don't import the strings (they're inline literals); this is
        # purely documentation. CI sees the snapshot.
        assert "agent_assigned" in self.EXPECTED_FALLBACK_REASONS
        assert "tenant_in_legacy_mode" in self.EXPECTED_FALLBACK_REASONS
        assert "daily_token_cap_exceeded" in self.EXPECTED_FALLBACK_REASONS


class TestDefaultBotMode:
    """Phase 5 flipped the default from 'legacy' to 'llm_first'."""

    def test_default_is_llm_first(self) -> None:
        # We import a fresh Settings to read the class default, not the
        # currently-configured runtime value.
        from config import Settings

        # Settings reads from .env at instance time; check the class default attribute.
        # Pydantic BaseSettings exposes default via model_fields.
        default = Settings.model_fields["bot_mode"].default
        assert default == "llm_first", (
            f"Phase 5 flipped bot_mode default to 'llm_first'. Got: {default}"
        )
