#!/usr/bin/env bash
# Idempotent Cloud Agent bootstrap for the THDFM Bolão app (FastAPI + SQLite).
set -euo pipefail

cd "$(dirname "$0")/.."

# The venv/ensurepip module is not in Cursor's default image; install once.
if ! python3 -c 'import ensurepip' >/dev/null 2>&1; then
  sudo apt-get update -qq
  sudo apt-get install -y python3-venv
fi

python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

# Local dev config: never clobber an existing .env.
[ -f .env ] || cp .env.example .env
