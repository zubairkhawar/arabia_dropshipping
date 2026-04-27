"""
Unit tests for the WhatsApp webhook batch parser (TC9 fix).

Meta sometimes packs multiple messages from the same customer into a single
webhook delivery. The previous parser returned only the first one; the new
`_parse_meta_whatsapp_inbound_all` returns all of them in order.
"""
from __future__ import annotations

from typing import Any, Dict, List

import pytest

from services.messaging_service.inbound_parser import (
    parse_meta_whatsapp_inbound as _parse_meta_whatsapp_inbound,
    parse_meta_whatsapp_inbound_all as _parse_meta_whatsapp_inbound_all,
)


def _wrap(messages: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Build a minimal Meta webhook payload with the given inbound messages."""
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WABA_ID",
                "changes": [
                    {
                        "value": {
                            "contacts": [{"profile": {"name": "Test User"}}],
                            "messages": messages,
                        },
                        "field": "messages",
                    }
                ],
            }
        ],
    }


def _text_msg(wa_id: str, body: str) -> Dict[str, Any]:
    return {
        "from": "923001234567",
        "id": wa_id,
        "timestamp": "1700000000",
        "type": "text",
        "text": {"body": body},
    }


class TestBatchParser:
    def test_single_text_message_parses(self) -> None:
        payload = _wrap([_text_msg("wamid.1", "Hello")])
        items = _parse_meta_whatsapp_inbound_all(payload)
        assert len(items) == 1
        assert items[0]["text"] == "Hello"
        assert items[0]["wa_message_id"] == "wamid.1"

    def test_two_text_messages_in_batch_both_parsed(self) -> None:
        """TC9 — when Meta delivers two messages in one webhook, both must be returned."""
        payload = _wrap([
            _text_msg("wamid.1", "Mujjhay orders ki invoice do"),
            _text_msg("wamid.2", "Meray total orders store k btao"),
        ])
        items = _parse_meta_whatsapp_inbound_all(payload)
        assert len(items) == 2
        assert items[0]["text"] == "Mujjhay orders ki invoice do"
        assert items[1]["text"] == "Meray total orders store k btao"

    def test_order_preserved(self) -> None:
        bodies = ["one", "two", "three", "four"]
        payload = _wrap([_text_msg(f"wamid.{i}", b) for i, b in enumerate(bodies)])
        items = _parse_meta_whatsapp_inbound_all(payload)
        assert [m["text"] for m in items] == bodies

    def test_empty_text_skipped(self) -> None:
        payload = _wrap([
            _text_msg("wamid.1", ""),
            _text_msg("wamid.2", "real message"),
        ])
        items = _parse_meta_whatsapp_inbound_all(payload)
        assert len(items) == 1
        assert items[0]["text"] == "real message"

    def test_non_whatsapp_payload_returns_empty(self) -> None:
        assert _parse_meta_whatsapp_inbound_all({"object": "page"}) == []
        assert _parse_meta_whatsapp_inbound_all({}) == []

    def test_missing_required_fields_skipped(self) -> None:
        payload = _wrap([
            {"id": "wamid.no_from", "type": "text", "text": {"body": "x"}},
            {"from": "9230", "type": "text", "text": {"body": "x"}},  # no id
            _text_msg("wamid.ok", "good"),
        ])
        items = _parse_meta_whatsapp_inbound_all(payload)
        assert len(items) == 1
        assert items[0]["text"] == "good"


class TestBackwardCompatWrapper:
    """`_parse_meta_whatsapp_inbound` keeps returning the first message only."""

    def test_returns_first_message(self) -> None:
        payload = _wrap([
            _text_msg("wamid.1", "first"),
            _text_msg("wamid.2", "second"),
        ])
        item = _parse_meta_whatsapp_inbound(payload)
        assert item is not None
        assert item["text"] == "first"

    def test_returns_none_when_empty(self) -> None:
        assert _parse_meta_whatsapp_inbound({"object": "page"}) is None
