"""
Meta WhatsApp Cloud API webhook helpers for tests.

``parse_meta_whatsapp_inbound`` mirrors ``_parse_meta_whatsapp_inbound`` in
``services.messaging_service.api`` so tests do not import the full API stack.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional


def parse_meta_whatsapp_inbound(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Parse Meta webhook: first inbound user message as text, image, audio, etc.
    Kept in sync with ``_parse_meta_whatsapp_inbound`` in messaging_service.api.
    """
    if payload.get("object") != "whatsapp_business_account":
        return None
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            messages = value.get("messages") or []
            if not messages:
                continue
            contacts = value.get("contacts") or []
            contact_name = None
            if contacts and isinstance(contacts[0], dict):
                profile = contacts[0].get("profile") or {}
                contact_name = profile.get("name")
            for msg in messages:
                from_phone = msg.get("from")
                wa_message_id = msg.get("id")
                if not from_phone or not wa_message_id:
                    continue
                base = {
                    "from_phone": from_phone,
                    "wa_message_id": wa_message_id,
                    "contact_name": contact_name,
                    "timestamp": msg.get("timestamp"),
                }
                mtype = msg.get("type")
                if mtype == "text":
                    text = (msg.get("text") or {}).get("body", "")
                    if not text:
                        continue
                    return {**base, "kind": "text", "text": text}
                if mtype == "image":
                    img = msg.get("image") or {}
                    mid = img.get("id")
                    if not mid:
                        continue
                    cap = (img.get("caption") or "") if isinstance(img.get("caption"), str) else ""
                    return {**base, "kind": "image", "media_id": str(mid), "caption": cap}
                if mtype == "audio":
                    au = msg.get("audio") or {}
                    mid = au.get("id")
                    if not mid:
                        continue
                    dur_raw = au.get("duration")
                    duration_seconds = None
                    if isinstance(dur_raw, (int, float)):
                        duration_seconds = int(dur_raw)
                    elif isinstance(dur_raw, str) and dur_raw.strip().isdigit():
                        duration_seconds = int(dur_raw.strip())
                    return {
                        **base,
                        "kind": "audio",
                        "media_id": str(mid),
                        "duration_seconds": duration_seconds,
                    }
                if mtype == "document":
                    doc = msg.get("document") or {}
                    mid = doc.get("id")
                    if not mid:
                        continue
                    return {
                        **base,
                        "kind": "document",
                        "media_id": str(mid),
                        "filename": str(doc.get("filename") or "File"),
                    }
                if mtype == "reaction":
                    rxn = msg.get("reaction") or {}
                    target_id = rxn.get("message_id")
                    emoji = rxn.get("emoji")
                    if not isinstance(target_id, str) or not target_id.strip():
                        continue
                    if not isinstance(emoji, str):
                        emoji = ""
                    return {
                        **base,
                        "kind": "reaction",
                        "target_wa_message_id": target_id.strip(),
                        "emoji": emoji.strip(),
                    }
                if mtype == "sticker":
                    st = msg.get("sticker") or {}
                    mid = st.get("id")
                    if not mid:
                        continue
                    return {**base, "kind": "image", "media_id": str(mid), "caption": ""}
    return None


def meta_text_message_payload(
    from_phone: str,
    text: str,
    *,
    wa_message_id: str = "wamid.test123",
) -> Dict[str, Any]:
    ts = str(int(time.time()))
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "from": from_phone,
                                    "id": wa_message_id,
                                    "timestamp": ts,
                                    "type": "text",
                                    "text": {"body": text},
                                }
                            ],
                            "contacts": [{"profile": {"name": "Test User"}}],
                        }
                    }
                ]
            }
        ],
    }
