#!/usr/bin/env bash
# Backup diário do SQLite e dos comprovantes. Uso: cron em /etc/cron.d/thdfm-backup
set -euo pipefail

APP_DIR="${APP_DIR:-/var/www/thdfm}"
BACKUP_ROOT="${BACKUP_ROOT:-/var/backups/thdfm}"
KEEP_DAYS="${KEEP_DAYS:-14}"
STAMP="$(date +%Y%m%d-%H%M%S)"
DEST="${BACKUP_ROOT}/${STAMP}"

mkdir -p "$DEST"
mkdir -p "$BACKUP_ROOT"

if [[ -f "${APP_DIR}/data/bolao.db" ]]; then
  # Snapshot consistente via sqlite3 .backup quando disponível.
  if command -v sqlite3 >/dev/null 2>&1; then
    sqlite3 "${APP_DIR}/data/bolao.db" ".backup '${DEST}/bolao.db'"
  else
    cp -a "${APP_DIR}/data/bolao.db" "${DEST}/bolao.db"
  fi
fi

if [[ -d "${APP_DIR}/data/comprovantes" ]]; then
  tar -C "${APP_DIR}/data" -czf "${DEST}/comprovantes.tar.gz" comprovantes
fi

# Remove backups antigos
find "$BACKUP_ROOT" -mindepth 1 -maxdepth 1 -type d -mtime "+${KEEP_DAYS}" -exec rm -rf {} +

echo "Backup OK: ${DEST}"
