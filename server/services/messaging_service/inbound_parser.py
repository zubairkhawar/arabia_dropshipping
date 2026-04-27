"""
Pure-Python parser for Meta WhatsApp Cloud webhook payloads.

Lives outside `api.py` so it can be tested without pulling in FastAPI / SQLAlchemy /
auth dependencies.  Imported by `api.py` and re-exported there for backward compatibility.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def parse_one_meta_message(
    msg: Dict[str, Any], contact_name: Optional[str]
) -> Optional[Dict[str, Any]]:
    """Parse a single Meta message dict into our canonical inbound format."""
    from_phone = msg.get("from")
    wa_message_id = msg.get("id")
    if not from_phone or not wa_message_id:
        return None
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
            return None
        return {**base, "kind": "text", "text": text}
    if mtype == "image":
        img = msg.get("image") or {}
        mid = img.get("id")
        if not mid:
            return None
        cap = (img.get("caption") or "") if isinstance(img.get("caption"), str) else ""
        return {**base, "kind": "image", "media_id": str(mid), "caption": cap}
    if mtype == "audio":
        au = msg.get("audio") or {}
        mid = au.get("id")
        if not mid:
            return None
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
    if mtype == "video":
        vid = msg.get("video") or {}
        mid = vid.get("id")
        if not mid:
            return None
        cap = (vid.get("caption") or "") if isinstance(vid.get("caption"), str) else ""
        return {
            **base,
            "kind": "video",
            "media_id": str(mid),
            "caption": cap,
        }
    if mtype == "document":
        doc = msg.get("document") or {}
        mid = doc.get("id")
        if not mid:
            return None
        cap = (doc.get("caption") or "") if isinstance(doc.get("caption"), str) else ""
        return {
            **base,
            "kind": "document",
            "media_id": str(mid),
            "filename": str(doc.get("filename") or "File"),
            "caption": cap,
        }
    if mtype == "reaction":
        rxn = msg.get("reaction") or {}
        target_id = rxn.get("message_id")
        emoji = rxn.get("emoji")
        if not isinstance(target_id, str) or not target_id.strip():
            return None
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
            return None
        return {**base, "kind": "image", "media_id": str(mid), "caption": ""}
    return None


def parse_meta_whatsapp_inbound_all(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Parse Meta webhook into ALL inbound user messages (text / image / audio / video /
    document / reaction / sticker), in delivery order.

    Meta may batch multiple messages in one webhook delivery. Returning only the
    first one (the original `_parse_meta_whatsapp_inbound` behaviour) silently
    dropped follow-up messages from the same customer — observed as TC9.
    """
    out: List[Dict[str, Any]] = []
    if payload.get("object") != "whatsapp_business_account":
        return out
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
                parsed = parse_one_meta_message(msg, contact_name)
                if parsed is not None:
                    out.append(parsed)
    return out


def parse_meta_whatsapp_inbound(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Backward-compat: first inbound user message only."""
    items = parse_meta_whatsapp_inbound_all(payload)
    return items[0] if items else None
