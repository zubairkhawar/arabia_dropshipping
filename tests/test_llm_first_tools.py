"""Unit tests for the LLM-first tool registry, schemas, and control plane gating."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from langchain_bot.tools import (
    TOOL_REGISTRY,
    ToolCategory,
    available_tool_names,
    get_tool,
    tools_for_verification_state,
)
from langchain_bot.tools.schemas import (
    GenerateCsvArgs,
    GetTrendingProductsArgs,
    LookupOrderArgs,
    LookupOrdersByRangeArgs,
)


class TestRegistryShape:
    def test_minimum_tools_present(self) -> None:
        names = set(available_tool_names())
        for required in (
            "start_verification",  # only verification tool exposed; OTP/email/mobile owned by deterministic flow
            "lookup_order",
            "lookup_orders_by_range",
            "list_invoices",
            "get_total_paid",
            "get_total_orders",
            "generate_csv",
            "search_kb",
            "get_trending_products",
            "escalate_to_agent",
        ):
            assert required in names, f"missing tool: {required}"

    def test_get_tool_round_trip(self) -> None:
        for name in available_tool_names():
            t = get_tool(name)
            assert t.name == name
            assert t.description
            assert t.args_schema is not None
            assert t.category in {
                ToolCategory.PUBLIC,
                ToolCategory.VERIFICATION,
                ToolCategory.ACCOUNT_DATA,
            }

    def test_unknown_tool_raises(self) -> None:
        with pytest.raises(KeyError):
            get_tool("definitely_not_a_real_tool")

    def test_account_data_tools_categorised_correctly(self) -> None:
        for name in (
            "lookup_order",
            "lookup_orders_by_range",
            "list_invoices",
            "get_total_paid",
            "get_total_orders",
            "generate_csv",
        ):
            assert get_tool(name).category == ToolCategory.ACCOUNT_DATA

    def test_public_tools_categorised_correctly(self) -> None:
        for name in ("search_kb", "get_trending_products", "escalate_to_agent"):
            assert get_tool(name).category == ToolCategory.PUBLIC


class TestVerificationGating:
    """The control plane filters the LLM's tool list so unverified customers
    physically cannot call account_data tools — the LLM never sees them."""

    def test_unverified_no_flow_excludes_account_data(self) -> None:
        tools = tools_for_verification_state(verified=False, in_verification_flow=False)
        names = {t.name for t in tools}
        for blocked in (
            "lookup_order",
            "lookup_orders_by_range",
            "list_invoices",
            "get_total_paid",
            "get_total_orders",
            "generate_csv",
        ):
            assert blocked not in names, f"unverified must not see {blocked}"
        # But start_verification must still be available so the LLM can begin.
        assert "start_verification" in names
        # Public tools always available.
        assert "search_kb" in names
        assert "escalate_to_agent" in names
        assert "get_trending_products" in names

    def test_unverified_no_flow_excludes_mid_verif_tools(self) -> None:
        """Without an active verification flow, the LLM can only START verification."""
        tools = tools_for_verification_state(verified=False, in_verification_flow=False)
        names = {t.name for t in tools}
        for not_yet in ("verify_otp", "submit_verification_email", "submit_verification_mobile", "send_otp_resend"):
            assert not_yet not in names

    def test_unverified_in_flow_only_has_start_verification(self) -> None:
        """The deterministic state machine owns email/OTP/mobile parsing once
        a verification flow is active. The LLM only ever calls
        `start_verification` to enter the flow — any subsequent turn while in
        a verification step is handled by the legacy handlers (control plane
        falls back). So the LLM never needs submit_* / verify_otp tools."""
        tools = tools_for_verification_state(verified=False, in_verification_flow=True)
        names = {t.name for t in tools}
        assert "start_verification" in names
        # These submit_* tools were intentionally removed from the registry —
        # see langchain_bot/tools/registry.py docstring for the WhatsApp
        # transcript regression that motivated it.
        for removed in ("verify_otp", "submit_verification_email", "submit_verification_mobile", "send_otp_resend"):
            assert removed not in names
        # Still no account_data while not verified.
        assert "lookup_order" not in names

    def test_verified_includes_everything(self) -> None:
        tools = tools_for_verification_state(verified=True, in_verification_flow=False)
        names = {t.name for t in tools}
        for required in (
            "lookup_order",
            "list_invoices",
            "get_total_paid",
            "search_kb",
            "escalate_to_agent",
            "generate_csv",
        ):
            assert required in names


class TestSchemaValidation:
    """Schemas reject hallucinated/malformed args — defense in depth."""

    def test_lookup_order_requires_order_id(self) -> None:
        with pytest.raises(ValidationError):
            LookupOrderArgs()  # type: ignore[call-arg]

    def test_lookup_order_strips_hashtag(self) -> None:
        # Pydantic doesn't strip — that's the handler's job — but the schema accepts both forms.
        a = LookupOrderArgs(order_id="#137044")
        assert a.order_id == "#137044"

    def test_lookup_orders_by_range_validates_iso_dates(self) -> None:
        a = LookupOrdersByRangeArgs(date_from="2026-03-01", date_to="2026-04-30", label="last 2 months")  # type: ignore[arg-type]
        assert a.date_from.isoformat() == "2026-03-01"
        assert a.date_to.isoformat() == "2026-04-30"

    def test_lookup_orders_by_range_rejects_garbage_date(self) -> None:
        with pytest.raises(ValidationError):
            LookupOrdersByRangeArgs(date_from="yesterday", date_to="today")  # type: ignore[arg-type]

    def test_generate_csv_kind_enum(self) -> None:
        GenerateCsvArgs(kind="orders")
        GenerateCsvArgs(kind="invoice")
        with pytest.raises(ValidationError):
            GenerateCsvArgs(kind="something_else")  # type: ignore[arg-type]

    def test_trending_direction_enum(self) -> None:
        GetTrendingProductsArgs(country="UAE", mode="trending", direction="first")
        GetTrendingProductsArgs(country="KSA", mode="non_trending", direction="next")
        with pytest.raises(ValidationError):
            GetTrendingProductsArgs(country="UAE", mode="trending", direction="backwards")  # type: ignore[arg-type]

    def test_extra_fields_forbidden(self) -> None:
        """Hallucinated field → reject."""
        with pytest.raises(ValidationError):
            LookupOrderArgs(order_id="137044", hallucinated_field="oops")  # type: ignore[call-arg]


class TestControlPlaneRouting:
    """Higher-level test: should_route_to_llm_first reasons should be correct."""

    def test_agent_assigned_falls_back(self) -> None:
        from langchain_bot.control_plane import should_route_to_llm_first

        reason = should_route_to_llm_first(
            tenant_id=1, customer_phone="9230", bot_flow={"step": "conversational"}, agent_assigned=True
        )
        assert reason == "agent_assigned"

    def test_active_verification_step_falls_back(self) -> None:
        from langchain_bot.control_plane import should_route_to_llm_first
        from config import settings

        # Simulate llm_first enabled for tenant
        original = settings.bot_mode
        settings.bot_mode = "llm_first"
        try:
            reason = should_route_to_llm_first(
                tenant_id=1,
                customer_phone="9230",
                bot_flow={"step": "existing_awaiting_verification_code"},
                agent_assigned=False,
            )
            assert reason == "deterministic_step:existing_awaiting_verification_code"
        finally:
            settings.bot_mode = original

    def test_legacy_mode_falls_back(self) -> None:
        from langchain_bot.control_plane import should_route_to_llm_first
        from config import settings

        original = settings.bot_mode
        settings.bot_mode = "legacy"
        settings.bot_mode_llm_first_tenants = ""
        try:
            reason = should_route_to_llm_first(
                tenant_id=1, customer_phone="9230", bot_flow={"step": "conversational"}, agent_assigned=False
            )
            assert reason == "tenant_in_legacy_mode"
        finally:
            settings.bot_mode = original

    def test_per_tenant_override_routes_to_llm_first(self) -> None:
        from langchain_bot.control_plane import should_route_to_llm_first
        from config import settings

        orig_mode = settings.bot_mode
        orig_tenants = settings.bot_mode_llm_first_tenants
        settings.bot_mode = "legacy"
        settings.bot_mode_llm_first_tenants = "1,7"
        try:
            # Tenant 1 is enabled → routed to llm_first (None means "go")
            assert (
                should_route_to_llm_first(
                    tenant_id=1, customer_phone="9230", bot_flow={"step": "conversational"}, agent_assigned=False
                )
                is None
            )
            # Tenant 2 is not in the list → falls back
            assert (
                should_route_to_llm_first(
                    tenant_id=2, customer_phone="9230", bot_flow={"step": "conversational"}, agent_assigned=False
                )
                == "tenant_in_legacy_mode"
            )
        finally:
            settings.bot_mode = orig_mode
            settings.bot_mode_llm_first_tenants = orig_tenants


class TestPiiRedaction:
    def test_redacts_customer_email(self) -> None:
        from langchain_bot.control_plane import redact_pii

        out = redact_pii(
            "Your email john@example.com is on file.",
            customer_email="john@example.com",
        )
        assert "john@example.com" not in out
        assert "[redacted-email]" in out

    def test_does_not_redact_arabia_support_email(self) -> None:
        from langchain_bot.control_plane import redact_pii

        # No customer_email passed — only the customer's own should be masked.
        out = redact_pii(
            "Contact info@arabiadropship.com for help.",
            customer_email=None,
        )
        assert "info@arabiadropship.com" in out

    def test_redacts_customer_phone_with_separators(self) -> None:
        from langchain_bot.control_plane import redact_pii

        out = redact_pii(
            "Number 923-001-234567 is yours.",
            customer_phone="923001234567",
        )
        assert "[redacted-phone]" in out
        assert "923001234567" not in out

    def test_handles_empty(self) -> None:
        from langchain_bot.control_plane import redact_pii

        assert redact_pii("", customer_email="x@y.z") == ""
        assert redact_pii(None) is None  # type: ignore[arg-type]


class TestCostTracker:
    def test_cost_estimate_directional(self) -> None:
        from langchain_bot.llm_cost_tracker import estimate_cost_usd

        # gpt-4.1: $2.50 per 1M input → 1k = $0.0025
        assert abs(estimate_cost_usd("gpt-4.1", 1000, 0) - 0.0025) < 1e-9

    def test_unknown_model_falls_back(self) -> None:
        from langchain_bot.llm_cost_tracker import estimate_cost_usd

        # Unknown model → conservative gpt-4.1 default
        assert estimate_cost_usd("super-fictional-7b", 1000, 0) > 0
