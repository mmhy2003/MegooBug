"""cache_get_json / cache_set_json: round-trip plus fail-open behavior."""
from app.services import pubsub


async def test_cache_get_returns_none_when_pool_uninitialised(monkeypatch):
    # No pool initialised in the test process -> _get_redis() raises -> miss.
    monkeypatch.setattr(pubsub, "_redis_pool", None)
    assert await pubsub.cache_get_json("stats:dashboard:all") is None


async def test_cache_set_is_noop_when_pool_uninitialised(monkeypatch):
    monkeypatch.setattr(pubsub, "_redis_pool", None)
    # Must not raise.
    await pubsub.cache_set_json("k", {"a": 1}, 30)


async def test_cache_round_trip_with_fake_redis(monkeypatch):
    store = {}

    class _FakeRedis:
        async def get(self, key):
            return store.get(key)

        async def set(self, key, value, ex=None):
            store[key] = value

    monkeypatch.setattr(pubsub, "_get_redis", lambda: _FakeRedis())

    await pubsub.cache_set_json("k", {"errors_24h": 7}, 30)
    assert await pubsub.cache_get_json("k") == {"errors_24h": 7}


async def test_cache_get_fails_open_on_redis_error(monkeypatch):
    class _BoomRedis:
        async def get(self, key):
            raise ConnectionError("redis down")

    monkeypatch.setattr(pubsub, "_get_redis", lambda: _BoomRedis())
    assert await pubsub.cache_get_json("k") is None
