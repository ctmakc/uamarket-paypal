#!/usr/bin/env bash
# Restore a nightly dump into a database of the production stack.
#
#   scripts/backup/restore.sh <dump-file-name> [target-db]
#
# <dump-file-name> is a file in the `backups` volume, e.g. uamarket-20260917T070000Z.dump
# (list them: docker compose -f docker-compose.yml -f docker-compose.prod.yml exec backup ls -l /backups).
# [target-db] defaults to `restore_check`, a scratch database created fresh for the purpose,
# so a restore never touches the live `heritage` database unless you name it on purpose
# (stop app, scheduler and web first when you do).
set -euo pipefail
cd "$(dirname "$0")/../.."
DUMP="${1:?usage: restore.sh <dump-file-name> [target-db]}"
TARGET="${2:-restore_check}"
# The hosted demo passes its own files and env: COMPOSE_ARGS="-p uamarket-demo -f … --env-file …" (docs/DEMO-DEPLOY.md).
read -r -a EXTRA <<< "${COMPOSE_ARGS:--f docker-compose.yml -f docker-compose.prod.yml}"
COMPOSE=(docker compose "${EXTRA[@]}")
if [ "$TARGET" != "heritage" ]; then
  "${COMPOSE[@]}" exec -T backup psql -d postgres -v ON_ERROR_STOP=1 -c "DROP DATABASE IF EXISTS \"$TARGET\"" -c "CREATE DATABASE \"$TARGET\""
fi
"${COMPOSE[@]}" exec -T backup pg_restore --no-owner --clean --if-exists --exit-on-error -d "$TARGET" "/backups/$DUMP"
"${COMPOSE[@]}" exec -T backup psql -d "$TARGET" -tAc "select 'orders=' || count(*) from orders union all select 'products=' || count(*) from products union all select 'alembic=' || version_num from alembic_version"
echo "restored $DUMP into $TARGET"
