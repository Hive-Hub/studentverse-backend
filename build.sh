#!/usr/bin/env bash
# Render build script — runs from the repo ROOT (/opt/render/project/src/)

set -o errexit

echo "==> Upgrading pip..."
pip install --upgrade pip

echo "==> Installing dependencies..."
pip install -r requirements.txt

# ---------------------------------------------------------------------------
# Build-time environment — safe fallbacks so Django can load settings
# without all runtime secrets being available during the build phase.
# These values are ONLY used during collectstatic / migrate — not at runtime.
# ---------------------------------------------------------------------------
export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-config.settings.production}"

# PYTHONPATH: repo root is /opt/render/project/src/, Django project is in src/
export PYTHONPATH="$(pwd)/src:${PYTHONPATH}"

# Fallbacks for required settings that are not needed at build time
export DJANGO_SECRET_KEY="${DJANGO_SECRET_KEY:-build-time-placeholder-change-in-render-env}"
export DJANGO_ALLOWED_HOSTS="${DJANGO_ALLOWED_HOSTS:-localhost}"
export CORS_ALLOWED_ORIGINS="${CORS_ALLOWED_ORIGINS:-http://localhost:3000}"
export CSRF_TRUSTED_ORIGINS="${CSRF_TRUSTED_ORIGINS:-http://localhost}"
export DJANGO_ENVIRONMENT="${DJANGO_ENVIRONMENT:-production}"
export DJANGO_SECURE_SSL_REDIRECT="${DJANGO_SECURE_SSL_REDIRECT:-false}"

# Supabase / Firebase — not needed for collectstatic/migrate
export SUPABASE_URL="${SUPABASE_URL:-https://placeholder.supabase.co}"
export SUPABASE_KEY="${SUPABASE_KEY:-placeholder}"

echo "==> Collecting static files..."
python manage.py collectstatic --noinput

echo "==> Running migrations..."
# DATABASE_URL must be set in the Render dashboard for this to succeed
python manage.py migrate --noinput

echo "==> Build complete!"
