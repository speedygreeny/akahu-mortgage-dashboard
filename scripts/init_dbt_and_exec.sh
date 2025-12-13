#!/usr/bin/env bash
set -euo pipefail

echo "[init] running dbt init script (if dbt present)"
if command -v dbt >/dev/null 2>&1; then
  if [ -d "/app/dbt_project" ]; then
    echo "[init] cd /app/dbt_project"
    cd /app/dbt_project
    echo "[init] running: dbt deps"
    dbt deps || echo "[init] dbt deps failed (continuing)"
    echo "[init] running: dbt compile"
    dbt compile || echo "[init] dbt compile failed (continuing)"
    echo "[init] dbt compile finished"
  else
    echo "[init] /app/dbt_project not found, skipping"
  fi
else
  echo "[init] dbt CLI not installed in this container, skipping dbt init"
fi

echo "[init] exec: $@"
exec "$@"
