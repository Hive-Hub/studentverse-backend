from __future__ import annotations

import os
from celery import Celery
from django.conf import settings

# Set the default Django settings module for Celery workers
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

app = Celery("studentverse")

# Namespace all Celery-related settings with 'CELERY_' prefix in Django settings
app.config_from_object("django.conf:settings", namespace="CELERY")

# Auto-discover tasks from all installed apps
app.autodiscover_tasks(lambda: settings.INSTALLED_APPS)


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f"Request: {self.request!r}")
