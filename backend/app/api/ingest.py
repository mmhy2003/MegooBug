"""Sentry-compatible ingest endpoints.

Accept-and-enqueue: these endpoints validate the DSN (cached), enforce
size and queue-depth limits, queue the event for the celery-ingest
worker, and return immediately. They never touch Postgres on the hot
path and never hold a DB connection while processing — inline processing
caused the 2026-06 pool-exhaustion incident class.
"""
import gzip
import uuid

from fastapi import APIRouter, HTTPException, Request, status

from app.config import settings
from app.services.ingest import (
    ingest_queue_full,
    parse_store_payload,
    parse_envelope_header,
    parse_envelope_payload,
    resolve_dsn,
)
from app.tasks.ingest_tasks import ingest_event
from app.logging import get_logger

logger = get_logger("api.ingest")

router = APIRouter()

_RETRY_AFTER = {"Retry-After": "30"}


def _decompress_body(body: bytes, content_encoding: str | None) -> bytes:
    """Decompress body if gzip/deflate encoded."""
    if content_encoding in ("gzip", "deflate"):
        try:
            return gzip.decompress(body)
        except Exception as e:
            logger.warning("Failed to decompress body: %s", e)
    # Also try auto-detect gzip magic bytes
    if body[:2] == b"\x1f\x8b":
        try:
            return gzip.decompress(body)
        except Exception:
            pass
    return body


def _check_limits_and_body(body: bytes) -> None:
    """Shared 413 guard."""
    if len(body) > settings.MAX_EVENT_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Event payload too large",
        )


async def _backpressure_guard() -> None:
    if await ingest_queue_full():
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Ingestion queue full, retry later",
            headers=_RETRY_AFTER,
        )


def _enqueue(project_id: str, event_data: dict) -> str:
    """Queue one event; returns its event_id. 503 if the broker is unreachable."""
    event_id = event_data.get("event_id") or uuid.uuid4().hex
    event_data["event_id"] = event_id
    try:
        ingest_event.delay(project_id, event_data)
    except Exception as e:
        logger.error("Failed to enqueue event (broker down?): %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Ingestion temporarily unavailable",
        )
    return event_id


@router.post("/{project_id}/store/")
async def store_event(project_id: str, request: Request):
    """Legacy Sentry store endpoint: accept-and-enqueue."""
    auth_header = request.headers.get("x-sentry-auth", "")
    query_params = dict(request.query_params)
    project = await resolve_dsn(auth_header, query_params)
    if project is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid DSN")

    raw_body = await request.body()
    body = _decompress_body(raw_body, request.headers.get("content-encoding"))
    _check_limits_and_body(body)

    event_data = parse_store_payload(body)
    if not event_data:
        logger.warning(
            "Empty store payload (project=%s, raw=%d bytes, decoded=%d bytes)",
            project.slug, len(raw_body), len(body),
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid payload")

    await _backpressure_guard()
    event_id = _enqueue(project.id, event_data)
    return {"id": event_id}


@router.post("/{project_id}/envelope/")
async def store_envelope(project_id: str, request: Request):
    """Sentry envelope endpoint: accept-and-enqueue each event."""
    raw_body = await request.body()
    body = _decompress_body(raw_body, request.headers.get("content-encoding"))
    _check_limits_and_body(body)

    envelope_header, _ = parse_envelope_header(body)

    auth_header = request.headers.get("x-sentry-auth", "")
    query_params = dict(request.query_params)
    project = await resolve_dsn(auth_header, query_params, envelope_header=envelope_header)
    if project is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid DSN")

    events = parse_envelope_payload(body)
    if not events:
        # Envelope may contain non-event items (sessions, etc.) — accept silently
        return {"id": str(uuid.uuid4().hex)}

    await _backpressure_guard()
    last_event_id = None
    for event_data in events:
        last_event_id = _enqueue(project.id, event_data)

    logger.debug("Envelope queued: %d events (project=%s)", len(events), project.slug)
    return {"id": last_event_id or str(uuid.uuid4().hex)}
