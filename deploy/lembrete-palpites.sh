#!/usr/bin/env bash
# Dispara o job de lembretes de palpites (14d / 7d / 24h).
# Uso: APP_DIR=/var/www/thdfm /usr/local/bin/thdfm-lembrete-palpites
set -euo pipefail

APP_DIR="${APP_DIR:-/var/www/thdfm}"
ENV_FILE="${APP_DIR}/.env"
BASE_URL="${PUBLIC_BASE_URL:-http://127.0.0.1:8000}"

if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  set -a
  # só variáveis simples KEY=VALUE
  # shellcheck disable=SC1091
  source <(grep -E '^(CRON_SECRET|PUBLIC_BASE_URL)=' "$ENV_FILE" | sed 's/\r$//')
  set +a
fi

if [[ -n "${PUBLIC_BASE_URL:-}" ]]; then
  BASE_URL="${PUBLIC_BASE_URL%/}"
fi

SECRET="${CRON_SECRET:-}"
if [[ -z "$SECRET" ]]; then
  echo "CRON_SECRET vazio — job ignorado" >&2
  exit 0
fi

curl -fsS -X POST \
  -H "X-Cron-Secret: ${SECRET}" \
  "${BASE_URL}/internal/jobs/lembrete-palpites"
echo
