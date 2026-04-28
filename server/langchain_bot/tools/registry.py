"""
Tool registry: name → ToolDefinition (schema + category + description).

The control plane uses ``tools_for_verification_state`` to filter the
LLM's allowed tools per turn so a non-verified customer literally
*cannot* call account_data tools — the LLM never sees them.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Type

from pydantic import BaseModel

from langchain_bot.tools import schemas as S


class ToolCategory(str, Enum):
    """Categories drive runtime gating in the control plane."""

    PUBLIC = "public"  # Anyone can use — KB, trending, escalation
    VERIFICATION = "verification"  # Always available; how customer becomes verified
    ACCOUNT_DATA = "account_data"  # Requires verified=True (orders, invoices, CSV, totals)


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    args_schema: Type[BaseModel]
    category: ToolCategory


TOOL_REGISTRY: Dict[str, ToolDefinition] = {
    # ── Verification ────────────────────────────────────────────────────────
    # The deterministic state machine owns email/OTP/mobile parsing — the LLM
    # only triggers entry into the flow via `start_verification`. Do not add
    # `submit_*` or `verify_otp` tools here; they would let the LLM 'play
    # verification' instead of deferring to the security-critical script.
    "start_verification": ToolDefinition(
        name="start_verification",
        description=(
            "Begin the deterministic verification script for an existing customer. "
            "Call this whenever the customer asks for order/invoice/tracking/profit/account data "
            "and is not yet verified. After this tool returns, the deterministic state machine "
            "takes over for email/OTP/mobile entry on subsequent turns — do not draft those "
            "prompts yourself, do not ask for email/OTP/mobile in free-form text."
        ),
        args_schema=S.StartVerificationArgs,
        category=ToolCategory.VERIFICATION,
    ),
    # ── Account data (gated: verified=True only) ────────────────────────────
    "lookup_order": ToolDefinition(
        name="lookup_order",
        description=(
            "Fetch full details for one order by id (date, status, tracking, items, "
            "shipping, profit, invoice). Use when the customer references a specific order number."
        ),
        args_schema=S.LookupOrderArgs,
        category=ToolCategory.ACCOUNT_DATA,
    ),
    "lookup_orders_by_range": ToolDefinition(
        name="lookup_orders_by_range",
        description=(
            "Fetch the customer's orders for a date range. Use for 'last 2 months', "
            "'March se April tak', or any explicit range request."
        ),
        args_schema=S.LookupOrdersByRangeArgs,
        category=ToolCategory.ACCOUNT_DATA,
    ),
    "list_invoices": ToolDefinition(
        name="list_invoices",
        description=(
            "List the customer's invoices, optionally filtered by date range or unpaid-only. "
            "Use for 'saari invoices', 'kitni invoices unpaid hain', etc."
        ),
        args_schema=S.ListInvoicesArgs,
        category=ToolCategory.ACCOUNT_DATA,
    ),
    "get_total_paid": ToolDefinition(
        name="get_total_paid",
        description="Total paid amount across all paid invoices. Use for 'total kitni payment ab tak mili hai'.",
        args_schema=S.GetTotalPaidArgs,
        category=ToolCategory.ACCOUNT_DATA,
    ),
    "get_total_orders": ToolDefinition(
        name="get_total_orders",
        description="Total order count across the customer's history. Use for 'meray total orders kitne hain'.",
        args_schema=S.GetTotalOrdersArgs,
        category=ToolCategory.ACCOUNT_DATA,
    ),
    "generate_csv": ToolDefinition(
        name="generate_csv",
        description=(
            "Generate a CSV (orders or single invoice) and send it as a WhatsApp document. "
            "Use when the customer types 'csv', 'send file', '22 April wali invoice ki CSV bhej do', etc."
        ),
        args_schema=S.GenerateCsvArgs,
        category=ToolCategory.ACCOUNT_DATA,
    ),
    # ── Public ──────────────────────────────────────────────────────────────
    "search_kb": ToolDefinition(
        name="search_kb",
        description=(
            "Search the knowledge base for service / policy questions (shipping, returns, "
            "fulfillment, agency, sourcing, payments, etc.). Use for any FAQ-style question."
        ),
        args_schema=S.SearchKbArgs,
        category=ToolCategory.PUBLIC,
    ),
    "get_trending_products": ToolDefinition(
        name="get_trending_products",
        description=(
            "Render the trending or non-trending product list for a country. Pagination "
            "is server-managed; pass direction='first' to start, 'next' to continue."
        ),
        args_schema=S.GetTrendingProductsArgs,
        category=ToolCategory.PUBLIC,
    ),
    "escalate_to_agent": ToolDefinition(
        name="escalate_to_agent",
        description=(
            "Route the conversation to a human support agent. Use when the customer asks "
            "for an agent, expresses frustration, or has a sensitive/bulk inquiry."
        ),
        args_schema=S.EscalateToAgentArgs,
        category=ToolCategory.PUBLIC,
    ),
}


def get_tool(name: str) -> ToolDefinition:
    if name not in TOOL_REGISTRY:
        raise KeyError(f"unknown tool: {name}")
    return TOOL_REGISTRY[name]


def available_tool_names() -> List[str]:
    return list(TOOL_REGISTRY.keys())


def tools_for_verification_state(*, verified: bool, in_verification_flow: bool) -> List[ToolDefinition]:
    """Filter the tool list per turn based on the customer's state.

    - Unverified, not in verification flow: PUBLIC + ``start_verification`` only.
    - Unverified, mid-verification: PUBLIC + VERIFICATION (so LLM can submit email/OTP/mobile).
    - Verified: PUBLIC + ACCOUNT_DATA + VERIFICATION (rare to re-verify, but allowed).
    """
    out: List[ToolDefinition] = [t for t in TOOL_REGISTRY.values() if t.category == ToolCategory.PUBLIC]
    if verified:
        out += [t for t in TOOL_REGISTRY.values() if t.category == ToolCategory.ACCOUNT_DATA]
        out += [t for t in TOOL_REGISTRY.values() if t.category == ToolCategory.VERIFICATION]
    elif in_verification_flow:
        out += [t for t in TOOL_REGISTRY.values() if t.category == ToolCategory.VERIFICATION]
    else:
        # Allow ONLY start_verification from the verification category — the LLM should not
        # pre-emptively submit email/OTP/mobile before the script is engaged.
        out.append(TOOL_REGISTRY["start_verification"])
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Structured tool result returned by handlers (consumed by the orchestrator
# loop and turned into a tool message for the next LLM invocation).
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class ToolResult:
    ok: bool
    data: Dict[str, Any]
    error: str = ""

    def to_llm_payload(self) -> Dict[str, Any]:
        """Compact JSON-able dict that goes back to the LLM as a tool message."""
        if self.ok:
            return {"ok": True, "data": self.data}
        return {"ok": False, "error": self.error or "unknown error"}
