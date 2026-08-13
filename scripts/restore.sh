#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "Usage: $0 <backup-directory>" >&2
  exit 2
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="$(cd "$1" && pwd)"
cd "$ROOT_DIR"

for required in postgres.dump redis.rdb uploads; do
  if [ ! -e "$BACKUP_DIR/$required" ]; then
    echo "Missing backup component: $required" >&2
    exit 2
  fi
done

POSTGRES_USER="${POSTGRES_USER:-booktranslate}"
POSTGRES_DB="${POSTGRES_DB:-booktranslate}"

echo "Stopping application workers..."
docker compose stop frontend backend worker vision-worker figure-render-worker || true

echo "Restoring PostgreSQL..."
cat "$BACKUP_DIR/postgres.dump" | docker compose exec -T postgres pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner

echo "Restoring uploads/assets/exports..."
docker compose cp "$BACKUP_DIR/uploads/." backend:/data/uploads >/dev/null

echo "Restoring Redis snapshot..."
docker compose stop redis
docker compose cp "$BACKUP_DIR/redis.rdb" redis:/data/dump.rdb >/dev/null
docker compose start redis

echo "Starting application..."
docker compose up -d backend worker vision-worker figure-render-worker frontend
printf 'Restore completed from: %s\n' "$BACKUP_DIR"
