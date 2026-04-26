"""Clear human assignment and scripted bot state (e.g. customer /reset while agent assigned)."""
from __future__ import annotations

from typing import Any, Dict

from models import Conversation

BOT_FLOW_KEY = "bot_flow"


def release_agent_and_clear_bot_flow(conversation: Conversation) -> None:
    conversation.agent_id = None
    raw = conversation.conversation_metadata
    md: Dict[str, Any] = dict(raw) if isinstance(raw, dict) else {}
    md[BOT_FLOW_KEY] = {}
    conversation.conversation_metadata = md


def normalize_bot_flow_after_human_handoff_end(conversation: Conversation) -> None:
    """
    When a human agent releases or closes a thread, reset scripted flow to normal bot chat.
    Clears handoff retry (awaiting_agent) and forces step 'conversational' so the next
    customer message is handled by the bot unless they explicitly ask for an agent again.
    """
    raw = conversation.conversation_metadata
    md: Dict[str, Any] = dict(raw) if isinstance(raw, dict) else {}
    bf = md.get(BOT_FLOW_KEY)
    if not isinstance(bf, dict):
        # If bot_flow key is absent or non-dict, write a fresh conversational state.
        md[BOT_FLOW_KEY] = {"step": "conversational"}
        conversation.conversation_metadata = md
        return
    new_bf = dict(bf)
    new_bf["step"] = "conversational"
    # Clear all handoff and sourcing state so the bot starts fresh
    for key in (
        "pending_handoff_team",
        "sourcing_product_name",
        "awaiting_sourcing_details",
    ):
        new_bf.pop(key, None)
    md[BOT_FLOW_KEY] = new_bf
    conversation.conversation_metadata = md
