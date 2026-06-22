"""Project trends caching: access check runs before any cache lookup; hits short-circuit."""
import uuid

import pytest
from fastapi import HTTPException

from app.api.v1 import stats
from app.models.user import User
from app.models.project import Project


@pytest.fixture
async def project(db):
    user = User(email=f"trends-{uuid.uuid4().hex[:8]}@example.com", name="T", password_hash="x")
    db.add(user)
    await db.flush()
    proj = Project(
        name="Trend Proj", slug=f"trend-{uuid.uuid4().hex[:8]}",
        dsn_public_key=uuid.uuid4().hex, created_by=user.id,
    )
    db.add(proj)
    await db.flush()
    return proj


async def test_trends_denied_before_cache_lookup(monkeypatch, db, project):
    async def _deny(user, project_id, db_):
        return False

    async def _cache_must_not_run(key):
        raise AssertionError("cache must not be consulted for an unauthorized caller")

    monkeypatch.setattr(stats, "check_project_access", _deny)
    monkeypatch.setattr(stats, "cache_get_json", _cache_must_not_run)

    with pytest.raises(HTTPException) as exc:
        await stats.project_trends(
            slug=project.slug, current_user=object(), db=db, days=7,
        )
    assert exc.value.status_code == 404


async def test_trends_cache_hit_short_circuits(monkeypatch, db, project):
    sentinel = {"project": project.slug, "days": 7, "data": [{"date": "2026-06-20", "count": 5}]}

    async def _allow(user, project_id, db_):
        return True

    async def _hit(key):
        assert key == f"stats:trends:{project.id}:7"
        return sentinel

    async def _no_set(key, value, ttl):
        pass

    monkeypatch.setattr(stats, "check_project_access", _allow)
    monkeypatch.setattr(stats, "cache_get_json", _hit)
    monkeypatch.setattr(stats, "cache_set_json", _no_set)

    result = await stats.project_trends(
        slug=project.slug, current_user=object(), db=db, days=7,
    )
    assert result == sentinel
