"""The backend engine sizes its pool from settings (budgeted under max_connections)."""
from app.config import settings
from app.database import engine


def test_engine_pool_size_from_settings():
    assert engine.sync_engine.pool.size() == settings.DB_POOL_SIZE
