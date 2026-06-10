from celery import Celery
from celery.schedules import crontab
from app.config import settings

celery_app = Celery(
    "megoobug",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_default_queue="default",
    # Bound .delay() against an unreachable broker: API handlers publish
    # tasks inline (guarded by try/except), and an unbounded connect would
    # stall the event loop for minutes on a blackholed broker.
    broker_transport_options={"socket_connect_timeout": 2, "socket_timeout": 5},
    task_publish_retry_policy={
        "max_retries": 1,
        "interval_start": 0,
        "interval_step": 0.2,
        "interval_max": 0.2,
    },
)

# Register task modules explicitly
celery_app.conf.include = [
    "app.tasks.event_tasks",
    "app.tasks.cleanup_tasks",
    "app.tasks.email_tasks",
]

# Periodic tasks (beat runs embedded in the worker via `-B`)
celery_app.conf.beat_schedule = {
    "cleanup-old-data-daily": {
        "task": "cleanup_old_data",
        "schedule": crontab(hour=3, minute=0),  # daily, 03:00 UTC
    },
}
