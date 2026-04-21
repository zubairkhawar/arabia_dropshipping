"""
Pytest configuration: test env and fake Redis for memory unit tests.

Keep server imports out of module scope except after env is set.
"""
from __future__ import annotations

import os

# Force test DB before any server module imports .env (pytest loads conftest first).
os.environ["JWT_SECRET_KEY"] = "test-jwt-secret-key-for-pytest-minimum-32-chars"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

import pytest


@pytest.fixture(autouse=True)
def fake_redis_for_memory(monkeypatch):
    """Isolate Redis; ConversationMemory uses this for all unit tests."""
    import fakeredis

    fake = fakeredis.FakeRedis(decode_responses=True)

    monkeypatch.setattr("services.memory_service._get_redis", lambda: fake)
    monkeypatch.setattr("services.memory_service._redis_failed", False)
    yield fake
    fake.flushall()
