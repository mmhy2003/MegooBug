"""Tests for the shared sentry_compat event lookup helper."""
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.api.sentry_compat.event_lookup import find_event
from app.models.event import Event
from app.models.issue import Issue
from app.models.project import Project
from app.models.user import User

SENTRY_HEX_ID = "31472ffb67c14b8d85ceb68f067146ae"
OTHER_HEX_ID = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


@pytest.fixture
async def seeded(db):
    now = datetime.now(timezone.utc)
    user = User(email="tester@example.com", name="Tester", password_hash="x")
    db.add(user)
    await db.flush()

    project = Project(
        name="Webmail Backend",
        slug="webmail-backend",
        dsn_public_key=uuid.uuid4().hex,
        created_by=user.id,
    )
    db.add(project)
    await db.flush()

    issue = Issue(project_id=project.id, title="Boom", fingerprint="fp-1")
    other_issue = Issue(project_id=project.id, title="Other", fingerprint="fp-2")
    db.add_all([issue, other_issue])
    await db.flush()

    event = Event(
        issue_id=issue.id,
        project_id=project.id,
        event_id=SENTRY_HEX_ID,
        data={},
        timestamp=now,
    )
    other_event = Event(
        issue_id=other_issue.id,
        project_id=project.id,
        event_id=OTHER_HEX_ID,
        data={},
        timestamp=now,
    )
    db.add_all([event, other_event])
    await db.flush()
    return SimpleNamespace(issue=issue, other_issue=other_issue, event=event)


async def test_finds_by_sentry_hex_id(db, seeded):
    """The bug from the report: a dashless-hex Sentry eventID parses as a
    UUID, so the old code compared it against the internal PK and 404'd."""
    found = await find_event(db, SENTRY_HEX_ID)
    assert found is not None
    assert found.id == seeded.event.id


async def test_finds_by_internal_uuid(db, seeded):
    found = await find_event(db, str(seeded.event.id))
    assert found is not None
    assert found.event_id == SENTRY_HEX_ID


async def test_unknown_id_returns_none(db, seeded):
    assert await find_event(db, "deadbeefdeadbeefdeadbeefdeadbeef") is None


async def test_non_uuid_garbage_returns_none(db, seeded):
    assert await find_event(db, "not-an-id") is None


async def test_issue_filter_scopes_lookup(db, seeded):
    found = await find_event(db, SENTRY_HEX_ID, issue_id=seeded.issue.id)
    assert found is not None

    # Same event, wrong issue → not found
    assert await find_event(db, SENTRY_HEX_ID, issue_id=seeded.other_issue.id) is None
