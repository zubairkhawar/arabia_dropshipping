#!/usr/bin/env python3
"""
Load-style exercise for ConversationMemory (Redis). Run against a dev Redis only.

  cd server && PYTHONPATH=. python ../scripts/load_test_memory.py --concurrent 20 --iterations 10
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time

_SERVER = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "server"))
if _SERVER not in sys.path:
    sys.path.insert(0, _SERVER)

os.environ.setdefault("JWT_SECRET_KEY", "load-test-memory-placeholder-key")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")


async def simulate_conversation(phone: str, iteration: int) -> bool:
    from services.memory_service import ConversationMemory

    ConversationMemory.store_pending_intent(
        phone, "test", "test", f"test_{iteration}", 0.8, queue_previous=False
    )
    ConversationMemory.store_extracted_entity(
        phone, "order_id", f"{100000 + iteration}", 0.95, "regex"
    )
    ConversationMemory.store_verification(phone, str(iteration % 100))
    ConversationMemory.get_all_context(phone)
    ConversationMemory.add_to_context_window(phone, "user", f"Message {iteration}")
    ConversationMemory.add_to_context_window(phone, "assistant", f"Response {iteration}")
    ConversationMemory.clear_all(phone)
    return True


async def load_test(concurrent: int, iterations: int) -> None:
    print(f"\nLoad test: {concurrent} concurrent x {iterations} iterations")
    print("=" * 50)
    start = time.time()
    successes = 0
    failures = 0
    for i in range(iterations):
        phones = [f"92300123{i:04d}{j:03d}" for j in range(concurrent)]
        tasks = [simulate_conversation(p, i) for p in phones]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for res in results:
            if res is True:
                successes += 1
            else:
                failures += 1
    elapsed = time.time() - start
    total = successes + failures
    print(f"\nResults: ok={successes} fail={failures} time={elapsed:.2f}s ops/s={total / elapsed:.1f}")
    if failures:
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--concurrent", type=int, default=20)
    parser.add_argument("--iterations", type=int, default=10)
    args = parser.parse_args()
    asyncio.run(load_test(args.concurrent, args.iterations))


if __name__ == "__main__":
    main()
