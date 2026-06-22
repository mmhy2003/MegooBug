"""Dashboard stats caching: key derivation, hit short-circuits DB, miss sets cache."""
import uuid

import pytest

from app.api.v1 import stats
from app.config import settings


def test_dashboard_cache_key_admin_is_stable():
    assert stats._dashboard_cache_key(None) == "stats:dashboard:all"


def test_dashboard_cache_key_is_scope_specific_and_order_independent():
    a, b = uuid.uuid4(), uuid.uuid4()
    k_ab = stats._dashboard_cache_key([a, b])
    k_ba = stats._dashboard_cache_key([b, a])
    assert k_ab == k_ba                       # order-independent
    assert k_ab != stats._dashboard_cache_key([a])   # scope-specific
    assert k_ab != "stats:dashboard:all"      # never collides with admin


async def test_dashboard_cache_hit_skips_db(monkeypatch):
    sentinel = {"total_projects": 7, "errors_24h": 3,
                "unresolved_issues": 1, "active_users": 2}

    async def _hit(key):
        assert key == "stats:dashboard:all"
        return sentinel

    async def _admin_scope(user, db):
        return None

    monkeypatch.setattr(stats, "cache_get_json", _hit)
    monkeypatch.setattr(stats, "get_user_project_ids", _admin_scope)

    class _NoDB:
        async def execute(self, *a, **k):
            raise AssertionError("DB must not be queried on a cache hit")

    result = await stats.dashboard_stats(current_user=object(), db=_NoDB())
    assert result == sentinel


async def test_dashboard_cache_miss_queries_and_sets(monkeypatch, db):
    async def _miss(key):
        return None

    sets = []

    async def _set(key, value, ttl):
        sets.append((key, value, ttl))

    async def _admin_scope(user, db_):
        return None

    monkeypatch.setattr(stats, "cache_get_json", _miss)
    monkeypatch.setattr(stats, "cache_set_json", _set)
    monkeypatch.setattr(stats, "get_user_project_ids", _admin_scope)

    result = await stats.dashboard_stats(current_user=object(), db=db)

    assert set(result) == {"total_projects", "errors_24h",
                           "unresolved_issues", "active_users"}
    assert len(sets) == 1
    key, value, ttl = sets[0]
    assert key == "stats:dashboard:all"
    assert value == result
    assert ttl == settings.STATS_CACHE_TTL
