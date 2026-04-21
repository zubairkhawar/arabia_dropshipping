"""
Integration-style tests: Meta webhook parsing + memory flows (no live HTTP/DB by default).

For full-stack tests against a running API + Postgres + Redis, set RUN_FULL_STACK=1
and configure DATABASE_URL / REDIS_URL.
"""

from __future__ import annotations

import os

import pytest

from services.memory_service import ConversationMemory

from tests.helpers.meta_webhook import (
    meta_text_message_payload,
    parse_meta_whatsapp_inbound,
)


class TestMetaWebhookParsing:
    def test_parse_text_inbound(self):
        body = meta_text_message_payload("923001234567", "How does dropshipping work?")
        parsed = parse_meta_whatsapp_inbound(body)
        assert parsed is not None
        assert parsed["kind"] == "text"
        assert parsed["text"] == "How does dropshipping work?"
        assert parsed["from_phone"] == "923001234567"


class TestMemoryMultiStepFlows:
    """Simulated multi-turn memory usage (same contract as bot + Redis)."""

    def test_topic_stack_then_promote(self):
        phone = "923001111111"
        ConversationMemory.clear_all(phone)
        try:
            ConversationMemory.store_pending_intent(
                phone, "dropshipping", "how_it_works", "q1", 0.85
            )
            ConversationMemory.store_pending_intent(
                phone, "shipping", "general_question", "q2", 0.85
            )
            assert ConversationMemory.get_intent_queue(phone)[0]["topic"] == "dropshipping"
            ConversationMemory.clear_pending_intent(phone, promote_from_queue=True)
            assert ConversationMemory.get_pending_intent(phone)["topic"] == "dropshipping"
            assert ConversationMemory.get_intent_queue(phone) == []
        finally:
            ConversationMemory.clear_all(phone)


@pytest.mark.skipif(
    not os.getenv("RUN_FULL_STACK"),
    reason="Set RUN_FULL_STACK=1 and DATABASE_URL to run API integration tests",
)
class TestFullStackOptional:
    """Placeholder for future httpx tests against a deployed or local server."""

    def test_placeholder(self):
        assert os.getenv("DATABASE_URL")
