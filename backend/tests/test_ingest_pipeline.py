"""Tests for the async ingestion pipeline: DSN cache, backpressure, endpoints, worker."""
import uuid

import pytest


# ── DSN snapshot cache ──────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _clear_dsn_cache():
    from app.services import ingest as ingest_service
    ingest_service.clear_dsn_cache()
    yield
    ingest_service.clear_dsn_cache()


def _snapshot(slug="cache-proj"):
    from app.services.ingest import ProjectSnapshot
    return ProjectSnapshot(id=str(uuid.uuid4()), name="Cache Proj", slug=slug)


async def test_resolve_dsn_caches_positive_lookups(monkeypatch):
    from app.services import ingest as ingest_service

    calls = []
    snap = _snapshot()

    async def _fake_fetch(dsn_key):
        calls.append(dsn_key)
        return snap

    monkeypatch.setattr(ingest_service, "_fetch_project_snapshot", _fake_fetch)

    auth = "Sentry sentry_key=aabbccdd, sentry_version=7"
    first = await ingest_service.resolve_dsn(auth, {})
    second = await ingest_service.resolve_dsn(auth, {})

    assert first == snap and second == snap
    assert calls == ["aabbccdd"]  # second hit served from cache


async def test_resolve_dsn_caches_negative_lookups(monkeypatch):
    from app.services import ingest as ingest_service

    calls = []

    async def _fake_fetch(dsn_key):
        calls.append(dsn_key)
        return None

    monkeypatch.setattr(ingest_service, "_fetch_project_snapshot", _fake_fetch)

    assert await ingest_service.resolve_dsn("", {"sentry_key": "badbadba"}) is None
    assert await ingest_service.resolve_dsn("", {"sentry_key": "badbadba"}) is None
    assert calls == ["badbadba"]  # invalid key cached too


# ── Queue-depth backpressure ────────────────────────────────────────

async def test_ingest_queue_full_fails_open(monkeypatch):
    """If the depth check itself errors, ingestion must NOT be blocked."""
    from app.services import ingest as ingest_service

    async def _boom(queue):
        raise ConnectionError("redis down")

    monkeypatch.setattr(ingest_service, "_queue_depth", _boom)
    ingest_service.clear_depth_cache()
    assert await ingest_service.ingest_queue_full() is False


async def test_ingest_queue_full_above_cap(monkeypatch):
    from app.config import settings
    from app.services import ingest as ingest_service

    async def _deep(queue):
        assert queue == "ingest"
        return settings.INGEST_QUEUE_MAX + 1

    monkeypatch.setattr(ingest_service, "_queue_depth", _deep)
    ingest_service.clear_depth_cache()
    assert await ingest_service.ingest_queue_full() is True


async def test_resolve_dsn_rejects_oversized_keys(monkeypatch):
    from app.services import ingest as ingest_service

    async def _fake_fetch(dsn_key):
        raise AssertionError("oversized key must not reach the DB")

    monkeypatch.setattr(ingest_service, "_fetch_project_snapshot", _fake_fetch)
    huge_key = "a" * 500
    assert await ingest_service.resolve_dsn("", {"sentry_key": huge_key}) is None
    assert huge_key not in ingest_service._DSN_CACHE


async def test_dsn_cache_is_bounded(monkeypatch):
    from app.services import ingest as ingest_service

    async def _fake_fetch(dsn_key):
        return None

    monkeypatch.setattr(ingest_service, "_fetch_project_snapshot", _fake_fetch)
    monkeypatch.setattr(ingest_service, "_DSN_CACHE_MAX", 5)

    for i in range(7):
        await ingest_service.resolve_dsn("", {"sentry_key": f"flood{i}"})

    assert len(ingest_service._DSN_CACHE) <= 5
