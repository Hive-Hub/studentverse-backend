from __future__ import annotations

# This makes Celery app available when Django starts (for task discovery).
# Guarded so the project still boots if Celery is not installed.
try:
    from .celery import app as celery_app  # noqa: F401
    __all__ = ["celery_app"]
except ImportError:
    __all__ = []
