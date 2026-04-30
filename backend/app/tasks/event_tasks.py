"""Celery tasks for async event processing and search indexing."""
from app.worker import celery_app
from app.logging import get_logger

logger = get_logger("tasks.events")


@celery_app.task(name="index_issue_to_meilisearch")
def index_issue_to_meilisearch(issue_data: dict):
    """Index or update an issue in Meilisearch for full-text search."""
    try:
        import meilisearch
        from app.config import settings

        client = meilisearch.Client(
            settings.MEILISEARCH_URL,
            settings.MEILISEARCH_MASTER_KEY,
        )

        index = client.index("issues")
        # Meilisearch requires a string ID
        doc = {
            "id": str(issue_data["id"]),
            "title": issue_data.get("title", ""),
            "fingerprint": issue_data.get("fingerprint", ""),
            "status": issue_data.get("status", ""),
            "level": issue_data.get("level", ""),
            "project_id": str(issue_data.get("project_id", "")),
            "event_count": issue_data.get("event_count", 0),
            "first_seen": issue_data.get("first_seen", ""),
            "last_seen": issue_data.get("last_seen", ""),
            "metadata": issue_data.get("metadata", {}),
        }
        index.add_documents([doc], primary_key="id")
        logger.debug("Indexed issue %s in Meilisearch", doc["id"])

    except Exception as e:
        logger.error("Failed to index issue in Meilisearch: %s", e)


@celery_app.task(name="index_event_to_meilisearch")
def index_event_to_meilisearch(event_data: dict):
    """Index an event in Meilisearch for full-text search."""
    try:
        import meilisearch
        from app.config import settings

        client = meilisearch.Client(
            settings.MEILISEARCH_URL,
            settings.MEILISEARCH_MASTER_KEY,
        )

        index = client.index("events")
        # Extract searchable text from the event payload
        raw = event_data.get("data", {})
        searchable_text = _extract_searchable_text(raw)

        doc = {
            "id": str(event_data["id"]),
            "event_id": event_data.get("event_id", ""),
            "issue_id": str(event_data.get("issue_id", "")),
            "project_id": str(event_data.get("project_id", "")),
            "message": searchable_text,
            "timestamp": event_data.get("timestamp", ""),
        }
        index.add_documents([doc], primary_key="id")
        logger.debug("Indexed event %s in Meilisearch", doc["id"])

    except Exception as e:
        logger.error("Failed to index event in Meilisearch: %s", e)


@celery_app.task(name="reindex_all")
def reindex_all():
    """Full re-index of all issues and events into Meilisearch.

    Called via `make reindex`. Uses synchronous DB access since Celery
    tasks run outside the async event loop.
    """
    try:
        import meilisearch
        from sqlalchemy import create_engine, text
        from app.config import settings

        # Use sync engine for Celery context
        sync_url = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
        engine = create_engine(sync_url)

        client = meilisearch.Client(
            settings.MEILISEARCH_URL,
            settings.MEILISEARCH_MASTER_KEY,
        )

        # Configure indexes
        _configure_indexes(client)

        # Re-index issues
        with engine.connect() as conn:
            result = conn.execute(text("SELECT id, project_id, title, fingerprint, status, level, event_count, first_seen, last_seen, metadata FROM issues"))
            issues = []
            for row in result:
                issues.append({
                    "id": str(row[0]),
                    "project_id": str(row[1]),
                    "title": row[2],
                    "fingerprint": row[3],
                    "status": row[4],
                    "level": row[5],
                    "event_count": row[6],
                    "first_seen": str(row[7]) if row[7] else "",
                    "last_seen": str(row[8]) if row[8] else "",
                    "metadata": row[9] or {},
                })
            if issues:
                client.index("issues").add_documents(issues, primary_key="id")
                logger.info("Re-indexed %d issues", len(issues))

            # Re-index projects
            result = conn.execute(text("SELECT id, name, slug, platform, created_at FROM projects"))
            projects = []
            for row in result:
                projects.append({
                    "id": str(row[0]),
                    "name": row[1],
                    "slug": row[2],
                    "platform": row[3] or "",
                    "created_at": str(row[4]) if row[4] else "",
                })
            if projects:
                client.index("projects").add_documents(projects, primary_key="id")
                logger.info("Re-indexed %d projects", len(projects))

        engine.dispose()
        logger.info("Full re-index complete")

    except Exception as e:
        logger.error("Re-index failed: %s", e)


def _configure_indexes(client):
    """Ensure Meilisearch indexes are configured with proper filterable/sortable attributes."""
    try:
        client.create_index("issues", {"primaryKey": "id"})
    except Exception:
        pass
    try:
        client.create_index("events", {"primaryKey": "id"})
    except Exception:
        pass
    try:
        client.create_index("projects", {"primaryKey": "id"})
    except Exception:
        pass

    client.index("issues").update_filterable_attributes(["project_id", "status", "level"])
    client.index("issues").update_sortable_attributes(["last_seen", "event_count"])
    client.index("events").update_filterable_attributes(["project_id", "issue_id"])
    client.index("events").update_sortable_attributes(["timestamp"])
    client.index("projects").update_filterable_attributes(["id"])
    client.index("projects").update_sortable_attributes(["created_at"])


@celery_app.task(name="index_project_to_meilisearch")
def index_project_to_meilisearch(project_data: dict):
    """Index a project in Meilisearch for full-text search."""
    try:
        import meilisearch
        from app.config import settings

        client = meilisearch.Client(
            settings.MEILISEARCH_URL,
            settings.MEILISEARCH_MASTER_KEY,
        )

        index = client.index("projects")
        doc = {
            "id": str(project_data["id"]),
            "name": project_data.get("name", ""),
            "slug": project_data.get("slug", ""),
            "platform": project_data.get("platform", ""),
            "created_at": project_data.get("created_at", ""),
        }
        index.add_documents([doc], primary_key="id")
        logger.debug("Indexed project %s in Meilisearch", doc["id"])

    except Exception as e:
        logger.error("Failed to index project in Meilisearch: %s", e)


def _extract_searchable_text(event_data: dict) -> str:
    """Extract searchable text from raw event payload."""
    parts = []

    # Message
    message = event_data.get("message", "")
    if isinstance(message, dict):
        message = message.get("formatted", message.get("message", ""))
    if message:
        parts.append(str(message))

    # Exception
    exception = event_data.get("exception", {})
    for exc in exception.get("values", []):
        parts.append(exc.get("type", ""))
        parts.append(exc.get("value", ""))

    # Logentry
    logentry = event_data.get("logentry", {})
    if logentry.get("message"):
        parts.append(logentry["message"])

    return " ".join(filter(None, parts))[:5000]
