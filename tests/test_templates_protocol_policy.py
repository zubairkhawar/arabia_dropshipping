"""
Policy lint: enforce the "templates are a protocol library, not the conversation engine" rule.

Every key in ``BOT_FLOW_TEMPLATES`` must either be on the **whitelist** of
known protocol templates OR have a `# protocol-reason: ...` comment in
``templates.py`` immediately above its block.

Goal: stop contributors from drifting back to template-everywhere thinking
once the LLM-first redesign ships. Adding a new template now requires
declaring why the LLM cannot draft it.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from services.customer_bot_flow.templates import BOT_FLOW_TEMPLATES


# Known protocol templates that already have a clear protocol reason.
# Update this list (with rationale) when adding a new protocol-reason entry.
PROTOCOL_WHITELIST: dict[str, str] = {
    # branded contract — exact welcome menu
    "greeting": "branded welcome menu — marketing/legal contract",
    "entry": "branded welcome menu (alias of greeting)",
    # next-turn parser contracts — flow expects literal '1'/'2', email shape, phone shape
    "customer_type_menu_reminder": "parser expects literal '1' or '2' reply",
    "ask_email": "next reply must be email-shaped",
    "ask_mobile": "next reply must be phone-shaped",
    "ask_order": "next reply must be order-id-shaped",
    # format hints — exact examples matter
    "email_invalid": "format hint with literal example",
    "mobile_unsupported_country": "format hints (+923..., +971..., +966...)",
    # security-critical with {email} placeholder — LLM cannot be trusted to substitute
    "code_sent": "OTP message with {email} substitution",
    "verify": "OTP message with {email} substitution (alias)",
    # categorical failure modes — paraphrasing collapses distinct outcomes
    "verify_send_error": "distinct from wrong/expired code",
    "verify_invalid_code": "distinct from send-error",
    "verification_expired_reverify": "re-entry trigger; flow re-arms here",
    "customer_not_found_after_verify": "terminal verification failure",
    # flow milestone marker — flow transitions on this exact text
    "email_verified_success": "flow milestone marker",
    # command literal
    "agent_relay_ack": "contains literal '/reset' command instruction",
    # LLM-failure fallback (must not depend on LLM)
    "fallback": "fallback when LLM call itself fails",
    # legacy structured renderers (trending, sourcing, handoff) — kept until
    # Phase 4.x migrates them; explicit reason logged for each below.
    "hello_ack": "legacy helper return-string contract; remove after helper refactor",
    "new_customer_welcome": "legacy state-machine reply",
    "existing_customer_welcome": "legacy state-machine reply",
    "customer_type_unclear": "next-turn parser expects 1/2 — keep until LLM-first owns the customer-type flow",
    "existing_switch_verify": "legacy state-machine intro for existing-customer verification",
    "order_verify_intro": "legacy state-machine intro",
    "account_verify_intro": "legacy state-machine intro",
    "verification_success": "legacy state-machine milestone",
    "verified_followup": "legacy state-machine prompt",
    "order_not_found": "legacy state-machine error",
    "order_lookup_error": "legacy state-machine error",
    "cannot_find_order_help": "legacy state-machine help block",
    "connecting_agent_named": "used by append_handoff_agent_line() helper",
    "connecting": "legacy handoff message",
    "handoff_retry": "legacy handoff retry message",
    "handoff_try_later_dropbot": "legacy handoff fallback",
    "handoff_unavailable": "legacy handoff with {schedule} substitution",
    "kb_wrap": "legacy KB reply wrapper",
    "kb_wrap_agency": "legacy KB reply wrapper for agency topic",
    # trending product list (structured renderer — kept deterministic by design)
    "trending_ask_country": "trending pagination flow",
    "trending_country_retry": "trending pagination flow",
    "trending_intro_first": "structured renderer — trending list",
    "trending_intro_more": "structured renderer — trending list",
    "trending_intro_first_category": "structured renderer — trending category",
    "trending_intro_more_category": "structured renderer — trending category",
    "trending_footer_first_has_more": "structured renderer — trending footer",
    "trending_footer_first_only": "structured renderer — trending footer",
    "trending_footer_more_has_more": "structured renderer — trending footer",
    "trending_footer_more_end": "structured renderer — trending footer",
    "trending_followup_suggestions": "structured renderer — trending follow-ups",
    "trending_no_more_pages": "structured renderer — trending end",
    "trending_product_detail_ok": "structured renderer — product detail",
    "trending_product_detail_missing": "structured renderer — product detail",
    "trending_no_products": "structured renderer — trending empty",
    "trending_no_products_category": "structured renderer — trending empty (category)",
    # non-trending parallel set (referenced via _trending_tpl dynamic mapping)
    "non_trending_intro_first": "structured renderer — non-trending list",
    "non_trending_intro_more": "structured renderer — non-trending list",
    "non_trending_intro_first_category": "structured renderer — non-trending category",
    "non_trending_intro_more_category": "structured renderer — non-trending category",
    "non_trending_footer_first_has_more": "structured renderer — non-trending footer",
    "non_trending_footer_first_only": "structured renderer — non-trending footer",
    "non_trending_footer_more_has_more": "structured renderer — non-trending footer",
    "non_trending_footer_more_end": "structured renderer — non-trending footer",
    "non_trending_followup_suggestions": "structured renderer — non-trending follow-ups",
    "non_trending_no_more_pages": "structured renderer — non-trending end",
    "non_trending_no_products": "structured renderer — non-trending empty",
    "non_trending_no_products_category": "structured renderer — non-trending empty (category)",
    # sourcing flow — structured data collection state machine
    "sourcing_collect_details": "sourcing flow — structured data prompt",
    "sourcing_with_product": "sourcing flow — structured data prompt with {product}",
    "sourcing_handoff": "sourcing flow handoff",
    "sourcing_bulk_handoff": "sourcing flow bulk handoff",
}


def _templates_file_text() -> str:
    repo_root = Path(__file__).resolve().parent.parent
    p = repo_root / "server" / "services" / "customer_bot_flow" / "templates.py"
    return p.read_text(encoding="utf-8")


class TestTemplatePolicy:
    def test_every_template_is_whitelisted(self) -> None:
        """Adding a new template entry without putting it on the whitelist
        with a protocol reason fails this test. That is the point — new
        templates require justification."""
        defined = set(BOT_FLOW_TEMPLATES.keys())
        whitelisted = set(PROTOCOL_WHITELIST.keys())
        unjustified = sorted(defined - whitelisted)
        assert not unjustified, (
            "New BOT_FLOW_TEMPLATES entries must be added to PROTOCOL_WHITELIST "
            "in tests/test_templates_protocol_policy.py with a one-line reason. "
            f"Unjustified keys: {unjustified}"
        )

    def test_whitelist_does_not_drift_above_what_exists(self) -> None:
        """Stale whitelist entries (template was deleted but reason wasn't)
        should be cleaned up so the whitelist stays accurate."""
        defined = set(BOT_FLOW_TEMPLATES.keys())
        whitelisted = set(PROTOCOL_WHITELIST.keys())
        stale = sorted(whitelisted - defined)
        assert not stale, (
            "PROTOCOL_WHITELIST has entries for templates that no longer exist. "
            f"Remove these from the whitelist: {stale}"
        )

    def test_design_rule_docstring_present(self) -> None:
        """The design rule must remain documented in templates.py so anyone
        editing the file sees it."""
        text = _templates_file_text()
        assert "Design rule" in text or "design rule" in text
        assert "protocol library" in text
        assert "control plane" in text

    def test_no_obvious_conversational_template_added(self) -> None:
        """Heuristic: keys named like generic conversation (apology_*, sorry_*,
        ack_*, sympathy_*, please_wait_*) almost always belong in prompts.py
        as LLM rules, not here. Catch them at PR time."""
        bad_prefixes = ("apology_", "sorry_", "sympathy_", "please_wait_")
        offenders = [
            k for k in BOT_FLOW_TEMPLATES
            if any(k.startswith(p) for p in bad_prefixes)
        ]
        assert not offenders, (
            "These keys look like generic conversational text — they belong "
            f"in prompts.py as LLM rules, not in templates.py: {offenders}"
        )
