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

from app.models.project import Project, ProjectMember
from app.models.issue import Issue, IssueStatus, IssueLevel
from app.models.event import Event
from app.models.notification import Notification, NotificationType
from app.logging import get_logger

try:
    from app.tasks.event_tasks import index_issue_to_meilisearch, index_event_to_meilisearch
    _HAS_TASKS = True
except Exception:
    _HAS_TASKS = False

logger = get_logger("services.ingest")

try:
    from app.services.pubsub import publish_to_user, publish_to_project, publish_global
    _HAS_PUBSUB = True
except Exception:
    _HAS_PUBSUB = False

# Regex to extract DSN public key from X-Sentry-Auth header
# Format: Sentry sentry_key=<key>, sentry_version=7, ...
_SENTRY_AUTH_RE = re.compile(r"sentry_key=([a-f0-9]+)")


async def validate_dsn(
    auth_header: str | None,
    query_params: dict,
    db: AsyncSession,
    envelope_header: dict | None = None,
) -> Project | None:
    """Validate DSN auth from X-Sentry-Auth header, query params, or envelope header.

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

    # Fallback: DSN in envelope header
    if dsn_key is None and envelope_header:
        dsn_str = envelope_header.get("dsn", "")
        if dsn_str:
            # DSN format: {PROTOCOL}://{PUBLIC_KEY}:{SECRET_KEY}@{HOST}/{PROJECT_ID}
            # Extract public key (the user part of the URL)
            try:
                from urllib.parse import urlparse
                parsed = urlparse(dsn_str)
                if parsed.username:
                    dsn_key = parsed.username
            except Exception:
                pass

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


def parse_envelope_header(body: bytes) -> tuple[dict, int]:
    """Parse the envelope header (first line) and return (header_dict, offset after header).

    Returns ({}, 0) if parsing fails.
    """
    newline_pos = body.find(b"\n")
    if newline_pos == -1:
        # Entire body is the header (empty envelope)
        try:
            return json.loads(body), len(body)
        except (json.JSONDecodeError, ValueError):
            return {}, 0

    header_line = body[:newline_pos]
    try:
        return json.loads(header_line), newline_pos + 1
    except (json.JSONDecodeError, ValueError):
        return {}, 0


def parse_envelope_payload(body: bytes) -> list[dict]:
    """Parse a Sentry envelope with proper length-prefixed item support.

    Envelope format (per Sentry spec):
        {envelope_header}\\n
        {item_header}\\n
        {item_payload}\\n   (or length-prefixed payload)
        {item_header}\\n
        {item_payload}\\n
        ...

    Items have a `type` header ("event", "error", "transaction", "session", etc.)
    and an optional `length` header. When `length` is present, the payload is
    exactly that many bytes (not newline-delimited).

    Returns list of event payloads found in the envelope.
    """
    events = []
    try:
        # Skip envelope header
        _, offset = parse_envelope_header(body)
        if offset == 0:
            logger.warning("Failed to parse envelope header")
            return events

        while offset < len(body):
            # Skip empty lines
            if body[offset:offset + 1] == b"\n":
                offset += 1
                continue

            # ── Item header ──
            header_end = body.find(b"\n", offset)
            if header_end == -1:
                # No more newlines — try to parse remaining as item header (no payload)
                break

            header_line = body[offset:header_end]
            offset = header_end + 1

            if not header_line.strip():
                continue

            try:
                item_header = json.loads(header_line)
            except (json.JSONDecodeError, ValueError):
                logger.debug("Skipping unparseable item header: %s", header_line[:100])
                continue

            item_type = item_header.get("type", "")
            item_length = item_header.get("length")

            # ── Item payload ──
            if item_length is not None and isinstance(item_length, int) and item_length > 0:
                # Length-prefixed payload
                payload_bytes = body[offset:offset + item_length]
                offset += item_length
                # Skip trailing newline after length-prefixed payload
                if offset < len(body) and body[offset:offset + 1] == b"\n":
                    offset += 1
            else:
                # Implicit length — payload goes to next newline
                payload_end = body.find(b"\n", offset)
                if payload_end == -1:
                    payload_bytes = body[offset:]
                    offset = len(body)
                else:
                    payload_bytes = body[offset:payload_end]
                    offset = payload_end + 1

            if not payload_bytes.strip():
                continue

            # Only process event-like item types
            if item_type in ("event", "error", "transaction", "default", ""):
                try:
                    payload = json.loads(payload_bytes)
                    events.append(payload)
                except (json.JSONDecodeError, ValueError) as e:
                    logger.debug(
                        "Failed to parse %s payload (%d bytes): %s",
                        item_type or "unknown", len(payload_bytes), e,
                    )
            else:
                logger.debug("Skipping envelope item type: %s", item_type)

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
    # Use .first() to handle potential duplicate rows that may exist before
    # the unique constraint migration is applied.
    result = await db.execute(
        select(Issue).where(
            Issue.fingerprint == fingerprint,
            Issue.project_id == project.id,
        ).order_by(Issue.first_seen)
    )
    issue = result.scalars().first()

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

    # Dispatch notifications for new issues or regressions
    if is_new or is_regression:
        await _create_notifications(
            db, project, issue,
            NotificationType.NEW_ISSUE if is_new else NotificationType.REGRESSION,
        )

    # Index in Meilisearch via Celery
    if _HAS_TASKS:
        try:
            index_issue_to_meilisearch.delay({
                "id": str(issue.id),
                "title": issue.title,
                "fingerprint": issue.fingerprint,
                "status": issue.status.value,
                "level": issue.level.value,
                "project_id": str(issue.project_id),
                "event_count": issue.event_count,
                "first_seen": issue.first_seen.isoformat() if issue.first_seen else "",
                "last_seen": issue.last_seen.isoformat() if issue.last_seen else "",
                "metadata": issue.metadata_ or {},
            })
            index_event_to_meilisearch.delay({
                "id": str(event.id),
                "event_id": event.event_id,
                "issue_id": str(event.issue_id),
                "project_id": str(event.project_id),
                "timestamp": event.timestamp.isoformat() if event.timestamp else "",
                "data": event_data,
            })
        except Exception as e:
            logger.warning("Failed to dispatch indexing tasks: %s", e)

    # ── Real-time WebSocket broadcasts ──
    if _HAS_PUBSUB:
        try:
            issue_payload = {
                "id": str(issue.id),
                "title": issue.title,
                "status": issue.status.value,
                "level": issue.level.value,
                "event_count": issue.event_count,
                "last_seen": issue.last_seen.isoformat() if issue.last_seen else "",
                "first_seen": issue.first_seen.isoformat() if issue.first_seen else "",
            }
            # Per-project event
            event_msg = {
                "type": "new_event",
                "project_id": str(project.id),
                "project_slug": project.slug,
                "issue": issue_payload,
                "is_new_issue": is_new,
                "is_regression": is_regression,
            }
            await publish_to_project(str(project.id), event_msg)
            # Also publish to global so dashboard picks it up
            await publish_global(event_msg)
            # Global stats bump
            await publish_global({
                "type": "stats_update",
                "project_id": str(project.id),
                "unresolved_delta": 1 if (is_new or is_regression) else 0,
                "errors_24h_delta": 1,
            })
        except Exception as e:
            logger.warning("Failed to publish real-time events: %s", e)

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


async def _create_notifications(
    db: AsyncSession,
    project: Project,
    issue: Issue,
    notification_type: NotificationType,
) -> None:
    """Create in-app notifications and send email alerts for project members."""
    try:
        from app.models.user import User

        # Get all project members who have notify_inapp OR notify_email enabled
        result = await db.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == project.id,
            )
        )
        members = result.scalars().all()

        type_label = "New issue" if notification_type == NotificationType.NEW_ISSUE else "Regression"

        # Separate lists for in-app and email notifications
        inapp_user_ids = []
        email_user_ids = []

        if members:
            for m in members:
                if m.notify_inapp:
                    inapp_user_ids.append(m.user_id)
                if m.notify_email:
                    email_user_ids.append(m.user_id)
        else:
            # Fallback: notify the project creator via in-app
            inapp_user_ids = [project.created_by]

        # ── In-app notifications ──
        for user_id in inapp_user_ids:
            notification = Notification(
                user_id=user_id,
                issue_id=issue.id,
                project_id=project.id,
                type=notification_type,
                title=f"{type_label} in {project.name}",
                body=issue.title[:300],
            )
            db.add(notification)

        await db.flush()

        # Publish real-time notification to each user via WebSocket
        if _HAS_PUBSUB:
            for user_id in inapp_user_ids:
                try:
                    await publish_to_user(str(user_id), {
                        "type": "new_notification",
                        "notification": {
                            "type": notification_type.value,
                            "title": f"{type_label} in {project.name}",
                            "body": issue.title[:300],
                            "issue_id": str(issue.id),
                            "project_id": str(project.id),
                            "created_at": datetime.now(timezone.utc).isoformat(),
                        },
                    })
                except Exception:
                    pass

        # ── Email notifications (fire-and-forget) ──
        if email_user_ids:
            try:
                from app.services.email import send_issue_notification_email

                # Fetch user emails
                user_result = await db.execute(
                    select(User.id, User.email).where(User.id.in_(email_user_ids))
                )
                user_emails = {row[0]: row[1] for row in user_result.all()}

                # Extract environment from issue metadata
                environment = ""
                if issue.metadata_ and isinstance(issue.metadata_, dict):
                    environment = issue.metadata_.get("environment", "")

                is_regression = notification_type == NotificationType.REGRESSION

                for user_id in email_user_ids:
                    email_addr = user_emails.get(user_id)
                    if not email_addr:
                        continue
                    try:
                        await send_issue_notification_email(
                            db=db,
                            to_email=email_addr,
                            project_name=project.name,
                            project_slug=project.slug,
                            issue_id=str(issue.id),
                            issue_title=issue.title,
                            issue_level=issue.level.value,
                            is_regression=is_regression,
                            event_count=issue.event_count,
                            environment=environment,
                        )
                    except Exception as e:
                        logger.warning(
                            "Failed to send issue email to %s: %s", email_addr, e
                        )
            except Exception as e:
                logger.warning("Failed to dispatch issue emails: %s", e)

        logger.debug(
            "Created %d in-app + %d email notifications for %s (project=%s, issue=%s)",
            len(inapp_user_ids), len(email_user_ids),
            notification_type.value, project.slug, issue.id,
        )
    except Exception as e:
        logger.error("Failed to create notifications: %s", e)

