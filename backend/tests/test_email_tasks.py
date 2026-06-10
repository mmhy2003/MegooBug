"""Tests for the Celery email tasks (no real SMTP, no broker)."""
import pytest


ISSUE_PAYLOAD = {
    "emails": ["a@example.com", "b@example.com"],
    "project_name": "Webmail Backend",
    "project_slug": "webmail-backend",
    "issue_id": "0dcae490-c3e2-4b5e-86b8-98e5f7e3ad10",
    "issue_title": "ZeroDivisionError: division by zero",
    "issue_level": "error",
    "is_regression": False,
    "event_count": 3,
    "environment": "production",
}


def test_send_issue_emails_noops_without_smtp(monkeypatch):
    from app.tasks import email_tasks

    monkeypatch.setattr(email_tasks, "_load_smtp_config", lambda: None)

    def _must_not_send(*args, **kwargs):
        raise AssertionError("_send must not be called without SMTP config")

    monkeypatch.setattr(email_tasks, "_send", _must_not_send)
    result = email_tasks.send_issue_emails.run(ISSUE_PAYLOAD)
    assert result == {"sent": 0, "failed": 0, "skipped": True}


def test_send_issue_emails_continues_after_failure(monkeypatch):
    from app.tasks import email_tasks

    monkeypatch.setattr(
        email_tasks, "_load_smtp_config",
        lambda: {"host": "smtp.example.com", "port": 587, "from_email": "x@example.com"},
    )

    attempted = []

    def _send_first_fails(cfg, to, subject, html_body, text_body):
        attempted.append(to)
        if to == "a@example.com":
            raise RuntimeError("smtp boom")

    monkeypatch.setattr(email_tasks, "_send", _send_first_fails)
    result = email_tasks.send_issue_emails.run(ISSUE_PAYLOAD)
    assert attempted == ["a@example.com", "b@example.com"]
    assert result == {"sent": 1, "failed": 1}


def test_send_invite_email_noops_without_smtp(monkeypatch):
    from app.tasks import email_tasks

    monkeypatch.setattr(email_tasks, "_load_smtp_config", lambda: None)

    def _must_not_send(*args, **kwargs):
        raise AssertionError("_send must not be called without SMTP config")

    monkeypatch.setattr(email_tasks, "_send", _must_not_send)
    result = email_tasks.send_invite_email.run({
        "to_email": "new@example.com",
        "invite_token": "tok123",
        "role": "developer",
        "invited_by_name": "Admin",
    })
    assert result == {"sent": 0, "skipped": True}


import uuid as _uuid


@pytest.fixture
async def notif_setup(db):
    """User who is a project member with email notifications on, + an issue."""
    from app.models.user import User
    from app.models.project import Project, ProjectMember
    from app.models.issue import Issue

    user = User(email="member@example.com", name="Member", password_hash="x")
    db.add(user)
    await db.flush()
    project = Project(
        name="Notif Proj", slug="notif-proj",
        dsn_public_key=_uuid.uuid4().hex, created_by=user.id,
    )
    db.add(project)
    await db.flush()
    db.add(ProjectMember(project_id=project.id, user_id=user.id,
                         notify_email=True, notify_inapp=True))
    issue = Issue(project_id=project.id, title="Kaboom", fingerprint="notif-fp")
    db.add(issue)
    await db.flush()
    return project, issue, user


async def test_create_notifications_dispatches_email_task(db, notif_setup, monkeypatch):
    from app.models.notification import NotificationType
    from app.services import ingest as ingest_service

    project, issue, user = notif_setup
    captured = []
    monkeypatch.setattr(
        ingest_service.send_issue_emails, "delay",
        lambda payload: captured.append(payload),
    )

    await ingest_service._create_notifications(
        db, project, issue, NotificationType.NEW_ISSUE
    )

    assert len(captured) == 1
    payload = captured[0]
    assert payload["emails"] == ["member@example.com"]
    assert payload["project_slug"] == "notif-proj"
    assert payload["issue_id"] == str(issue.id)
    assert payload["issue_title"] == "Kaboom"
    assert payload["is_regression"] is False


async def test_create_notifications_survives_broker_failure(db, notif_setup, monkeypatch):
    from app.models.notification import NotificationType
    from app.services import ingest as ingest_service

    project, issue, user = notif_setup

    def _broker_down(payload):
        raise ConnectionError("redis unreachable")

    monkeypatch.setattr(ingest_service.send_issue_emails, "delay", _broker_down)

    # Must not raise — a dead broker cannot fail ingest
    await ingest_service._create_notifications(
        db, project, issue, NotificationType.NEW_ISSUE
    )


def test_send_issue_emails_happy_path_builds_correct_content(monkeypatch):
    """Pin what actually reaches _send (catches payload-key typos in body construction)."""
    from app.tasks import email_tasks

    monkeypatch.setattr(
        email_tasks, "_load_smtp_config",
        lambda: {"host": "smtp.example.com", "port": 587, "from_email": "x@example.com"},
    )
    calls = []
    monkeypatch.setattr(
        email_tasks, "_send",
        lambda cfg, to, subject, html_body, text_body: calls.append(
            {"to": to, "subject": subject, "html": html_body, "text": text_body}
        ),
    )

    long_title = "X" * 150
    payload = dict(ISSUE_PAYLOAD, emails=["a@example.com"], issue_title=long_title)
    result = email_tasks.send_issue_emails.run(payload)

    assert result == {"sent": 1, "failed": 0}
    call = calls[0]
    assert call["to"] == "a@example.com"
    # title truncated to 100 chars in the subject
    assert call["subject"] == f"[Webmail Backend] New Issue: {'X' * 100}"
    expected_link = "http://localhost:3000/projects/webmail-backend/issues/0dcae490-c3e2-4b5e-86b8-98e5f7e3ad10"
    assert expected_link in call["text"]
    assert expected_link in call["html"]
    assert long_title in call["text"]
