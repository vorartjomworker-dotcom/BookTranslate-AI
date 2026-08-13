#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_ROOT="${BACKUP_ROOT:-$ROOT_DIR/backups}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DEST="$BACKUP_ROOT/$STAMP"
mkdir -p "$DEST"
cd "$ROOT_DIR"

POSTGRES_USER="${POSTGRES_USER:-booktranslate}"
POSTGRES_DB="${POSTGRES_DB:-booktranslate}"

echo "Creating PostgreSQL backup..."
docker compose exec -T postgres pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc > "$DEST/postgres.dump"

echo "Creating Redis snapshot..."
docker compose exec -T redis redis-cli --rdb /data/booktranslate-backup.rdb >/dev/null
docker compose cp redis:/data/booktranslate-backup.rdb "$DEST/redis.rdb" >/dev/null
docker compose exec -T redis rm -f /data/booktranslate-backup.rdb

echo "Copying persistent uploads/assets/exports..."
mkdir -p "$DEST/uploads"
docker compose cp backend:/data/uploads/. "$DEST/uploads" >/dev/null

{
  echo "created_utc=$STAMP"
  echo "git_sha=$(git rev-parse HEAD 2>/dev/null || echo unknown)"
  echo "postgres_db=$POSTGRES_DB"
} > "$DEST/manifest.txt"

printf 'Backup created: %s\n' "$DEST"
