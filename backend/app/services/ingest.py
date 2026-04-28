"""Sentry-compatible event ingestion service.

Handles DSN authentication, payload parsing (legacy store + envelope format),
event fingerprinting, deduplication, and issue grouping.
"""
import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from urllib.parse import parse_qs

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.models.issue import Issue, IssueStatus, IssueLevel
from app.models.event import Event
from app.logging import get_logger

logger = get_logger("services.ingest")

# Regex to extract DSN public key from X-Sentry-Auth header
# Format: Sentry sentry_key=<key>, sentry_version=7, ...
_SENTRY_AUTH_RE = re.compile(r"sentry_key=([a-f0-9]+)")


async def validate_dsn(
    auth_header: str | None,
    query_params: dict,
    db: AsyncSession,
) -> Project | None:
    """Validate DSN auth from X-Sentry-Auth header or query params.

    Returns the Project if valid, None otherwise.
    """
    dsn_key = None

    # Try X-Sentry-Auth header
    if auth_header:
        match = _SENTRY_AUTH_RE.search(auth_header)
        if match:
            dsn_key = match.group(1)

    # Fallback: query param ?sentry_key=...
    if dsn_key is None:
        dsn_key = query_params.get("sentry_key")

    if dsn_key is None:
        logger.warning("No DSN key found in request")
        return None

    result = await db.execute(
        select(Project).where(Project.dsn_public_key == dsn_key)
    )
    project = result.scalar_one_or_none()
    if project is None:
        logger.warning("Invalid DSN key: %s", dsn_key[:8])

    return project


def parse_store_payload(body: bytes) -> dict:
    """Parse a legacy Sentry store JSON payload."""
    try:
        return json.loads(body)
    except (json.JSONDecodeError, ValueError) as e:
        logger.error("Failed to parse store payload: %s", e)
        return {}


def parse_envelope_payload(body: bytes) -> list[dict]:
    """Parse a Sentry envelope (newline-delimited JSON items).

    Envelope format:
        {header}\n
        {item_header}\n
        {item_payload}\n
        ...

    Returns list of event payloads found in the envelope.
    """
    events = []
    try:
        lines = body.split(b"\n")
        i = 0
        # Skip envelope header
        if len(lines) > 0:
            i = 1

        while i < len(lines):
            # Item header
            if i >= len(lines) or not lines[i].strip():
                i += 1
                continue

            try:
                item_header = json.loads(lines[i])
            except (json.JSONDecodeError, ValueError):
                i += 1
                continue

            item_type = item_header.get("type", "")
            i += 1

            # Item payload
            if i < len(lines) and lines[i].strip():
                try:
                    payload = json.loads(lines[i])
                    if item_type in ("event", "error", "transaction", ""):
                        events.append(payload)
                except (json.JSONDecodeError, ValueError):
                    pass
            i += 1

    except Exception as e:
        logger.error("Failed to parse envelope: %s", e)

    return events


def compute_fingerprint(event_data: dict) -> str:
    """Compute a fingerprint for event grouping.

    Uses exception type + top stack frame (file + function) if available.
    Falls back to message content hash.
    """
    parts = []

    # Try custom fingerprint from event data
    if "fingerprint" in event_data:
        custom = event_data["fingerprint"]
        if isinstance(custom, list) and custom != ["{{ default }}"]:
            return hashlib.sha256(
                "|".join(str(p) for p in custom).encode()
            ).hexdigest()[:32]

    # Extract from exception
    exception = event_data.get("exception", {})
    values = exception.get("values", [])
    if values:
        exc = values[-1]  # most specific exception
        exc_type = exc.get("type", "")
        parts.append(exc_type)

        # Top stack frame
        stacktrace = exc.get("stacktrace", {})
        frames = stacktrace.get("frames", [])
        if frames:
            top = frames[-1]  # most recent frame
            parts.append(top.get("filename", ""))
            parts.append(top.get("function", ""))

    # Fallback to message
    if not parts:
        message = event_data.get("message", "")
        if isinstance(message, dict):
            message = message.get("formatted", message.get("message", ""))
        parts.append(str(message)[:200])

    # Fallback to logentry
    if not parts or parts == [""]:
        logentry = event_data.get("logentry", {})
        parts.append(logentry.get("message", "unknown"))

    fingerprint_str = "|".join(parts)
    return hashlib.sha256(fingerprint_str.encode()).hexdigest()[:32]


def extract_title(event_data: dict) -> str:
    """Extract a human-readable title from event data."""
    # Try exception
    exception = event_data.get("exception", {})
    values = exception.get("values", [])
    if values:
        exc = values[-1]
        exc_type = exc.get("type", "Error")
        exc_value = exc.get("value", "")
        if exc_value:
            return f"{exc_type}: {exc_value}"[:500]
        return exc_type[:500]

    # Try message
    message = event_data.get("message", "")
    if isinstance(message, dict):
        message = message.get("formatted", message.get("message", ""))
    if message:
        return str(message)[:500]

    # Try logentry
    logentry = event_data.get("logentry", {})
    if logentry.get("message"):
        return logentry["message"][:500]

    return "Unknown Error"


def extract_level(event_data: dict) -> IssueLevel:
    """Extract severity level from event data."""
    level_str = event_data.get("level", "error").lower()
    level_map = {
        "fatal": IssueLevel.FATAL,
        "error": IssueLevel.ERROR,
        "warning": IssueLevel.WARNING,
        "info": IssueLevel.INFO,
        "debug": IssueLevel.INFO,
    }
    return level_map.get(level_str, IssueLevel.ERROR)


async def process_event(
    project: Project,
    event_data: dict,
    db: AsyncSession,
) -> tuple[Issue, Event]:
    """Process an incoming event: deduplicate, create/update issue, store event.

    Returns (issue, event) tuple.
    """
    fingerprint = compute_fingerprint(event_data)
    title = extract_title(event_data)
    level = extract_level(event_data)

    # Generate a Sentry-style event ID if not present
    event_id = event_data.get("event_id", str(uuid.uuid4().hex))

    # Event timestamp
    ts = event_data.get("timestamp")
    if ts:
        try:
            if isinstance(ts, (int, float)):
                event_ts = datetime.fromtimestamp(ts, tz=timezone.utc)
            else:
                event_ts = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        except (ValueError, OSError):
            event_ts = datetime.now(timezone.utc)
    else:
        event_ts = datetime.now(timezone.utc)

    # Deduplicate: find existing issue by fingerprint + project
    result = await db.execute(
        select(Issue).where(
            Issue.fingerprint == fingerprint,
            Issue.project_id == project.id,
        )
    )
    issue = result.scalar_one_or_none()

    is_new = issue is None
    is_regression = False

    if issue is None:
        # New issue
        issue = Issue(
            project_id=project.id,
            title=title,
            fingerprint=fingerprint,
            status=IssueStatus.UNRESOLVED,
            level=level,
            first_seen=event_ts,
            last_seen=event_ts,
            event_count=1,
            metadata_=_extract_metadata(event_data),
        )
        db.add(issue)
        await db.flush()
        logger.info("New issue created: %s (project=%s)", title[:60], project.slug)
    else:
        # Existing issue: update counters
        issue.last_seen = event_ts
        issue.event_count += 1

        # Check for regression (resolved issue getting new events)
        if issue.status == IssueStatus.RESOLVED:
            issue.status = IssueStatus.UNRESOLVED
            is_regression = True
            logger.info("Issue regressed: %s (project=%s)", title[:60], project.slug)

    # Store the raw event
    event = Event(
        issue_id=issue.id,
        project_id=project.id,
        event_id=event_id,
        data=event_data,
        timestamp=event_ts,
    )
    db.add(event)
    await db.flush()

    return issue, event


def _extract_metadata(event_data: dict) -> dict:
    """Extract useful metadata from event data for quick display."""
    metadata = {}

    # Browser/OS from contexts
    contexts = event_data.get("contexts", {})
    browser = contexts.get("browser", {})
    if browser.get("name"):
        metadata["browser"] = f"{browser['name']} {browser.get('version', '')}".strip()

    os_ctx = contexts.get("os", {})
    if os_ctx.get("name"):
        metadata["os"] = f"{os_ctx['name']} {os_ctx.get('version', '')}".strip()

    # Runtime
    runtime = contexts.get("runtime", {})
    if runtime.get("name"):
        metadata["runtime"] = f"{runtime['name']} {runtime.get('version', '')}".strip()

    # Environment
    if event_data.get("environment"):
        metadata["environment"] = event_data["environment"]

    # Release
    if event_data.get("release"):
        metadata["release"] = event_data["release"]

    # SDK
    sdk = event_data.get("sdk", {})
    if sdk.get("name"):
        metadata["sdk"] = f"{sdk['name']} {sdk.get('version', '')}".strip()

    # Tags (first 10)
    tags = event_data.get("tags", {})
    if isinstance(tags, list):
        tags = {t[0]: t[1] for t in tags if len(t) >= 2}
    if tags:
        metadata["tags"] = dict(list(tags.items())[:10])

    return metadata
