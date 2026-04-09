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
