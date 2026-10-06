#!/bin/sh
set -eu
# Render supplies PORT. Local containers default to the documented port 8000.
exec /app/backend/.venv/bin/uvicorn app.main:app \
  --host 0.0.0.0 --port "${PORT:-8000}" --workers 1 --proxy-headers
