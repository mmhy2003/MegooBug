"""Redis pub/sub service for real-time WebSocket event broadcasting.

Channels:
  - megoobug:user:{user_id}       per-user notifications
  - megoobug:project:{project_id} per-project events (new issue / updated issue)
  - megoobug:global               instance-wide stats updates
"""
import json

import redis.asyncio as aioredis

from app.config import settings
from app.logging import get_logger

logger = get_logger("services.pubsub")

_redis_pool: aioredis.Redis | None = None


async def init_redis() -> None:
    """Create the async Redis connection pool.  Call once at app startup."""
    global _redis_pool
    _redis_pool = aioredis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
        max_connections=20,
    )
    logger.info("Redis pub/sub pool initialised (%s)", settings.REDIS_URL)


async def close_redis() -> None:
    """Shut down the Redis pool.  Call once at app shutdown."""
    global _redis_pool
    if _redis_pool is not None:
        await _redis_pool.aclose()
        _redis_pool = None
        logger.info("Redis pub/sub pool closed")


def _get_redis() -> aioredis.Redis:
    if _redis_pool is None:
        raise RuntimeError("Redis pub/sub pool not initialised — call init_redis() first")
    return _redis_pool


# ── Publish helpers ──────────────────────────────────────────────────

async def publish_to_user(user_id: str, payload: dict) -> None:
    """Publish a message to a specific user's channel."""
    try:
        r = _get_redis()
        channel = f"megoobug:user:{user_id}"
        await r.publish(channel, json.dumps(payload))
    except Exception as e:
        logger.warning("Failed to publish to user %s: %s", user_id, e)


async def publish_to_project(project_id: str, payload: dict) -> None:
    """Publish a message to a project's channel."""
    try:
        r = _get_redis()
        channel = f"megoobug:project:{project_id}"
        await r.publish(channel, json.dumps(payload))
    except Exception as e:
        logger.warning("Failed to publish to project %s: %s", project_id, e)


async def publish_global(payload: dict) -> None:
    """Publish a message to the global channel."""
    try:
        r = _get_redis()
        await r.publish("megoobug:global", json.dumps(payload))
    except Exception as e:
        logger.warning("Failed to publish global event: %s", e)
