#!/bin/sh
set -e

# Print the deployed build first, so the droplet log shows which code this restart is running.
REVISION="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
echo "Deploying build ${REVISION}"

echo "Running database migrations..."
alembic upgrade head

echo "Starting server..."
exec uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1
