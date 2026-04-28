"""WebSocket endpoint for real-time notifications and event streaming.

Route: /ws/notifications

Authentication is done via the `access_token` HTTP-only cookie sent during
the WebSocket handshake (same JWT used by the REST API).

Protocol:
  Server → Client messages:
    {"type": "new_notification", "notification": {...}}
    {"type": "new_event", "project_id": "...", "issue": {...}, "is_new_issue": true}
    {"type": "stats_update", "unresolved_delta": 1, "errors_24h_delta": 1}
    {"type": "ping"}

  Client → Server messages:
    {"action": "subscribe", "channel": "project", "id": "<project_id>"}
    {"action": "unsubscribe", "channel": "project", "id": "<project_id>"}
    {"type": "pong"}
"""
import asyncio
import json
import uuid

import redis.asyncio as aioredis
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.config import settings
from app.database import async_session_factory
from app.models.user import User
from app.services.auth import decode_token
from app.logging import get_logger

logger = get_logger("api.websocket")
router = APIRouter()


async def _authenticate_ws(websocket: WebSocket) -> User | None:
    """Authenticate a WebSocket connection using the JWT cookie."""
    token = websocket.cookies.get("access_token")
    if not token:
        return None

    payload = decode_token(token)
    if payload is None or payload.get("type") != "access":
        return None

    user_id = payload.get("sub")
    if user_id is None:
        return None

    try:
        async with async_session_factory() as session:
            result = await session.execute(
                select(User).where(User.id == uuid.UUID(user_id))
            )
            user = result.scalar_one_or_none()
            if user is None or not user.is_active:
                return None
            return user
    except Exception as e:
        logger.warning("WebSocket auth error: %s", e)
        return None


@router.websocket("/ws/notifications")
async def websocket_notifications(websocket: WebSocket):
    """Real-time notification and event stream."""
    # Authenticate before accepting
    user = await _authenticate_ws(websocket)
    if user is None:
        await websocket.accept()
        await websocket.close(code=4001, reason="Unauthorized")
        return

    await websocket.accept()
    user_id = str(user.id)
    logger.info("WebSocket connected: user=%s", user.email)

    # Create a dedicated Redis connection for this subscriber
    sub_redis: aioredis.Redis = aioredis.from_url(
        settings.REDIS_URL, decode_responses=True
    )
    pubsub = sub_redis.pubsub()

    # Auto-subscribe to user channel + global channel
    user_channel = f"megoobug:user:{user_id}"
    await pubsub.subscribe(user_channel, "megoobug:global")

    # Track project subscriptions
    project_channels: set[str] = set()

    async def _relay_redis_messages():
        """Read from Redis pub/sub and forward to the WebSocket client."""
        try:
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                try:
                    await websocket.send_text(message["data"])
                except Exception:
                    break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug("Redis relay stopped: %s", e)

    async def _heartbeat():
        """Send periodic pings to keep the connection alive."""
        try:
            while True:
                await asyncio.sleep(30)
                await websocket.send_json({"type": "ping"})
        except asyncio.CancelledError:
            pass
        except Exception:
            pass

    # Start background tasks
    relay_task = asyncio.create_task(_relay_redis_messages())
    heartbeat_task = asyncio.create_task(_heartbeat())

    try:
        # Listen for client messages (subscribe/unsubscribe commands)
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            # Handle pong (heartbeat response) — no action needed
            if msg.get("type") == "pong":
                continue

            action = msg.get("action")
            channel_type = msg.get("channel")
            channel_id = msg.get("id")

            if action == "subscribe" and channel_type == "project" and channel_id:
                ch = f"megoobug:project:{channel_id}"
                if ch not in project_channels:
                    await pubsub.subscribe(ch)
                    project_channels.add(ch)
                    logger.debug("User %s subscribed to %s", user.email, ch)

            elif action == "unsubscribe" and channel_type == "project" and channel_id:
                ch = f"megoobug:project:{channel_id}"
                if ch in project_channels:
                    await pubsub.unsubscribe(ch)
                    project_channels.discard(ch)
                    logger.debug("User %s unsubscribed from %s", user.email, ch)

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected: user=%s", user.email)
    except Exception as e:
        logger.warning("WebSocket error: %s", e)
    finally:
        # Cleanup
        relay_task.cancel()
        heartbeat_task.cancel()

        try:
            await relay_task
        except asyncio.CancelledError:
            pass
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass

        await pubsub.unsubscribe()
        await pubsub.aclose()
        await sub_redis.aclose()
