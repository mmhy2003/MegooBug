"""Tests for the async ingestion pipeline: DSN cache, backpressure, endpoints, worker."""
import json
import time
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


# ── Worker task end-to-end ──────────────────────────────────────────

def test_ingest_event_end_to_end(monkeypatch, db_engine):
    """The real task body against the test DB: creates issue + event rows."""
    import asyncio
    from sqlalchemy import delete, select
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.config import settings as app_settings
    from app.services import ingest as ingest_service
    from app.tasks import ingest_tasks
    from app.models.user import User
    from app.models.project import Project
    from app.models.issue import Issue
    from app.models.event import Event
    from tests.conftest import TEST_URL

    # Point the task machinery at the test DB and reset its cached loop/engine
    monkeypatch.setattr(app_settings, "DATABASE_URL", TEST_URL)
    ingest_tasks._reset_state()
    # Suppress meili/email side-dispatches from process_event
    monkeypatch.setattr(ingest_service, "_HAS_TASKS", False)

    marker = uuid.uuid4().hex[:12]
    event_id = uuid.uuid4().hex

    async def _setup():
        engine = create_async_engine(TEST_URL)
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory() as db:
            user = User(email=f"ing-{marker}@example.com", name="Ing", password_hash="x")
            db.add(user)
            await db.flush()
            project = Project(
                name=f"Ingest {marker}", slug=f"ingest-{marker}",
                dsn_public_key=uuid.uuid4().hex, created_by=user.id,
            )
            db.add(project)
            await db.commit()
            pid = str(project.id)
        await engine.dispose()
        return pid

    async def _assert_and_cleanup(pid):
        engine = create_async_engine(TEST_URL)
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory() as db:
            issue = (await db.execute(
                select(Issue).where(Issue.project_id == uuid.UUID(pid))
            )).scalars().first()
            assert issue is not None
            assert "IngestBoom" in issue.title
            stored = (await db.execute(
                select(Event).where(Event.event_id == event_id)
            )).scalar_one_or_none()
            assert stored is not None
            # Cleanup: cascade removes issue + event; user removed too
            await db.execute(delete(Project).where(Project.id == uuid.UUID(pid)))
            await db.execute(delete(User).where(User.email == f"ing-{marker}@example.com"))
            await db.commit()
        await engine.dispose()

    # Use an explicit loop rather than asyncio.run() so we never call
    # set_event_loop / set_event_loop(None) — which would clobber the
    # session-scoped loop that pytest-asyncio relies on for later async tests.
    _helper = asyncio.new_event_loop()
    try:
        pid = _helper.run_until_complete(_setup())
    finally:
        _helper.close()

    try:
        result = ingest_tasks.ingest_event.run(pid, {
            "event_id": event_id,
            "message": f"IngestBoom {marker}",
            "timestamp": time.time(),
        })
        assert result == event_id

        # Verify warm-loop reuse: a second event through the same cached machinery
        second_eid = uuid.uuid4().hex
        result2 = ingest_tasks.ingest_event.run(pid, {
            "event_id": second_eid,
            "message": f"IngestBoom again {marker}",
            "timestamp": time.time(),
        })
        assert result2 == second_eid

        _cleanup = asyncio.new_event_loop()
        try:
            _cleanup.run_until_complete(_assert_and_cleanup(pid))
        finally:
            _cleanup.close()
    finally:
        ingest_tasks._reset_state()


def test_ingest_event_drops_missing_project(monkeypatch, db_engine):
    from app.config import settings as app_settings
    from app.tasks import ingest_tasks
    from tests.conftest import TEST_URL

    monkeypatch.setattr(app_settings, "DATABASE_URL", TEST_URL)
    ingest_tasks._reset_state()
    try:
        result = ingest_tasks.ingest_event.run(str(uuid.uuid4()), {"message": "orphan"})
        assert result is None
    finally:
        ingest_tasks._reset_state()


# ── Thin endpoints ──────────────────────────────────────────────────


@pytest.fixture
async def api_client():
    from httpx import ASGITransport, AsyncClient
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


def _patch_pipeline(monkeypatch, snapshot, queue_full=False):
    from app.api import ingest as ingest_api

    captured = []

    async def _resolve(auth_header, query_params, envelope_header=None):
        return snapshot

    async def _full():
        return queue_full

    monkeypatch.setattr(ingest_api, "resolve_dsn", _resolve)
    monkeypatch.setattr(ingest_api, "ingest_queue_full", _full)
    monkeypatch.setattr(
        ingest_api.ingest_event, "delay",
        lambda project_id, event_data: captured.append((project_id, event_data)),
    )
    return captured


async def test_store_endpoint_enqueues_and_returns_200(api_client, monkeypatch):
    snap = _snapshot()
    captured = _patch_pipeline(monkeypatch, snap)

    eid = uuid.uuid4().hex
    resp = await api_client.post(
        "/api/1/store/?sentry_key=aabbccdd",
        json={"event_id": eid, "message": "queued!"},
    )

    assert resp.status_code == 200
    assert resp.json() == {"id": eid}
    assert len(captured) == 1
    project_id, event_data = captured[0]
    assert project_id == snap.id
    assert event_data["message"] == "queued!"


async def test_store_endpoint_401_unknown_dsn(api_client, monkeypatch):
    _patch_pipeline(monkeypatch, snapshot=None)
    resp = await api_client.post("/api/1/store/?sentry_key=bad", json={"message": "x"})
    assert resp.status_code == 401


async def test_store_endpoint_413_oversized(api_client, monkeypatch):
    from app.config import settings
    snap = _snapshot()
    _patch_pipeline(monkeypatch, snap)
    monkeypatch.setattr(settings, "MAX_EVENT_BYTES", 50)

    resp = await api_client.post(
        "/api/1/store/?sentry_key=aabbccdd",
        json={"message": "Y" * 200},
    )
    assert resp.status_code == 413


async def test_store_endpoint_429_when_queue_full(api_client, monkeypatch):
    snap = _snapshot()
    _patch_pipeline(monkeypatch, snap, queue_full=True)

    resp = await api_client.post(
        "/api/1/store/?sentry_key=aabbccdd", json={"message": "x"},
    )
    assert resp.status_code == 429
    assert resp.headers.get("retry-after") == "30"


async def test_store_endpoint_503_when_broker_down(api_client, monkeypatch):
    from app.api import ingest as ingest_api
    snap = _snapshot()
    _patch_pipeline(monkeypatch, snap)

    def _broker_down(project_id, event_data):
        raise ConnectionError("redis unreachable")

    monkeypatch.setattr(ingest_api.ingest_event, "delay", _broker_down)
    resp = await api_client.post(
        "/api/1/store/?sentry_key=aabbccdd", json={"message": "x"},
    )
    assert resp.status_code == 503


async def test_envelope_endpoint_enqueues_each_event(api_client, monkeypatch):
    snap = _snapshot()
    captured = _patch_pipeline(monkeypatch, snap)

    eid = uuid.uuid4().hex
    envelope = (
        json.dumps({"dsn": "http://aabbccdd@localhost/1"}) + "\n"
        + json.dumps({"type": "event"}) + "\n"
        + json.dumps({"event_id": eid, "message": "from envelope"}) + "\n"
    )
    resp = await api_client.post(
        "/api/1/envelope/",
        content=envelope.encode(),
        headers={"Content-Type": "application/x-sentry-envelope"},
    )

    assert resp.status_code == 200
    assert len(captured) == 1
    assert captured[0][1]["event_id"] == eid
