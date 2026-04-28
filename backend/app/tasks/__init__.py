# Tasks package — Celery task modules go here
# Import all task modules so Celery auto-discovers them
from app.tasks.event_tasks import *  # noqa: F401, F403
