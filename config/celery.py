"""
Celery configuration for async task processing
"""
import os
from celery import Celery
from celery.schedules import crontab

# Set default Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')

app = Celery('email_support_agent')

# Load config from Django settings
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover tasks from all registered apps
app.autodiscover_tasks()

# Celery Beat Schedule (Periodic Tasks)
app.conf.beat_schedule = {
    'fetch-emails-every-minute': {
        'task': 'apps.emails.tasks.fetch_emails_task',
        'schedule': crontab(minute='*/1'),  # Every 1 minute
    },
    'generate-daily-metrics': {
        'task': 'apps.analytics.tasks.generate_daily_metrics_task',
        'schedule': crontab(hour=0, minute=5),  # Daily at 00:05
    },
    'cleanup-old-logs': {
        'task': 'apps.emails.tasks.cleanup_old_logs_task',
        'schedule': crontab(hour=2, minute=0, day_of_week=0),  # Weekly on Sunday at 2 AM
    },
}

@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f'Request: {self.request!r}')