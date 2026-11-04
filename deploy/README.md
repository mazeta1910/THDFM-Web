# Deploy THDFM (VPS 24/7)

## Componentes

| Arquivo | Função |
|---|---|
| `setup-vps.sh` | Bootstrap Ubuntu: clone, venv, nginx, systemd, ufw, cron de backup |
| `bolao.service` | Uvicorn em `127.0.0.1:8000`, `Restart=always` |
| `nginx-thdfm.conf` | Proxy reverso + (após certbot) HTTPS |
| `backup-bolao.sh` | Cópia diária de `bolao.db` + comprovantes |

## Checklist pós-setup

1. Editar `/var/www/thdfm/.env` (`SECRET_KEY`, `ADMIN_USERS`, `PUBLIC_BASE_URL=https://thdfm.com.br`).
2. DNS A `@` e `www` → IP do VPS.
3. `certbot --nginx -d thdfm.com.br -d www.thdfm.com.br`
4. `systemctl restart bolao && systemctl status bolao`
5. Healthcheck: `curl -fsS https://thdfm.com.br/health` → `{"ok":true,...}`

## Observabilidade mínima

```bash
systemctl is-active bolao
journalctl -u bolao -n 50 --no-pager
# Cron opcional (já instalado pelo setup): /etc/cron.d/thdfm-backup
# Alerta simples (crontab do root):
# */5 * * * * systemctl is-active --quiet bolao || echo "bolao down" | mail -s "THDFM" voce@exemplo.com
```

## E-mail transacional (esqueci senha)

No `.env` (ver `.env.example`):

- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`
- `SMTP_FROM` (ex.: `THDFM <noreply@thdfm.com.br>`)
- Sem SMTP configurado, o reset grava o link no log do serviço (dev/teste).
