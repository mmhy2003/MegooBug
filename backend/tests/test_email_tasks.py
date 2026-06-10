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
