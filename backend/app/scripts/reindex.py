"""Full Meilisearch re-index script.

Thin CLI wrapper around the Celery `reindex_all` task body (single source
of truth in app.tasks.event_tasks) — clears the indexes, then re-adds all
projects, issues, and events.

Usage:
    python -m app.scripts.reindex
"""
from app.logging import setup_logging, get_logger
from app.tasks.event_tasks import reindex_all

setup_logging()
logger = get_logger("scripts.reindex")


if __name__ == "__main__":
    logger.info("Starting full Meilisearch rebuild")
    reindex_all.run()
