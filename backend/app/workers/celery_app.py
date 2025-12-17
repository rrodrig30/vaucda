"""
Celery application configuration for background task processing
"""
from celery import Celery
from celery.schedules import crontab
from app.config import settings

# Create Celery application
celery_app = Celery(
    "vaucda",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.workers.tasks"]
)

# Configure Celery
celery_app.conf.update(
    task_serializer=settings.CELERY_TASK_SERIALIZER,
    result_serializer=settings.CELERY_RESULT_SERIALIZER,
    accept_content=settings.celery_accept_content_list,
    timezone=settings.CELERY_TIMEZONE,
    enable_utc=True,
    task_track_started=True,
    task_time_limit=settings.CELERY_TASK_TIME_LIMIT,
    task_soft_time_limit=settings.CELERY_TASK_SOFT_TIME_LIMIT,
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,
    result_expires=3600,  # 1 hour
)

# Periodic tasks configuration
celery_app.conf.beat_schedule = {
    "cleanup-expired-sessions": {
        "task": "app.workers.tasks.cleanup_expired_sessions",
        "schedule": crontab(minute=f"*/{settings.SESSION_CLEANUP_INTERVAL_MINUTES}"),  # Every 5 minutes
    },
    "cleanup-old-audit-logs": {
        "task": "app.workers.tasks.cleanup_old_audit_logs",
        "schedule": crontab(hour=2, minute=0),  # Daily at 2 AM
    },
}

if __name__ == "__main__":
    celery_app.start()
