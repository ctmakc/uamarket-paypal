#!/bin/sh
# Nightly backups for docker-compose.prod.yml (runs inside the postgres:16-alpine `backup` service).
#
#   sh pg-backup.sh loop     wait for BACKUP_HOUR_UTC every day, then back up (the service command)
#   sh pg-backup.sh now      one backup immediately
#
# Writes /backups/uamarket-YYYYmmddTHHMMSSZ.dump (pg_dump custom format) and
# /backups/media-YYYYmmddTHHMMSSZ.tar.gz (the product photo volume), then deletes files older
# than BACKUP_KEEP_DAYS (default 14). Restore: scripts/backup/restore.sh.
set -eu

KEEP="${BACKUP_KEEP_DAYS:-14}"
HOUR="${BACKUP_HOUR_UTC:-7}"

backup() {
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  tmp="/backups/.uamarket-$stamp.dump.partial"
  pg_dump --format=custom --no-owner --file="$tmp"
  mv "$tmp" "/backups/uamarket-$stamp.dump"
  if [ -d /media ]; then
    tar -czf "/backups/.media-$stamp.tar.gz.partial" -C /media . && mv "/backups/.media-$stamp.tar.gz.partial" "/backups/media-$stamp.tar.gz"
  fi
  find /backups -maxdepth 1 -type f \( -name 'uamarket-*.dump' -o -name 'media-*.tar.gz' \) -mtime +"$((KEEP - 1))" -delete
  echo "backup $stamp: $(ls -1 /backups | grep -c "$stamp") file(s); kept: $(ls -1 /backups/uamarket-*.dump | wc -l) database dump(s)"
}

case "${1:-now}" in
  now) backup ;;
  loop)
    while true; do
      now_h="$(date -u +%H | sed 's/^0//')"; now_m="$(date -u +%M | sed 's/^0//')"; now_s="$(date -u +%S | sed 's/^0//')"
      elapsed=$(( ${now_h:-0} * 3600 + ${now_m:-0} * 60 + ${now_s:-0} ))
      target=$(( HOUR * 3600 ))
      wait=$(( target - elapsed ))
      [ "$wait" -le 0 ] && wait=$(( wait + 86400 ))
      echo "next backup in ${wait}s (at ${HOUR}:00 UTC)"
      sleep "$wait"
      backup || echo "backup FAILED"
    done ;;
  *) echo "usage: pg-backup.sh loop|now" >&2; exit 2 ;;
esac
