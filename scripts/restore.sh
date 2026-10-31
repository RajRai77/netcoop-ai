#!/usr/bin/env sh
# Restore a backup made by scripts/backup.sh into the Compose PostgreSQL database.
#   sh scripts/restore.sh backups/netcoop-<ts>.dump
# Intended for an EMPTY database (fresh volume). The web service is stopped during the restore so
# no migration or request races with it, then started again.
set -eu
COMPOSE="${COMPOSE:-docker compose}"
IN="${1:?usage: restore.sh <backup.dump>}"
test -s "$IN"
$COMPOSE stop web
# append-only triggers live in the dump; restoring into an empty schema does not fire them
$COMPOSE exec -T db sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --exit-on-error' < "$IN"
$COMPOSE start web
echo "restored: $IN"
