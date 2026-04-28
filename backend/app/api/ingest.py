"""Sentry-compatible ingest endpoints.

These endpoints accept events from Sentry SDKs and CLI tools.
Authentication is via DSN public key, not user JWT.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.ingest import (
    validate_dsn,
    parse_store_payload,
    parse_envelope_payload,
    process_event,
)
from app.logging import get_logger

logger = get_logger("api.ingest")

router = APIRouter()


@router.post("/{project_id}/store/")
async def store_event(
    project_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Legacy Sentry store endpoint. Accepts JSON event payload.

    Auth via X-Sentry-Auth header or ?sentry_key= query param.
    """
    # Validate DSN
    auth_header = request.headers.get("x-sentry-auth", "")
    query_params = dict(request.query_params)
    project = await validate_dsn(auth_header, query_params, db)

    if project is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid DSN")

    # Parse body
    body = await request.body()
    event_data = parse_store_payload(body)
    if not event_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid payload")

    # Process
    issue, event = await process_event(project, event_data, db)

    logger.info(
        "Event stored: %s (project=%s, issue=%s)",
        event.event_id, project.slug, issue.id,
    )

    return {"id": event.event_id}


@router.post("/{project_id}/envelope/")
async def store_envelope(
    project_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Sentry envelope endpoint. Accepts newline-delimited envelope format.

    Used by modern Sentry SDKs.
    Auth via X-Sentry-Auth header or ?sentry_key= query param.
    """
    # Validate DSN
    auth_header = request.headers.get("x-sentry-auth", "")
    query_params = dict(request.query_params)
    project = await validate_dsn(auth_header, query_params, db)

    if project is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid DSN")

    # Parse envelope
    body = await request.body()
    events = parse_envelope_payload(body)

    if not events:
        # Envelope may contain non-event items (sessions, etc.) — accept silently
        return {"id": str(uuid.uuid4().hex)}

    # Process each event in the envelope
    last_event_id = None
    for event_data in events:
        issue, event = await process_event(project, event_data, db)
        last_event_id = event.event_id

    logger.info(
        "Envelope processed: %d events (project=%s)",
        len(events), project.slug,
    )

    return {"id": last_event_id or str(uuid.uuid4().hex)}
