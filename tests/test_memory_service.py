"""Unit tests for ConversationMemory (Redis layer; uses fakeredis)."""

from __future__ import annotations

import pytest

from services.memory_service import ConversationMemory


class TestConversationMemory:
    @pytest.fixture
    def phone(self) -> str:
        return "923001234567"

    @pytest.fixture
    def cleanup(self, phone: str):
        yield
        ConversationMemory.clear_all(phone)

    # ----- pending intent -----

    def test_store_and_get_pending_intent(self, phone: str, cleanup):
        ConversationMemory.store_pending_intent(
            phone,
            "dropshipping",
            "how_it_works",
            "How does dropshipping work?",
            0.85,
        )
        pending = ConversationMemory.get_pending_intent(phone)
        assert pending is not None
        assert pending["topic"] == "dropshipping"
        assert pending["intent_type"] == "how_it_works"
        assert pending["confidence"] == 0.85

    def test_clear_pending_intent(self, phone: str, cleanup):
        ConversationMemory.store_pending_intent(
            phone, "dropshipping", "how_it_works", "test", 0.85
        )
        ConversationMemory.clear_pending_intent(phone)
        assert ConversationMemory.get_pending_intent(phone) is None

    def test_relevance_check_with_number(self, phone: str, cleanup):
        ConversationMemory.store_pending_intent(
            phone, "dropshipping", "how_it_works", "test", 0.85
        )
        assert ConversationMemory.is_relevant_to_pending_intent(phone, "1") is True

    def test_relevance_check_with_topic_change(self, phone: str, cleanup):
        ConversationMemory.store_pending_intent(
            phone, "dropshipping", "how_it_works", "test", 0.85
        )
        assert (
            ConversationMemory.is_relevant_to_pending_intent(
                phone, "actually tell me about shipping"
            )
            is False
        )
        assert ConversationMemory.get_pending_intent(phone) is None

    # ----- intent queue -----

    def test_intent_queue_stores_different_topics(self, phone: str, cleanup):
        ConversationMemory.store_pending_intent(
            phone, "dropshipping", "how_it_works", "test1", 0.85, queue_previous=True
        )
        ConversationMemory.store_pending_intent(
            phone, "shipping", "general_question", "test2", 0.85, queue_previous=True
        )
        queue = ConversationMemory.get_intent_queue(phone)
        assert len(queue) == 1
        assert queue[0]["topic"] == "dropshipping"
        pending = ConversationMemory.get_pending_intent(phone)
        assert pending is not None
        assert pending["topic"] == "shipping"

    def test_same_topic_does_not_queue(self, phone: str, cleanup):
        ConversationMemory.store_pending_intent(
            phone, "dropshipping", "how_it_works", "test1", 0.85
        )
        ConversationMemory.store_pending_intent(
            phone, "dropshipping", "profit_query", "test2", 0.85, queue_previous=True
        )
        assert len(ConversationMemory.get_intent_queue(phone)) == 0
        pending = ConversationMemory.get_pending_intent(phone)
        assert pending["intent_type"] == "profit_query"

    def test_promote_from_queue(self, phone: str, cleanup):
        ConversationMemory.store_pending_intent(
            phone, "dropshipping", "how_it_works", "test1", 0.85
        )
        ConversationMemory.store_pending_intent(
            phone, "shipping", "general_question", "test2", 0.85, queue_previous=True
        )
        ConversationMemory.clear_pending_intent(phone, promote_from_queue=True)
        pending = ConversationMemory.get_pending_intent(phone)
        assert pending is not None
        assert pending["topic"] == "dropshipping"
        assert ConversationMemory.get_intent_queue(phone) == []

    # ----- entities -----

    def test_store_and_get_extracted_order_id(self, phone: str, cleanup):
        ConversationMemory.store_extracted_entity(
            phone, "order_id", "157955", 0.95, "regex"
        )
        assert ConversationMemory.get_extracted_entity(phone, "order_id") == "157955"

    def test_extracted_entity_min_confidence(self, phone: str, cleanup):
        ConversationMemory.store_extracted_entity(
            phone, "order_id", "157955", 0.5, "regex"
        )
        assert (
            ConversationMemory.get_extracted_entity(
                phone, "order_id", min_confidence=0.7
            )
            is None
        )

    # ----- verification -----

    def test_store_and_get_verification(self, phone: str, cleanup):
        ConversationMemory.store_verification(phone, "4")
        assert ConversationMemory.get_verification(phone) == "4"

    def test_verification_ttl(self, phone: str, cleanup):
        ConversationMemory.store_verification(phone, "4")
        # Use ConversationMemory._r() so we resolve patched _get_redis on the module.
        r = ConversationMemory._r()
        assert r is not None
        key = ConversationMemory.REDIS_KEYS["verification"].format(phone=phone)
        ttl = r.ttl(key)
        assert ttl > 0
        assert ttl <= ConversationMemory.configured_ttl_seconds() + 5

    # ----- context window -----

    def test_context_window_stores_messages(self, phone: str, cleanup):
        ConversationMemory.add_to_context_window(
            phone, "user", "Hello", intent="greeting"
        )
        ConversationMemory.add_to_context_window(
            phone, "assistant", "Hi!", intent="greeting_response"
        )
        window = ConversationMemory.get_context_window(phone)
        assert len(window) == 2
        assert window[0]["role"] == "user"
        assert window[0]["intent"] == "greeting"

    def test_context_window_max_size(self, phone: str, cleanup):
        for i in range(15):
            ConversationMemory.add_to_context_window(phone, "user", f"Message {i}")
        window = ConversationMemory.get_context_window(phone)
        max_msgs = ConversationMemory.MAX_CONTEXT_MESSAGES * 2
        assert len(window) <= max_msgs

    # ----- batch -----

    def test_get_all_context_batch(self, phone: str, cleanup):
        ConversationMemory.store_pending_intent(
            phone, "dropshipping", "how_it_works", "test", 0.85
        )
        ConversationMemory.store_extracted_entity(
            phone, "order_id", "157955", 0.95, "regex"
        )
        ConversationMemory.store_verification(phone, "4")
        ctx = ConversationMemory.get_all_context(phone)
        assert ctx["pending_intent"] is not None
        assert ctx["extracted_order_id"] is not None
        assert ctx["verification"] is not None
        assert ctx["is_verified"] is True

    # ----- clear -----

    def test_clear_all_removes_all_keys(self, phone: str, cleanup):
        ConversationMemory.store_pending_intent(
            phone, "dropshipping", "how_it_works", "test", 0.85
        )
        ConversationMemory.store_extracted_entity(
            phone, "order_id", "157955", 0.95, "regex"
        )
        ConversationMemory.store_verification(phone, "4")
        ConversationMemory.clear_all(phone)
        ctx = ConversationMemory.get_all_context(phone)
        assert ctx["pending_intent"] is None
        assert ctx["extracted_order_id"] is None
        assert ctx["verification"] is None
