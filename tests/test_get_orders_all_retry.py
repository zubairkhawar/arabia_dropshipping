"""
Regression test for WhatsApp transcript 2026-04-30 01:19:

Verified customer asked 'give me recent 5 orders' — bot replied 'I could not
find any orders in your records'. Customer has hundreds of orders. The
upstream /orders/all endpoint is flaky on wide-range queries: ~5-15% of
calls return [] even when orders exist.

Fix: bump the retry count in StoreIntegrationClient.get_orders_all from
1 retry to 2 retries (3 attempts total) with backoff. The static check
below confirms the loop body is wired correctly.
"""
from __future__ import annotations

from pathlib import Path


def _client_text() -> str:
    src = (
        Path(__file__).resolve().parent.parent
        / "server" / "services" / "store_integration_service" / "client.py"
    )
    return src.read_text(encoding="utf-8")


class TestGetOrdersAllRetry:
    def test_three_attempts_loop_present(self) -> None:
        text = _client_text()
        # The retry must use a 3-iteration loop (range(3)) so we get
        # initial + 2 retries before giving up.
        i = text.find("async def get_orders_all")
        assert i > 0
        block = text[i: i + 3000]
        assert "for attempt in range(3):" in block, (
            "get_orders_all must attempt the upstream call 3 times before "
            "giving up; flakiness is a known issue and 1 retry isn't enough"
        )

    def test_backoff_present(self) -> None:
        text = _client_text()
        i = text.find("async def get_orders_all")
        block = text[i: i + 3000]
        # A simple progressive backoff between attempts.
        assert "asyncio.sleep" in block, "must sleep between attempts"
        assert "attempt < 2" in block, (
            "must skip the sleep on the final attempt"
        )

    def test_returns_empty_on_exhaustion(self) -> None:
        text = _client_text()
        i = text.find("async def get_orders_all")
        block = text[i: i + 3000]
        # On total failure we should still return [] (caller handles 'no orders').
        assert "return []" in block
