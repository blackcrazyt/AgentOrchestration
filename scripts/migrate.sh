#!/bin/bash
# Database migration script - runs BEFORE application rollout.
# The orchestrator entrypoint calls this synchronously before starting the server.

set -e

echo "Running database migrations..."

if [ -f alembic.ini ]; then
    alembic upgrade head
elif [ -f pyproject.toml ]; then
    python -m src.db.migrate
fi

echo "Migrations complete."
