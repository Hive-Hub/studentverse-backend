from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, unquote, urlparse
import logging
import logging.config
import os
import sys

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parents[3]
SRC_DIR = BASE_DIR / "src"
load_dotenv(BASE_DIR / ".env")


def parse_bool_env(name: str, default: bool = False) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def parse_csv_env(name: str, default: str = "") -> list[str]:
    raw_value = os.getenv(name, default)
    return [item.strip() for item in raw_value.split(",") if item.strip()]


def require_csv_env(name: str) -> list[str]:
    values = parse_csv_env(name)
    if not values:
        raise ImproperlyConfigured(f"{name} must be set for this environment.")
    return values


def _database_from_url(database_url: str) -> dict[str, Any]:
    parsed = urlparse(database_url)
    if parsed.scheme not in {"postgres", "postgresql"}:
        raise ImproperlyConfigured("DATABASE_URL must use the postgres or postgresql scheme.")

    query_options = dict(parse_qsl(parsed.query))
    database_name = unquote(parsed.path.lstrip("/"))

    config: dict[str, Any] = {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": database_name,
        "USER": unquote(parsed.username or ""),
        "PASSWORD": unquote(parsed.password or ""),
        "HOST": parsed.hostname or "",
        "PORT": parsed.port or 5432,
        "CONN_MAX_AGE": int(os.getenv("DJANGO_DB_CONN_MAX_AGE", "0")),
        "OPTIONS": {},
    }

    sslmode = query_options.get("sslmode")
    if sslmode:
        config["OPTIONS"]["sslmode"] = sslmode

    return config


def build_database_settings(allow_sqlite_fallback: bool) -> dict[str, dict[str, Any]]:
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return {"default": _database_from_url(database_url)}

    postgres_name = os.getenv("POSTGRES_NAME") or os.getenv("DB_NAME")
    postgres_user = os.getenv("POSTGRES_USER") or os.getenv("DB_USER")
    postgres_password = os.getenv("POSTGRES_PASSWORD") or os.getenv("DB_PASSWORD")
    postgres_host = os.getenv("POSTGRES_HOST") or os.getenv("DB_HOST")
    postgres_port = os.getenv("POSTGRES_PORT") or os.getenv("DB_PORT") or "5432"

    if all([postgres_name, postgres_user, postgres_password, postgres_host]):
        return {
            "default": {
                "ENGINE": "django.db.backends.postgresql",
                "NAME": postgres_name,
                "USER": postgres_user,
                "PASSWORD": postgres_password,
                "HOST": postgres_host,
                "PORT": postgres_port,
                "CONN_MAX_AGE": int(os.getenv("DJANGO_DB_CONN_MAX_AGE", "0")),
                "OPTIONS": {"sslmode": os.getenv("DJANGO_DB_SSLMODE", "require")},
            }
        }

    if allow_sqlite_fallback:
        return {
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": BASE_DIR / "db.sqlite3",
            }
        }

    raise ImproperlyConfigured(
        "A PostgreSQL connection must be configured through DATABASE_URL or POSTGRES_* values."
    )


SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "django-insecure-change-this-secret-key-in-production")
DEBUG = parse_bool_env("DJANGO_DEBUG", default=False)
APP_NAME = os.getenv("APP_NAME", "StudentVerse Backend")
APP_VERSION = os.getenv("APP_VERSION", "0.1.0")
DJANGO_ENVIRONMENT = os.getenv("DJANGO_ENVIRONMENT", "development")
TIME_ZONE = os.getenv("DJANGO_TIME_ZONE", "UTC")
LANGUAGE_CODE = os.getenv("DJANGO_LANGUAGE_CODE", "en-us")
USE_I18N = True
USE_TZ = True

ALLOWED_HOSTS = []
ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

INSTALLED_APPS = [
    "daphne",
    "channels",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "apps.accounts.apps.AccountsConfig",
    "apps.logs.apps.LogsConfig",
    "apps.common",
    "apps.health",
    "apps.communities.apps.CommunitiesConfig",
    "apps.news.apps.NewsConfig",
    "apps.events.apps.EventsConfig",
    "apps.notifications.apps.NotificationsConfig",
    "apps.search.apps.SearchConfig",
    "apps.messaging.apps.MessagingConfig",
    "apps.moderation.apps.ModerationConfig",
    "apps.dashboard.apps.DashboardConfig",
    "apps.public.apps.PublicConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "apps.logs.middleware.DatabaseLoggingMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "apps.accounts.middleware.AuthTokenContextMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.accounts.middleware.CurrentUserMiddleware",
]

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    }
]

DATABASES = {}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

CORS_ALLOW_CREDENTIALS = True
CORS_ALLOWED_ORIGINS = parse_csv_env(
    "CORS_ALLOWED_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000",
)
CSRF_TRUSTED_ORIGINS = parse_csv_env(
    "CSRF_TRUSTED_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000",
)

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "apps.common.authentication.FirebaseAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_RENDERER_CLASSES": ("rest_framework.renderers.JSONRenderer",),
    "DEFAULT_PARSER_CLASSES": (
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.FormParser",
        "rest_framework.parsers.MultiPartParser",
    ),
    "EXCEPTION_HANDLER": "apps.common.responses.api_exception_handler",
    "DEFAULT_THROTTLE_CLASSES": [],
    "DEFAULT_THROTTLE_RATES": {
        "public_high": "60/min",
        "public_low": "30/min",
        "anon": "120/min",
        "user": "300/min",
    },
}

# Cache configuration (Redis in production if configured, local memory fallback)
REDIS_URL = os.getenv("REDIS_URL", "")
if REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": REDIS_URL,
            "KEY_PREFIX": "sv",
            "OPTIONS": {
                "socket_connect_timeout": 5,
                "socket_timeout": 5,
            },
        }
    }
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {
                "hosts": [REDIS_URL],
            },
        },
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "sv-locmem-fallback",
        }
    }
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels.layers.InMemoryChannelLayer",
        },
    }

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=int(os.getenv("JWT_ACCESS_TOKEN_LIFETIME_MINUTES", "60"))),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=int(os.getenv("JWT_REFRESH_TOKEN_LIFETIME_DAYS", "7"))),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": False,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

LOG_LEVEL = os.getenv("DJANGO_LOG_LEVEL", "INFO").upper()
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {"format": "%(levelname)s %(name)s %(message)s"},
        "verbose": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
        "database": {
            "class": "apps.logs.handlers.DatabaseLogHandler",
            "formatter": "verbose",
        },
    },
    "root": {"handlers": ["console", "database"], "level": LOG_LEVEL},
    "loggers": {
        "django": {"handlers": ["console", "database"], "level": LOG_LEVEL, "propagate": False},
        "apps": {"handlers": ["console", "database"], "level": LOG_LEVEL, "propagate": False},
    },
}
