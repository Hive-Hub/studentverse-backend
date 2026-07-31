from __future__ import annotations

import sys

from .base import *  # noqa: F401,F403

DEBUG = True
DJANGO_ENVIRONMENT = "development"
ALLOWED_HOSTS = parse_csv_env("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]")
if any(command == "test" or command.startswith("test") for command in sys.argv[1:]):
	DATABASES = {
		"default": {
			"ENGINE": "django.db.backends.sqlite3",
			"NAME": BASE_DIR / "test_db.sqlite3",
		}
	}
else:
	DATABASES = build_database_settings(allow_sqlite_fallback=True)
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
