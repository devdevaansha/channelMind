#!/bin/bash
set -e

echo "Running Django migrations..."
python manage.py migrate --noinput

echo "Starting web server..."
exec "$@"
