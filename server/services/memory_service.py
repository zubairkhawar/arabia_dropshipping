"""
Short-term conversation memory (Redis/Valkey) for the customer bot.

Long-term history remains in PostgreSQL (messages) and optional OpenAI features elsewhere;
this module does not replace DB-backed thread history.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from config import settings

logger = logging.getLogger(__name__)

try:
    import redis  # type: ignore
except ImportError:  # pragma: no cover
    redis = None  # type: ignore

_redis_client: Any = None
_redis_failed: bool = False


def _ttl_seconds() -> int:
    days = int(getattr(settings, "redis_ttl_days", 3) or 3)
    return max(60, days * 24 * 60 * 60)


def _get_redis():
    """Lazy singleton; returns None if disabled or unreachable."""
    global _redis_client, _redis_failed
    if not bool(getattr(settings, "conversation_memory_enabled", True)):
        return None
    if redis is None:
        return None
    if _redis_failed:
        return None
    if _redis_client is not None:
        return _redis_client
    try:
        client = redis.from_url(settings.redis_url, decode_responses=True)
        client.ping()
        _redis_client = client
        return _redis_client
    except Exception as exc:  # noqa: BLE001
        logger.warning("Redis/Valkey unavailable (%s); conversation memory disabled", exc)
        _redis_failed = True
        return None


def normalize_memory_scope_id(
    phone: Optional[str],
    conversation: Optional[Any] = None,
) -> Optional[str]:
    """
    Stable key segment for mem:{id}:... keys.
    Prefer E.164 digits from phone; else conversation id for web without phone.
    """
    if phone:
        digits = "".join(c for c in str(phone) if c.isdigit())
        if len(digits) >= 8:
            return digits
        if str(phone).strip():
            return str(phone).strip()[:64]
    if conversation is not None and getattr(conversation, "id", None):
        return f"conv:{int(conversation.id)}"
    return None


class ConversationMemory:
    """Production-grade short-term memory with Redis."""

    REDIS_KEYS = {
        "pending_intent": "mem:{phone}:pending_intent",
        "intent_queue": "mem:{phone}:intent_queue",
        "last_intent": "mem:{phone}:last_intent",
        "extracted_order_id": "mem:{phone}:extracted_order_id",
        "extracted_country": "mem:{phone}:extracted_country",
        "extracted_product_id": "mem:{phone}:extracted_product_id",
        "verification": "mem:{phone}:verification",
        "context_window": "mem:{phone}:context_window",
        "last_summary": "mem:{phone}:last_summary",
        "bot_customer_kind": "mem:{phone}:bot_customer_kind",
    }

    MAX_CONTEXT_MESSAGES = 5
    MAX_INTENT_QUEUE = 3

    @classmethod
    def configured_ttl_seconds(cls) -> int:
        """TTL seconds applied to memory keys (from settings.redis_ttl_days)."""
        return _ttl_seconds()

    @classmethod
    def _ttl(cls) -> int:
        return _ttl_seconds()

    @classmethod
    def _r(cls):
        return _get_redis()

    # ----- pending intent -----

    @classmethod
    def store_pending_intent(
        cls,
        phone: str,
        topic: str,
        intent_type: str,
        original_question: str,
        confidence: float = 0.7,
        *,
        queue_previous: bool = True,
    ) -> None:
        r = cls._r()
        if not r:
            return
        if queue_previous:
            existing = cls.get_pending_intent(phone)
            if existing:
                old_topic = (existing.get("topic") or "").strip().lower()
                new_topic = (topic or "").strip().lower()
                # Queue only when switching to a different topic (same topic updates pending in place).
                if old_topic != new_topic:
                    cls.add_to_intent_queue(
                        phone,
                        str(existing.get("topic") or "general"),
                        str(existing.get("intent_type") or "general_question"),
                        str(existing.get("original_question") or ""),
                    )
        pending_intent = {
            "topic": topic,
            "intent_type": intent_type,
            "original_question": original_question,
            "confidence": confidence,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        key = cls.REDIS_KEYS["pending_intent"].format(phone=phone)
        try:
            r.setex(key, cls._ttl(), json.dumps(pending_intent))
            logger.info("memory: stored pending_intent %s for %s", intent_type, phone[:8])
        except Exception as exc:  # noqa: BLE001
            logger.warning("memory: store_pending_intent failed: %s", exc)

    @classmethod
    def get_pending_intent(cls, phone: str) -> Optional[Dict[str, Any]]:
        r = cls._r()
        if not r:
            return None
        try:
            key = cls.REDIS_KEYS["pending_intent"].format(phone=phone)
            value = r.get(key)
            if value:
                return json.loads(value)
        except Exception as exc:  # noqa: BLE001
            logger.warning("memory: get_pending_intent failed: %s", exc)
        return None

    @classmethod
    def clear_pending_intent(cls, phone: str, *, promote_from_queue: bool = False) -> None:
        r = cls._r()
        if not r:
            return
        try:
            r.delete(cls.REDIS_KEYS["pending_intent"].format(phone=phone))
        except Exception as exc:  # noqa: BLE001
            logger.warning("memory: clear_pending_intent failed: %s", exc)
        if promote_from_queue:
            nxt = cls.get_next_intent_from_queue(phone)
            if nxt and isinstance(nxt, dict):
                cls.store_pending_intent(
                    phone,
                    str(nxt.get("topic") or "general"),
                    str(nxt.get("intent_type") or "general_question"),
                    str(nxt.get("original_question") or ""),
                    confidence=0.75,
                    queue_previous=False,
                )

    @classmethod
    def is_relevant_to_pending_intent(cls, phone: str, message: str) -> bool:
        pending = cls.get_pending_intent(phone)
        if not pending:
            return False
        m = (message or "").strip().lower()
        topic_changes = (
            "actually",
            "wait",
            "instead",
            "never mind",
            "nevermind",
            "change topic",
            "not that",
        )
        if any(p in m for p in topic_changes):
            cls.clear_pending_intent(phone, promote_from_queue=False)
            return False
        current = (pending.get("topic") or "").lower()
        other_topics = (
            "shipping",
            "returns",
            "orders",
            "payments",
            "agency",
            "fulfillment",
            "3pl",
            "invoice",
        )
        for t in other_topics:
            if t != current and t in m and len(m) > 8:
                cls.clear_pending_intent(phone, promote_from_queue=False)
                return False
        if m in {"1", "2", "3", "yes", "no", "y", "n", "haan", "nahi"}:
            return True
        return True

    # ----- intent queue -----

    @classmethod
    def add_to_intent_queue(
        cls,
        phone: str,
        topic: str,
        intent_type: str,
        original_question: str,
    ) -> None:
        r = cls._r()
        if not r:
            return
        key = cls.REDIS_KEYS["intent_queue"].format(phone=phone)
        try:
            raw = r.get(key)
            queue: List[Dict[str, Any]] = json.loads(raw) if raw else []
            queue.append(
                {
                    "topic": topic,
                    "intent_type": intent_type,
                    "original_question": original_question,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )
            max_q = int(getattr(settings, "memory_max_intent_queue", cls.MAX_INTENT_QUEUE) or 3)
            if len(queue) > max_q:
                queue = queue[-max_q:]
            r.setex(key, cls._ttl(), json.dumps(queue))
        except Exception as exc:  # noqa: BLE001
            logger.warning("memory: add_to_intent_queue failed: %s", exc)

    @classmethod
    def get_intent_queue(cls, phone: str) -> List[Dict[str, Any]]:
        r = cls._r()
        if not r:
            return []
        key = cls.REDIS_KEYS["intent_queue"].format(phone=phone)
        try:
            raw = r.get(key)
            if not raw:
                return []
            q = json.loads(raw)
            return q if isinstance(q, list) else []
        except Exception as exc:  # noqa: BLE001
            logger.warning("memory: get_intent_queue failed: %s", exc)
        return []

    @classmethod
    def get_next_intent_from_queue(cls, phone: str) -> Optional[Dict[str, Any]]:
        r = cls._r()
        if not r:
            return None
        key = cls.REDIS_KEYS["intent_queue"].format(phone=phone)
        try:
            raw = r.get(key)
            if not raw:
                return None
            queue: List[Dict[str, Any]] = json.loads(raw)
            if not queue:
                return None
            nxt = queue.pop(0)
            if queue:
                r.setex(key, cls._ttl(), json.dumps(queue))
            else:
                r.delete(key)
            return nxt
        except Exception as exc:  # noqa: BLE001
            logger.warning("memory: get_next_intent_from_queue failed: %s", exc)
        return None

    # ----- entities -----

    @classmethod
    def store_extracted_entity(
        cls,
        phone: str,
        entity_type: str,
        value: str,
        confidence: float,
        source: str,
    ) -> None:
        r = cls._r()
        if not r:
            return
        entity = {
            "value": value,
            "confidence": confidence,
            "source": source,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        key_map = {
            "order_id": cls.REDIS_KEYS["extracted_order_id"],
            "country": cls.REDIS_KEYS["extracted_country"],
            "product_id": cls.REDIS_KEYS["extracted_product_id"],
        }
        if entity_type not in key_map:
            return
        key = key_map[entity_type].format(phone=phone)
        try:
            r.setex(key, cls._ttl(), json.dumps(entity))
        except Exception as exc:  # noqa: BLE001
            logger.warning("memory: store_extracted_entity failed: %s", exc)

    @classmethod
    def get_extracted_entity(
        cls,
        phone: str,
        entity_type: str,
        min_confidence: Optional[float] = None,
    ) -> Optional[str]:
        r = cls._r()
        if not r:
            return None
        if min_confidence is None:
            min_confidence = float(getattr(settings, "memory_min_entity_confidence", 0.7) or 0.7)
        key_map = {
            "order_id": cls.REDIS_KEYS["extracted_order_id"],
            "country": cls.REDIS_KEYS["extracted_country"],
            "product_id": cls.REDIS_KEYS["extracted_product_id"],
        }
        if entity_type not in key_map:
            return None
        key = key_map[entity_type].format(phone=phone)
        try:
            raw = r.get(key)
            if not raw:
                return None
            entity = json.loads(raw)
            if float(entity.get("confidence", 0)) >= min_confidence:
                return str(entity.get("value") or "").strip() or None
        except Exception as exc:  # noqa: BLE001
            logger.warning("memory: get_extracted_entity failed: %s", exc)
        return None

    # ----- last intent -----

    @classmethod
    def store_last_intent(cls, phone: str, intent: str) -> None:
        r = cls._r()
        if not r:
            return
        try:
            r.setex(
                cls.REDIS_KEYS["last_intent"].format(phone=phone),
                cls._ttl(),
                intent,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("memory: store_last_intent failed: %s", exc)

    @classmethod
    def get_last_intent(cls, phone: str) -> Optional[str]:
        r = cls._r()
        if not r:
            return None
        try:
            return r.get(cls.REDIS_KEYS["last_intent"].format(phone=phone))
        except Exception as exc:  # noqa: BLE001
            logger.warning("memory: get_last_intent failed: %s", exc)
        return None

    # ----- verification -----

    @classmethod
    def store_verification(cls, phone: str, seller_id: str) -> None:
        r = cls._r()
        if not r:
            return
        now = datetime.now(timezone.utc)
        expires = now + timedelta(seconds=cls._ttl())
        verification = {
            "seller_id": str(seller_id).strip(),
            "verified_at": now.isoformat(),
            "expires_at": expires.isoformat(),
        }
        key = cls.REDIS_KEYS["verification"].format(phone=phone)
        try:
            r.setex(key, cls._ttl(), json.dumps(verification))
        except Exception as exc:  # noqa: BLE001
            logger.warning("memory: store_verification failed: %s", exc)

    @classmethod
    def get_verification(cls, phone: str) -> Optional[str]:
        r = cls._r()
        if not r:
            return None
        try:
            raw = r.get(cls.REDIS_KEYS["verification"].format(phone=phone))
            if raw:
                data = json.loads(raw)
                return str(data.get("seller_id") or "").strip() or None
        except Exception as exc:  # noqa: BLE001
            logger.warning("memory: get_verification failed: %s", exc)
        return None

    @classmethod
    def is_verification_expired(cls, phone: str) -> bool:
        return cls.get_verification(phone) is None

    # ----- context window -----

    @classmethod
    def add_to_context_window(
        cls,
        phone: str,
        role: str,
        content: str,
        intent: Optional[str] = None,
        **metadata: Any,
    ) -> None:
        r = cls._r()
        if not r:
            return
        key = cls.REDIS_KEYS["context_window"].format(phone=phone)
        max_pairs = int(getattr(settings, "memory_max_context_messages", cls.MAX_CONTEXT_MESSAGES) or 5)
        max_messages = max_pairs * 2
        try:
            raw = r.get(key)
            window: List[Dict[str, Any]] = json.loads(raw) if raw else []
            msg: Dict[str, Any] = {
                "role": role,
                "content": (content or "")[:500],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            msg.update({k: v for k, v in metadata.items() if k in ("has_order_id", "has_country")})
            if intent:
                msg["intent"] = intent
            window.append(msg)
            if len(window) > max_messages:
                window = window[-max_messages:]
            r.setex(key, cls._ttl(), json.dumps(window))
        except Exception as exc:  # noqa: BLE001
            logger.warning("memory: add_to_context_window failed: %s", exc)

    @classmethod
    def get_context_window(cls, phone: str) -> List[Dict[str, Any]]:
        r = cls._r()
        if not r:
            return []
        try:
            raw = r.get(cls.REDIS_KEYS["context_window"].format(phone=phone))
            if raw:
                return json.loads(raw)
        except Exception as exc:  # noqa: BLE001
            logger.warning("memory: get_context_window failed: %s", exc)
        return []

    # ----- summary -----

    @classmethod
    def store_last_summary(cls, phone: str, summary: str) -> None:
        r = cls._r()
        if not r:
            return
        try:
            r.setex(
                cls.REDIS_KEYS["last_summary"].format(phone=phone),
                cls._ttl(),
                (summary or "")[:200],
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("memory: store_last_summary failed: %s", exc)

    @classmethod
    def get_last_summary(cls, phone: str) -> Optional[str]:
        r = cls._r()
        if not r:
            return None
        try:
            return r.get(cls.REDIS_KEYS["last_summary"].format(phone=phone))
        except Exception as exc:  # noqa: BLE001
            logger.warning("memory: get_last_summary failed: %s", exc)
        return None

    @classmethod
    def store_bot_customer_kind(cls, phone: str, kind: str) -> None:
        r = cls._r()
        if not r:
            return
        k = (kind or "").strip().lower()
        if k not in ("new", "existing"):
            return
        try:
            r.setex(
                cls.REDIS_KEYS["bot_customer_kind"].format(phone=phone),
                cls._ttl(),
                k,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("memory: store_bot_customer_kind failed: %s", exc)

    @classmethod
    def get_bot_customer_kind(cls, phone: str) -> Optional[str]:
        r = cls._r()
        if not r:
            return None
        try:
            raw = r.get(cls.REDIS_KEYS["bot_customer_kind"].format(phone=phone))
            if not raw:
                return None
            k = str(raw).strip().lower()
            return k if k in ("new", "existing") else None
        except Exception as exc:  # noqa: BLE001
            logger.warning("memory: get_bot_customer_kind failed: %s", exc)
        return None

    @classmethod
    def get_all_context(cls, phone: str) -> Dict[str, Any]:
        r = cls._r()
        if not r:
            return cls._empty_context()
        keys = [
            cls.REDIS_KEYS["pending_intent"].format(phone=phone),
            cls.REDIS_KEYS["intent_queue"].format(phone=phone),
            cls.REDIS_KEYS["last_intent"].format(phone=phone),
            cls.REDIS_KEYS["extracted_order_id"].format(phone=phone),
            cls.REDIS_KEYS["extracted_country"].format(phone=phone),
            cls.REDIS_KEYS["extracted_product_id"].format(phone=phone),
            cls.REDIS_KEYS["verification"].format(phone=phone),
            cls.REDIS_KEYS["context_window"].format(phone=phone),
            cls.REDIS_KEYS["last_summary"].format(phone=phone),
        ]
        try:
            values = r.mget(keys)
        except Exception as exc:  # noqa: BLE001
            logger.warning("memory: mget failed: %s", exc)
            return cls._empty_context()

        def _j(i: int) -> Any:
            v = values[i] if i < len(values) else None
            if not v:
                return None
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return None

        ver_raw = values[6] if len(values) > 6 else None
        return {
            "pending_intent": _j(0),
            "intent_queue": _j(1) or [],
            "last_intent": values[2] if len(values) > 2 else None,
            "extracted_order_id": _j(3),
            "extracted_country": _j(4),
            "extracted_product_id": _j(5),
            "verification": _j(6),
            "context_window": _j(7) or [],
            "last_summary": values[8] if len(values) > 8 else None,
            "is_verified": ver_raw is not None,
        }

    @classmethod
    def _empty_context(cls) -> Dict[str, Any]:
        return {
            "pending_intent": None,
            "intent_queue": [],
            "last_intent": None,
            "extracted_order_id": None,
            "extracted_country": None,
            "extracted_product_id": None,
            "verification": None,
            "context_window": [],
            "last_summary": None,
            "is_verified": False,
        }

    @classmethod
    def clear_all(cls, phone: str) -> None:
        r = cls._r()
        if not r:
            return
        keys = [
            cls.REDIS_KEYS[k].format(phone=phone)
            for k in (
                "pending_intent",
                "intent_queue",
                "last_intent",
                "extracted_order_id",
                "extracted_country",
                "extracted_product_id",
                "verification",
                "context_window",
                "last_summary",
                "bot_customer_kind",
            )
        ]
        try:
            r.delete(*keys)
            logger.info("memory: cleared all keys for scope %s", phone[:16])
        except Exception as exc:  # noqa: BLE001
            logger.warning("memory: clear_all failed: %s", exc)

    @classmethod
    def health_check(cls) -> bool:
        r = cls._r()
        if not r:
            return False
        try:
            return bool(r.ping())
        except Exception:
            return False


def record_conversation_turn(
    scope_id: Optional[str],
    user_message: str,
    assistant_reply: str,
    *,
    user_intent: Optional[str] = None,
) -> None:
    """Append one user + assistant turn to Redis context_window (and a short last_summary)."""
    if not scope_id:
        return
    u = (user_message or "").strip()
    r = (assistant_reply or "").strip()
    if u:
        ConversationMemory.add_to_context_window(scope_id, "user", u, intent=user_intent)
    if r:
        ConversationMemory.add_to_context_window(scope_id, "assistant", r)
    if u and r:
        ConversationMemory.store_last_summary(
            scope_id,
            f"{u[:100]} → {r[:100]}",
        )


def format_memory_block_for_prompt(mem: Dict[str, Any]) -> str:
    """Compact block for LLM system prompt."""
    if not mem or not any(
        mem.get(k)
        for k in (
            "pending_intent",
            "intent_queue",
            "last_intent",
            "extracted_order_id",
            "extracted_country",
            "verification",
            "context_window",
            "last_summary",
        )
    ):
        return "None (no Redis memory for this scope)."
    lines = []
    pi = mem.get("pending_intent")
    if isinstance(pi, dict):
        lines.append(
            f"- Pending intent: topic={pi.get('topic')}, type={pi.get('intent_type')}, "
            f"original={pi.get('original_question', '')[:200]}"
        )
    iq = mem.get("intent_queue") or []
    if isinstance(iq, list) and iq:
        lines.append("- Queued intents (address after current pending is resolved):")
        for item in iq[: int(getattr(settings, "memory_max_intent_queue", 3) or 3)]:
            if isinstance(item, dict):
                lines.append(
                    f"  • topic={item.get('topic')}, type={item.get('intent_type')}, "
                    f"original={str(item.get('original_question', ''))[:120]}"
                )
    if mem.get("last_intent"):
        lines.append(f"- Last intent: {mem.get('last_intent')}")
    for label, key in (
        ("Order ID", "extracted_order_id"),
        ("Country", "extracted_country"),
        ("Product ID", "extracted_product_id"),
    ):
        ent = mem.get(key)
        if isinstance(ent, dict) and ent.get("value"):
            lines.append(f"- Known {label}: {ent.get('value')} (confidence {ent.get('confidence')})")
    if mem.get("is_verified") and isinstance(mem.get("verification"), dict):
        lines.append(f"- Redis verification cache: seller_id={mem['verification'].get('seller_id')}")
    if mem.get("last_summary"):
        lines.append(f"- Last summary: {mem.get('last_summary')}")
    cw = mem.get("context_window") or []
    if cw:
        lines.append("- Recent turns (Redis context_window):")
        for m in cw[-6:]:
            if isinstance(m, dict):
                role = m.get("role", "?")
                content = (m.get("content") or "")[:180]
                lines.append(f"  • {role}: {content}")
    return "\n".join(lines) if lines else "None."
