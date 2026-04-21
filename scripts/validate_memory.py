#!/usr/bin/env python3
"""
Post-deploy memory validation (TTL, isolation, batch vs single reads).

Run from repo root:
  pip install -r server/requirements.txt
  cd server && PYTHONPATH=. python ../scripts/validate_memory.py

Or with dev deps + fakeredis (offline smoke):
  pytest tests/test_memory_service.py -q
"""

from __future__ import annotations

import json
import os
import sys
import time

# Resolve server package
_SERVER = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "server"))
if _SERVER not in sys.path:
    sys.path.insert(0, _SERVER)

os.environ.setdefault("JWT_SECRET_KEY", "validate-memory-script-placeholder-key")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")


def main() -> None:
    from services.memory_service import ConversationMemory, _get_redis, _ttl_seconds

    phone = "923001234567"
    phone2 = "923009999999"

    print("Memory validation report\n" + "=" * 50)

    r = _get_redis()
    if not r:
        print("Redis unavailable (CONVERSATION_MEMORY_ENABLED=false or connection failed).")
        print("Set REDIS_URL and ensure Redis/Valkey is reachable.")
        sys.exit(1)

    ttl_cap = _ttl_seconds()
    print("\n1. TTL validation")
    ConversationMemory.clear_all(phone)
    ConversationMemory.store_pending_intent(phone, "test", "test", "test", 0.8)
    k_pending = ConversationMemory.REDIS_KEYS["pending_intent"].format(phone=phone)
    ttl = r.ttl(k_pending)
    assert ttl > 0, f"expected TTL > 0, got {ttl}"
    assert ttl <= ttl_cap + 5, f"TTL {ttl} exceeds configured cap ~{ttl_cap}"
    print(f"   OK pending_intent TTL={ttl} (cap ~{ttl_cap})")

    ConversationMemory.store_verification(phone, "4")
    k_ver = ConversationMemory.REDIS_KEYS["verification"].format(phone=phone)
    ttl_v = r.ttl(k_ver)
    assert ttl_v > 0
    assert ttl_v <= ttl_cap + 5
    print(f"   OK verification TTL={ttl_v}")

    print("\n2. Key isolation")
    ConversationMemory.clear_all(phone)
    ConversationMemory.clear_all(phone2)
    ConversationMemory.store_pending_intent(phone, "test", "test", "test", 0.8)
    ConversationMemory.store_pending_intent(phone2, "test2", "test", "test", 0.8)
    p1 = ConversationMemory.get_pending_intent(phone)
    p2 = ConversationMemory.get_pending_intent(phone2)
    assert p1 and p1.get("topic") == "test"
    assert p2 and p2.get("topic") == "test2"
    print("   OK keys isolated by phone scope")

    print("\n3. JSON round-trip")
    complex_intent = {
        "topic": "dropshipping",
        "intent_type": "how_it_works",
        "original_question": "How does dropshipping work with multiple products?",
        "confidence": 0.85,
        "timestamp": "2026-04-21T11:20:00+00:00",
    }
    r.setex("mem:test:complex", 3600, json.dumps(complex_intent))
    raw = r.get("mem:test:complex")
    retrieved = json.loads(raw)
    assert retrieved["topic"] == "dropshipping"
    assert retrieved["confidence"] == 0.85
    r.delete("mem:test:complex")
    print("   OK complex JSON")

    print("\n4. Batch vs individual reads")
    ConversationMemory.clear_all(phone)
    ConversationMemory.store_pending_intent(phone, "dropshipping", "how_it_works", "x", 0.85)
    ConversationMemory.store_extracted_entity(phone, "order_id", "157955", 0.95, "regex")
    t0 = time.time()
    for _ in range(10):
        ConversationMemory.get_pending_intent(phone)
        ConversationMemory.get_extracted_entity(phone, "order_id")
        ConversationMemory.get_verification(phone)
    t_indiv = time.time() - t0
    t1 = time.time()
    for _ in range(10):
        ConversationMemory.get_all_context(phone)
    t_batch = time.time() - t1
    print(f"   Individual 10x: {t_indiv:.4f}s")
    print(f"   get_all_context 10x: {t_batch:.4f}s")

    ConversationMemory.clear_all(phone)
    ConversationMemory.clear_all(phone2)

    print("\n" + "=" * 50)
    print("All memory validations passed.")
    print("=" * 50)


if __name__ == "__main__":
    main()
