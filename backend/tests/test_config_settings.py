"""The new read-protection / ingest-throttle settings expose the right defaults."""


def test_read_protection_settings_defaults():
    from app.config import Settings

    f = Settings.model_fields
    assert f["STATS_CACHE_TTL"].default == 30
    assert f["INGEST_CONCURRENCY"].default == 4
    assert f["INGEST_RATE_LIMIT"].default is None
    assert f["DB_POOL_SIZE"].default == 10
    assert f["DB_MAX_OVERFLOW"].default == 5
