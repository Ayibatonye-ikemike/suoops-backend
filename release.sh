#!/bin/bash
set -euo pipefail
echo "[release] Starting database migrations..."
python -m alembic upgrade head
echo "[release] Migrations complete."