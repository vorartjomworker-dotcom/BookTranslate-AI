#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

POSTGRES_USER="${POSTGRES_USER:-booktranslate}"
POSTGRES_DB="${POSTGRES_DB:-booktranslate}"
DRILL_ID="${DRILL_ID:-$(date -u +%Y%m%dT%H%M%SZ)-$RANDOM}"
BACKUP_ROOT="${BACKUP_ROOT:-$ROOT_DIR/.restore-drill-backups}"
MARKER_FILE="/data/uploads/.restore-drill-$DRILL_ID"
REDIS_KEY="booktranslate:restore-drill:$DRILL_ID"

cleanup() {
  docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 \
    -c "DROP TABLE IF EXISTS restore_drill_marker;" >/dev/null 2>&1 || true
  docker compose exec -T redis redis-cli DEL "$REDIS_KEY" >/dev/null 2>&1 || true
  docker compose exec -T backend rm -f "$MARKER_FILE" >/dev/null 2>&1 || true
  rm -rf "$BACKUP_ROOT"
}
trap cleanup EXIT

mkdir -p "$BACKUP_ROOT"
echo "[$DRILL_ID] creating restore markers"
docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 <<SQL >/dev/null
DROP TABLE IF EXISTS restore_drill_marker;
CREATE TABLE restore_drill_marker (id text PRIMARY KEY, created_at timestamptz NOT NULL DEFAULT now());
INSERT INTO restore_drill_marker (id) VALUES ('$DRILL_ID');
SQL
docker compose exec -T redis redis-cli SET "$REDIS_KEY" "$DRILL_ID" >/dev/null
docker compose exec -T backend sh -c "printf '%s\n' '$DRILL_ID' > '$MARKER_FILE'"

echo "[$DRILL_ID] creating backup"
BACKUP_ROOT="$BACKUP_ROOT" "$ROOT_DIR/scripts/backup.sh" >/tmp/booktranslate-restore-drill-backup.log
BACKUP_DIR="$(find "$BACKUP_ROOT" -mindepth 1 -maxdepth 1 -type d | sort | tail -n 1)"
test -n "$BACKUP_DIR"

# Destroy all three markers before restoration. The drill only passes if the
# backup restores PostgreSQL, Redis and persistent file storage independently.
echo "[$DRILL_ID] destroying live markers"
docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 \
  -c "DROP TABLE restore_drill_marker;" >/dev/null
docker compose exec -T redis redis-cli DEL "$REDIS_KEY" >/dev/null
docker compose exec -T backend rm -f "$MARKER_FILE"

echo "[$DRILL_ID] restoring backup"
"$ROOT_DIR/scripts/restore.sh" "$BACKUP_DIR" >/tmp/booktranslate-restore-drill-restore.log

for attempt in $(seq 1 30); do
  if docker compose exec -T backend python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=2)" >/dev/null 2>&1; then
    break
  fi
  if [ "$attempt" -eq 30 ]; then
    echo "Backend did not become healthy after restore" >&2
    exit 1
  fi
  sleep 2
done

pg_value="$(docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "SELECT id FROM restore_drill_marker LIMIT 1;")"
redis_value="$(docker compose exec -T redis redis-cli --raw GET "$REDIS_KEY" | tr -d '\r')"
file_value="$(docker compose exec -T backend cat "$MARKER_FILE" | tr -d '\r\n')"

if [ "$pg_value" != "$DRILL_ID" ]; then
  echo "PostgreSQL restore verification failed: '$pg_value'" >&2
  exit 1
fi
if [ "$redis_value" != "$DRILL_ID" ]; then
  echo "Redis restore verification failed: '$redis_value'" >&2
  exit 1
fi
if [ "$file_value" != "$DRILL_ID" ]; then
  echo "Persistent file restore verification failed: '$file_value'" >&2
  exit 1
fi

printf 'Restore drill succeeded: %s\n' "$DRILL_ID"
