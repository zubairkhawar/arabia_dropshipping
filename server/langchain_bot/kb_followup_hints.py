"""
Heuristic follow-up question lines when KB chunks do not define ``followup_questions`` in metadata.

Matched against the user's message and/or retrieved excerpt text (lowercased). Used only to
seed the runtime **KB follow-up suggestions** block — the model still must obey excerpt facts.
"""
from __future__ import annotations

from typing import Iterable, List, Sequence, Tuple

# (keywords that may appear in user message OR excerpt blob), (English suggestion lines)
KB_FOLLOWUP_RULES: Tuple[Tuple[Tuple[str, ...], Tuple[str, ...]], ...] = (
    (
        ("3pl", "third-party logistics", "third party logistics", "third-party"),
        (
            "Would you like shipping rates for UAE compared to KSA?",
            "Do you want to know how to open or link a courier account for 3PL?",
            "Should I explain how 3PL differs from standard dropshipping on Arabia?",
        ),
    ),
    (
        ("product sourcing", "local sourcing", "sourcing from local", "wholesale"),
        (
            "Would you like the dropshipping (no-inventory) path or wholesale purchase details?",
            "Do you want to know what information to send for a sourcing request?",
            "Should I connect you with support for bulk or custom sourcing?",
        ),
    ),
    (
        ("china sourcing", "sourcing from china", "global sourcing"),
        (
            "Do you want to know typical capital or MOQ expectations for China sourcing?",
            "Would you like fulfillment options after goods arrive in the UAE?",
            "Should I summarize timelines vs local sourcing?",
        ),
    ),
    (
        ("store creation", "marketing service", "aed 300", "store setup", "tiktok", "meta ads"),
        (
            "Would you like pricing for store creation only or bundled with marketing?",
            "Do you want the steps to activate the service after payment?",
            "Should I explain what the marketing team handles day to day?",
        ),
    ),
    (
        ("agency partnership", "agency program", "commission", "referral"),
        (
            "Do you want to see how commissions are tracked for partners?",
            "Would you like the onboarding steps for your first seller?",
            "Should I share the official Agency Partnership Program link again?",
        ),
    ),
    (
        ("whatsapp order confirmation", "order confirmation", "screenshot proof", "per order"),
        (
            "Would you like the per-order pricing and which countries it applies to?",
            "Do you want the screenshot proof workflow explained step by step?",
            "Should I clarify how this differs from standard order notifications?",
        ),
    ),
    (
        ("shipping charge", "delivery charge", "return charge", "uae shipping", "ksa shipping"),
        (
            "Do you need return charges as well as delivery rates?",
            "Would you like typical delivery timelines for your market?",
            "Should I compare UAE vs KSA shipping rules from the knowledge base?",
        ),
    ),
    (
        ("calculator", "profit calculator", "margin"),
        (
            "Would you like a walk-through example using a sample product price?",
            "Do you want to know which fees are included in the calculator output?",
            "Should I explain how profit relates to shipping in the calculator?",
        ),
    ),
    (
        ("bulk upload", "shopify", "sync", "order placement", "place orders"),
        (
            "Would you like bulk upload vs Shopify sync explained in short?",
            "Do you want the requirements before enabling automatic order push?",
            "Should I outline what happens after an order is placed from your store?",
        ),
    ),
    (
        ("logistics", "fulfillment", "warehouse", "courier"),
        (
            "Would you like rates and surcharges for your selling country?",
            "Do you want handoff vs self-managed inventory options?",
            "Should I summarize returns handling from the knowledge base?",
        ),
    ),
)


def heuristic_kb_followups(user_message: str, excerpt_lines: Sequence[str]) -> List[str]:
    blob = " ".join(excerpt_lines).lower()
    um = (user_message or "").lower()
    combined = f"{um} {blob}"
    out: List[str] = []
    for keys, questions in KB_FOLLOWUP_RULES:
        if any(k in combined for k in keys):
            out.extend(questions)
    return out


def dedupe_suggestions(lines: Iterable[str], *, max_items: int = 10) -> List[str]:
    seen: set[str] = set()
    out: List[str] = []
    for raw in lines:
        s = (raw or "").strip()
        if len(s) < 10:
            continue
        key = s.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
        if len(out) >= max_items:
            break
    return out
