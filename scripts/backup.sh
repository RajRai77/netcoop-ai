#!/usr/bin/env sh
# Back up the NetCoop PostgreSQL database of the Docker Compose stack.
#   sh scripts/backup.sh [output-file]          (default: backups/netcoop-<UTC timestamp>.dump)
# Uses pg_dump custom format inside the db container; nothing is written into the container image.
# Local SQLite installs: use `uv run netcoop --database-url sqlite:///var/netcoop.db db backup <file>`.
set -eu
COMPOSE="${COMPOSE:-docker compose}"
OUT="${1:-backups/netcoop-$(date -u +%Y%m%dT%H%M%SZ).dump}"
mkdir -p "$(dirname "$OUT")"
$COMPOSE exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom --no-owner' > "$OUT"
test -s "$OUT"
echo "backup written: $OUT ($(wc -c < "$OUT") bytes)"
