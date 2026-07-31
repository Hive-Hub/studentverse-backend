#!/usr/bin/env bash
# Render build script — runs before every deploy

set -o errexit  # Exit immediately if any command fails

echo "==> Upgrading pip..."
pip install --upgrade pip

echo "==> Installing dependencies..."
pip install -r requirements.txt

echo "==> Collecting static files..."
cd src
python manage.py collectstatic --noinput

echo "==> Running migrations..."
python manage.py migrate --noinput

echo "==> Build complete!"
