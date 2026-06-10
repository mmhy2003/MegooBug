"""Tests for the retention cleanup core (Postgres only — no Celery, no Meilisearch)."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.tasks.cleanup_tasks import _cleanup
from app.models.event import Event
from app.models.issue import Issue
from app.models.project import Project
from app.models.user import User


@pytest.fixture
async def project(db):
    user = User(email="retention@example.com", name="Retention", password_hash="x")
    db.add(user)
    await db.flush()
    proj = Project(
        name="Retention Proj",
        slug="retention-proj",
        dsn_public_key=uuid.uuid4().hex,
        created_by=user.id,
    )
    db.add(proj)
    await db.flush()
    return proj


async def _make_issue(db, project, fingerprint, last_seen):
    issue = Issue(
        project_id=project.id,
        title=f"Issue {fingerprint}",
        fingerprint=fingerprint,
        last_seen=last_seen,
    )
    db.add(issue)
    await db.flush()
    return issue


async def _make_event(db, issue, timestamp):
    event = Event(
        issue_id=issue.id,
        project_id=issue.project_id,
        event_id=uuid.uuid4().hex,
        data={},
        timestamp=timestamp,
    )
    db.add(event)
    await db.flush()
    return event


async def _count(db, model):
    return (await db.execute(select(func.count()).select_from(model))).scalar()


async def test_stale_issue_cascades(db, project):
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=14)
    stale = await _make_issue(db, project, "stale-fp", last_seen=now - timedelta(days=30))
    await _make_event(db, stale, timestamp=now - timedelta(days=30))
    fresh = await _make_issue(db, project, "fresh-fp", last_seen=now)
    await _make_event(db, fresh, timestamp=now)

    summary = await _cleanup(db, cutoff)

    assert summary["issues_deleted"] == 1
    assert stale.id in summary["stale_issue_ids"]
    remaining_issues = (await db.execute(select(Issue.id))).scalars().all()
    assert remaining_issues == [fresh.id]
    # stale issue's event went away via cascade; fresh event survives
    remaining_events = (await db.execute(select(Event.issue_id))).scalars().all()
    assert remaining_events == [fresh.id]


async def test_active_issue_keeps_recent_events(db, project):
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=14)
    issue = await _make_issue(db, project, "active-fp", last_seen=now)
    old_event = await _make_event(db, issue, timestamp=now - timedelta(days=30))
    new_event = await _make_event(db, issue, timestamp=now)

    summary = await _cleanup(db, cutoff)

    assert summary["issues_deleted"] == 0
    assert summary["events_deleted"] == 1
    assert old_event.id in summary["deleted_event_ids"]
    remaining = (await db.execute(select(Event.id))).scalars().all()
    assert remaining == [new_event.id]


async def test_cutoff_boundary_keeps_newer_events(db, project):
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=14)
    issue = await _make_issue(db, project, "boundary-fp", last_seen=now)
    await _make_event(db, issue, timestamp=cutoff + timedelta(seconds=1))

    summary = await _cleanup(db, cutoff)

    assert summary["events_deleted"] == 0
    assert await _count(db, Event) == 1


async def test_batching_terminates_and_deletes_all(db, project):
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=14)
    issue = await _make_issue(db, project, "batch-fp", last_seen=now)
    for _ in range(3):
        await _make_event(db, issue, timestamp=now - timedelta(days=30))

    summary = await _cleanup(db, cutoff, batch_size=1)

    assert summary["events_deleted"] == 3
    assert await _count(db, Event) == 0
