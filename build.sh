#!/usr/bin/env bash
# Render build script — runs before every deploy from the repo ROOT

set -o errexit  # Exit immediately if any command fails

echo "==> Upgrading pip..."
pip install --upgrade pip

echo "==> Installing dependencies..."
pip install -r requirements.txt

# manage.py is at the repo root; Django config lives inside src/
export PYTHONPATH="${PYTHONPATH}:$(pwd)/src"
export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-config.settings.production}"

echo "==> Collecting static files..."
python manage.py collectstatic --noinput

echo "==> Running migrations..."
python manage.py migrate --noinput

echo "==> Build complete!"
