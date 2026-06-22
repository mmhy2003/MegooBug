"""ingest_event gets a Celery rate_limit only when INGEST_RATE_LIMIT is set."""
from celery import Celery

from app.worker import _apply_ingest_rate_limit


def test_rate_limit_applied_when_set():
    app = Celery("t")
    _apply_ingest_rate_limit(app, "200/s")
    assert app.conf.task_annotations["ingest_event"]["rate_limit"] == "200/s"


def test_rate_limit_absent_when_unset():
    app = Celery("t")
    _apply_ingest_rate_limit(app, None)
    assert not app.conf.task_annotations  # None (Celery default) -> falsy


def test_real_celery_app_matches_settings():
    from app.config import settings
    from app.worker import celery_app
    if settings.INGEST_RATE_LIMIT:
        assert celery_app.conf.task_annotations["ingest_event"]["rate_limit"] == settings.INGEST_RATE_LIMIT
    else:
        assert not celery_app.conf.task_annotations
