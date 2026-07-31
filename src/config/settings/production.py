from __future__ import annotations

import os

from .base import *  # noqa: F401,F403

DEBUG = False
DJANGO_ENVIRONMENT = "production"
ALLOWED_HOSTS = require_csv_env("DJANGO_ALLOWED_HOSTS")
DATABASES = build_database_settings(allow_sqlite_fallback=False)

# CORS / CSRF — fall back to HTTPS versions of ALLOWED_HOSTS if not explicitly set
_allowed_hosts = ALLOWED_HOSTS
_default_origins = [f"https://{h}" for h in _allowed_hosts if h not in ("*", "localhost", "127.0.0.1")]
CORS_ALLOWED_ORIGINS = parse_csv_env("CORS_ALLOWED_ORIGINS", ",".join(_default_origins) or "https://localhost")
CSRF_TRUSTED_ORIGINS = parse_csv_env("CSRF_TRUSTED_ORIGINS", ",".join(_default_origins) or "https://localhost")

STORAGES = {
    **STORAGES,
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# ---------------------------------------------------------------------------
# Security Headers
# ---------------------------------------------------------------------------
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
X_FRAME_OPTIONS = "DENY"
SECURE_HSTS_SECONDS = int(os.getenv("DJANGO_SECURE_HSTS_SECONDS", "31536000"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = parse_bool_env("DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS", True)
SECURE_HSTS_PRELOAD = parse_bool_env("DJANGO_SECURE_HSTS_PRELOAD", True)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = parse_bool_env("DJANGO_SECURE_SSL_REDIRECT", False)

# ---------------------------------------------------------------------------
# Production Cache — Redis (overrides base.py CACHES)
# ---------------------------------------------------------------------------
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": os.getenv("REDIS_URL", "redis://redis:6379/1"),
        "KEY_PREFIX": "sv_prod",
        "TIMEOUT": 300,
        "OPTIONS": {
            "socket_connect_timeout": 5,
            "socket_timeout": 5,
        },
    }
}

# ---------------------------------------------------------------------------
# Email — SMTP (configure via environment variables)
# ---------------------------------------------------------------------------
EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.sendgrid.net")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_USE_TLS = parse_bool_env("EMAIL_USE_TLS", True)
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "noreply@studentverse.app")

# ---------------------------------------------------------------------------
# Celery — Redis broker + result backend
# ---------------------------------------------------------------------------
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", os.getenv("REDIS_URL", "redis://redis:6379/2"))
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", os.getenv("REDIS_URL", "redis://redis:6379/3"))
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60  # 30 minutes hard limit
CELERY_TASK_SOFT_TIME_LIMIT = 25 * 60  # 25 minutes soft limit

# Celery Beat — Periodic task schedule
CELERY_BEAT_SCHEDULE = {
    "cleanup-expired-bans-daily": {
        "task": "apps.common.tasks.cleanup_expired_bans",
        "schedule": 86400,  # every 24 hours
    },
    "cleanup-expired-mutes-hourly": {
        "task": "apps.common.tasks.cleanup_expired_mutes",
        "schedule": 3600,  # every hour
    },
    "prune-expired-announcements-hourly": {
        "task": "apps.common.tasks.prune_expired_announcements",
        "schedule": 3600,  # every hour
    },
    "cleanup-old-logs-weekly": {
        "task": "apps.common.tasks.cleanup_old_logs",
        "schedule": 604800,  # every 7 days
        "kwargs": {"days": 90},
    },
    "generate-weekly-stats-snapshot": {
        "task": "apps.common.tasks.generate_weekly_stats_snapshot",
        "schedule": 604800,  # every 7 days
    },
    "cleanup-orphan-search-history-weekly": {
        "task": "apps.common.tasks.cleanup_orphan_search_history",
        "schedule": 604800,  # every 7 days
    },
}

# ---------------------------------------------------------------------------
# Sentry — Error monitoring (optional, configure via SENTRY_DSN env var)
# ---------------------------------------------------------------------------
_sentry_dsn = os.getenv("SENTRY_DSN", "")
if _sentry_dsn:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration
    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.redis import RedisIntegration

    sentry_sdk.init(
        dsn=_sentry_dsn,
        integrations=[
            DjangoIntegration(),
            CeleryIntegration(),
            RedisIntegration(),
        ],
        traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
        send_default_pii=False,
        environment="production",
        release=os.getenv("APP_VERSION", "unknown"),
    )

# ---------------------------------------------------------------------------
# Production Logging — rotating file handler (safe for Render / Docker)
# ---------------------------------------------------------------------------
import pathlib

_log_dir = pathlib.Path(BASE_DIR) / "logs"
_log_dir.mkdir(parents=True, exist_ok=True)  # create logs/ if it doesn't exist

LOGGING["handlers"]["file"] = {  # type: ignore[index]
    "class": "logging.handlers.RotatingFileHandler",
    "filename": str(_log_dir / "django.log"),
    "maxBytes": 1024 * 1024 * 10,  # 10 MB
    "backupCount": 5,
    "formatter": "verbose",
    "delay": True,  # don't open the file until the first log message
}
LOGGING["root"]["handlers"].append("file")  # type: ignore[index]
LOGGING["loggers"]["django"]["handlers"].append("file")  # type: ignore[index]
LOGGING["loggers"]["apps"]["handlers"].append("file")  # type: ignore[index]
