#!/usr/bin/env bash
# Rode no VPS (Ubuntu 22.04/24.04) como root ou com sudo.
# Uso: bash setup-vps.sh
set -euo pipefail

APP_DIR=/var/www/thdfm
REPO_URL="${REPO_URL:-https://github.com/mazeta1910/THDFM-Bolao-Copa-do-Brasil.git}"

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y git python3 python3-venv python3-pip nginx certbot \
  python3-certbot-nginx ufw sqlite3 curl

if [[ ! -d "$APP_DIR/.git" ]]; then
  mkdir -p /var/www
  git clone "$REPO_URL" "$APP_DIR"
else
  git -C "$APP_DIR" pull --ff-only
fi

cd "$APP_DIR"
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo ">>> Edite $APP_DIR/.env antes de liberar o site (senhas, SECRET_KEY, PUBLIC_BASE_URL, SMTP_*)."
fi

mkdir -p data/comprovantes data/avatars data/emblemas /var/backups/thdfm
chown -R www-data:www-data "$APP_DIR"
chmod -R u+rwX,g+rwX data
chown root:root /var/backups/thdfm

cp deploy/bolao.service /etc/systemd/system/bolao.service
cp deploy/nginx-thdfm.conf /etc/nginx/sites-available/thdfm
install -m 755 deploy/backup-bolao.sh /usr/local/bin/thdfm-backup
ln -sfn /etc/nginx/sites-available/thdfm /etc/nginx/sites-enabled/thdfm
rm -f /etc/nginx/sites-enabled/default

cat >/etc/cron.d/thdfm-backup <<'CRON'
# Backup diário 03:15 America/Sao_Paulo (servidor em UTC-3 ou ajuste)
15 3 * * * root APP_DIR=/var/www/thdfm /usr/local/bin/thdfm-backup >>/var/log/thdfm-backup.log 2>&1
CRON

# Watchdog leve: a cada 5 min, se o serviço caiu, tenta subir de novo
cat >/etc/cron.d/thdfm-watchdog <<'CRON'
*/5 * * * * root systemctl is-active --quiet bolao || systemctl start bolao
CRON

nginx -t
systemctl daemon-reload
systemctl enable --now bolao
systemctl reload nginx

ufw allow OpenSSH
ufw allow 'Nginx Full'
ufw --force enable

echo
echo "Pronto (base)."
echo "1) Edite $APP_DIR/.env (SECRET_KEY, ADMIN_USERS, PUBLIC_BASE_URL, SMTP_* para reset de senha)"
echo "2) Aponte o DNS de thdfm.com.br para o IP deste VPS (A @ e A www)"
echo "3) Rode: certbot --nginx -d thdfm.com.br -d www.thdfm.com.br"
echo "4) systemctl restart bolao"
echo "5) Health: curl -fsS http://127.0.0.1:8000/health"
