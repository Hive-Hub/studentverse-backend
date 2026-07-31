#!/bin/sh
# Container entrypoint: wait for DB, apply migrations, collect static, then start app.
set -e

echo "==> Waiting for database..."
until python -c "
import os, sys, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.production')
django.setup()
from django.db import connection
connection.ensure_connection()
print('DB ready.')
"; do
  echo "Database not ready, retrying in 2s..."
  sleep 2
done

echo "==> Running migrations..."
python manage.py migrate --noinput

echo "==> Collecting static files..."
python manage.py collectstatic --noinput --clear

echo "==> Starting application..."
exec "$@"
