"""
Pydantic argument schemas for every bot tool.

**Design rule:** the LLM drafts; the control plane gates and executes;
templates are the protocol library for messages whose exact bytes are
contractually meaningful (security, branding, parser contracts).
Anything else — greetings, errors, explanations, summaries — is LLM-drafted.

Each schema below is what the LLM must produce when it decides to call
the corresponding tool. The control plane re-validates server-side
because the LLM is allowed to be wrong about types.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class _Base(BaseModel):
    """Strict base — reject unknown fields so hallucinated args fail fast."""

    model_config = ConfigDict(extra="forbid")


# ─────────────────────────────────────────────────────────────────────────────
# VERIFICATION
# ─────────────────────────────────────────────────────────────────────────────
class StartVerificationArgs(_Base):
    """Begin the email→OTP→mobile script for an existing customer."""

    reason: str = Field(
        ...,
        description=(
            "One-line reason why verification is needed (e.g. 'order_lookup', "
            "'invoice_request'). Used for audit log only — not shown to customer."
        ),
        min_length=2,
        max_length=120,
    )


class VerifyOtpArgs(_Base):
    """Submit the 6-digit OTP the customer just typed."""

    code: str = Field(
        ...,
        description="The 6-digit code typed by the customer. Whitespace is stripped.",
        min_length=4,
        max_length=10,
    )


class SubmitVerificationEmailArgs(_Base):
    """Submit the email address the customer typed for verification."""

    email: str = Field(..., description="Email address typed by the customer.", min_length=4, max_length=200)


class SubmitVerificationMobileArgs(_Base):
    """Submit the mobile number the customer typed (after email+OTP succeed)."""

    mobile: str = Field(
        ...,
        description="Mobile number as typed by the customer; control plane normalizes formats.",
        min_length=6,
        max_length=20,
    )


class ResendOtpArgs(_Base):
    """Re-send the verification code to the email already on file for this turn."""

    pass


# ─────────────────────────────────────────────────────────────────────────────
# ORDER & INVOICE LOOKUPS  (verified-only)
# ─────────────────────────────────────────────────────────────────────────────
class LookupOrderArgs(_Base):
    """Fetch a single order by id. Returns full detail including tracking + invoice."""

    order_id: str = Field(
        ...,
        description="Order id or order number as referenced by the customer (digits, possibly with #).",
        min_length=1,
        max_length=40,
    )


class LookupOrdersByRangeArgs(_Base):
    """Fetch the customer's orders within a date range (ISO YYYY-MM-DD)."""

    date_from: date = Field(..., description="Inclusive start date (UTC), ISO YYYY-MM-DD.")
    date_to: date = Field(..., description="Inclusive end date (UTC), ISO YYYY-MM-DD.")
    label: Optional[str] = Field(
        None,
        description="Human label of the requested range, e.g. 'last 2 months'. Optional.",
        max_length=80,
    )


class ListInvoicesArgs(_Base):
    """List the customer's invoices (optionally filtered by date range)."""

    date_from: Optional[date] = Field(None, description="Inclusive start date, ISO YYYY-MM-DD.")
    date_to: Optional[date] = Field(None, description="Inclusive end date, ISO YYYY-MM-DD.")
    only_unpaid: bool = Field(
        False, description="If True, return only invoices where pay_status != 'Yes'."
    )


class GetTotalPaidArgs(_Base):
    """Sum of payable across paid invoices. No params; uses the verified seller scope."""

    pass


class GetTotalOrdersArgs(_Base):
    """Total order count across the verified customer's history."""

    pass


# ─────────────────────────────────────────────────────────────────────────────
# CSV EXPORT
# ─────────────────────────────────────────────────────────────────────────────
class GenerateCsvArgs(_Base):
    """Generate a CSV file for orders or a specific invoice and send via WhatsApp."""

    kind: str = Field(
        ...,
        description="'orders' for an orders CSV, 'invoice' for a single invoice's orders.",
        pattern="^(orders|invoice)$",
    )
    date_from: Optional[date] = Field(
        None, description="For kind=orders: inclusive start date. Defaults to last 365 days."
    )
    date_to: Optional[date] = Field(
        None, description="For kind=orders: inclusive end date. Defaults to today."
    )
    invoice_id: Optional[str] = Field(
        None, description="For kind=invoice: invoice id, if known."
    )
    invoice_date: Optional[date] = Field(
        None, description="For kind=invoice: the invoice's issue date, if known."
    )


# ─────────────────────────────────────────────────────────────────────────────
# KNOWLEDGE BASE & TRENDING
# ─────────────────────────────────────────────────────────────────────────────
class SearchKbArgs(_Base):
    """Retrieve relevant knowledge-base chunks for the customer's question."""

    query: str = Field(..., description="The customer's question, paraphrased if helpful.", min_length=2, max_length=400)
    max_chunks: int = Field(6, description="Top-N chunks to return.", ge=1, le=12)


class GetTrendingProductsArgs(_Base):
    """Render the trending (or non-trending) product list for a country."""

    country: str = Field(..., description="ISO-style country code or name: 'UAE', 'KSA', 'PAK'.", min_length=2, max_length=24)
    mode: str = Field(
        "trending",
        description="'trending' for trending products, 'non_trending' for the parallel list.",
        pattern="^(trending|non_trending)$",
    )
    direction: str = Field(
        "first",
        description="'first' = first page, 'next' = next page in cursor, 'restart' = page 1.",
        pattern="^(first|next|restart)$",
    )
    category: Optional[str] = Field(
        None, description="Optional category filter (must match an admin-configured category).", max_length=80
    )


# ─────────────────────────────────────────────────────────────────────────────
# HANDOFF
# ─────────────────────────────────────────────────────────────────────────────
class EscalateToAgentArgs(_Base):
    """Hand the conversation off to a human support agent."""

    reason: str = Field(
        ...,
        description=(
            "Short reason for routing to a human (e.g. 'customer_requested', "
            "'sensitive_dispute', 'bulk_order_inquiry')."
        ),
        min_length=2,
        max_length=120,
    )
    team: Optional[str] = Field(
        None,
        description="Suggested team name if known: 'new_customer', 'beginner', 'intermediate', 'expert'.",
        max_length=40,
    )
