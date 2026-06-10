"""Celery tasks for sending emails off the request path.

Emails were previously sent inline during ingest/invite requests, holding
the request's pooled DB connection through slow SMTP I/O — under an error
storm this exhausted the API's connection pool (the 2026-06 production
incident). These tasks run on the worker: fire once, log failures, no
retries. SMTP credentials are loaded here (DB settings → env fallback),
never passed through the broker.
"""
from app.worker import celery_app
from app.config import settings
from app.logging import get_logger
from app.services.email import (
    _build_invite_html,
    _build_issue_notification_html,
    _env_smtp_config,
    _send,
)

logger = get_logger("tasks.email")


def _load_smtp_config() -> dict | None:
    """SMTP config from the settings table (sync engine), env fallback.

    Replaces the API's former async _get_smtp_config — Celery tasks run
    outside the async event loop (same pattern as reindex_all).
    """
    try:
        from sqlalchemy import create_engine, text

        sync_url = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
        engine = create_engine(sync_url)
        try:
            with engine.connect() as conn:
                row = conn.execute(
                    text("SELECT value FROM settings WHERE key = 'smtp'")
                ).fetchone()
        finally:
            engine.dispose()
        if row and row[0] and row[0].get("host"):
            return row[0]
    except Exception:
        logger.warning("Could not read SMTP settings from DB, falling back to env", exc_info=True)

    return _env_smtp_config()


@celery_app.task(name="send_issue_emails")
def send_issue_emails(payload: dict) -> dict:
    """Send new-issue/regression notification emails to project members."""
    emails = payload.get("emails", [])
    cfg = _load_smtp_config()
    if cfg is None:
        logger.debug("SMTP not configured — skipping %d issue emails", len(emails))
        return {"sent": 0, "failed": 0, "skipped": True}

    app_url = settings.APP_URL.rstrip("/")
    app_name = settings.APP_NAME
    issue_link = f"{app_url}/projects/{payload['project_slug']}/issues/{payload['issue_id']}"
    is_regression = bool(payload.get("is_regression"))
    type_label = "Regression" if is_regression else "New Issue"
    subject = f"[{payload['project_name']}] {type_label}: {payload['issue_title'][:100]}"
    environment = payload.get("environment", "")

    text_body = (
        f"{type_label} in {payload['project_name']}\n\n"
        f"Level: {payload['issue_level'].upper()}\n"
        f"Title: {payload['issue_title']}\n"
        f"Events: {payload.get('event_count', 1)}\n"
        + (f"Environment: {environment}\n" if environment else "")
        + f"\nView issue: {issue_link}\n\n"
        f"— {app_name}"
    )
    html_body = _build_issue_notification_html(
        app_name=app_name,
        project_name=payload["project_name"],
        issue_title=payload["issue_title"],
        issue_level=payload["issue_level"],
        issue_link=issue_link,
        is_regression=is_regression,
        event_count=payload.get("event_count", 1),
        environment=environment,
    )

    sent = failed = 0
    for to_email in emails:
        try:
            _send(cfg, to_email, subject, html_body, text_body)
            sent += 1
        except Exception as e:
            failed += 1
            logger.error("Failed to send issue email to %s: %s", to_email, e)

    logger.info(
        "Issue emails: %d sent, %d failed (issue=%s)",
        sent, failed, payload["issue_id"][:8],
    )
    return {"sent": sent, "failed": failed}


@celery_app.task(name="send_invite_email")
def send_invite_email(payload: dict) -> dict:
    """Send a team invite email."""
    to_email = payload["to_email"]
    cfg = _load_smtp_config()
    if cfg is None:
        logger.warning("Cannot send invite email to %s — SMTP not configured", to_email)
        return {"sent": 0, "skipped": True}

    app_url = settings.APP_URL.rstrip("/")
    app_name = settings.APP_NAME
    invite_link = f"{app_url}/register?token={payload['invite_token']}"
    expire_hours = settings.INVITE_TOKEN_EXPIRE_HOURS
    role = payload.get("role", "viewer")
    invited_by_name = payload.get("invited_by_name", "An admin")

    subject = f"You've been invited to {app_name}"
    text_body = (
        f"Hi,\n\n"
        f"{invited_by_name} has invited you to join {app_name} as a {role}.\n\n"
        f"Click the link below to create your account:\n"
        f"{invite_link}\n\n"
        f"This link expires in {expire_hours} hours.\n\n"
        f"If you didn't expect this invite, you can safely ignore this email.\n\n"
        f"— {app_name}"
    )
    html_body = _build_invite_html(
        app_name=app_name,
        invite_link=invite_link,
        invited_by_name=invited_by_name,
        role=role,
        expire_hours=expire_hours,
    )

    try:
        _send(cfg, to_email, subject, html_body, text_body)
        logger.info("Invite email sent to %s", to_email)
        return {"sent": 1}
    except Exception as e:
        logger.error("Failed to send invite email to %s: %s", to_email, e)
        return {"sent": 0, "failed": 1}
