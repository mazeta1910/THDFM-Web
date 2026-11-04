"""Envio de e-mail transacional (SMTP). Sem SMTP_HOST, registra no log."""

from __future__ import annotations

import logging
import os
import smtplib
import ssl
from email.message import EmailMessage

log = logging.getLogger("thdfm.mail")


def smtp_configurado() -> bool:
    return bool((os.environ.get("SMTP_HOST") or "").strip())


def enviar_email(*, para: str, assunto: str, texto: str) -> bool:
    """Envia texto puro. Retorna True se enviou (ou logou em modo dev)."""
    para = (para or "").strip()
    if not para or "@" not in para:
        raise ValueError("e-mail inválido")

    host = (os.environ.get("SMTP_HOST") or "").strip()
    if not host:
        log.warning(
            "SMTP não configurado — e-mail para %s | %s | %s",
            para,
            assunto,
            texto.replace("\n", " | "),
        )
        return True

    port = int((os.environ.get("SMTP_PORT") or "587").strip() or "587")
    user = (os.environ.get("SMTP_USER") or "").strip()
    password = os.environ.get("SMTP_PASSWORD") or ""
    from_addr = (os.environ.get("SMTP_FROM") or user or "noreply@localhost").strip()
    use_tls = (os.environ.get("SMTP_TLS") or "1").strip() not in ("0", "false", "False")

    msg = EmailMessage()
    msg["Subject"] = assunto
    msg["From"] = from_addr
    msg["To"] = para
    msg.set_content(texto)

    if use_tls:
        context = ssl.create_default_context()
        with smtplib.SMTP(host, port, timeout=30) as smtp:
            smtp.starttls(context=context)
            if user:
                smtp.login(user, password)
            smtp.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=30) as smtp:
            if user:
                smtp.login(user, password)
            smtp.send_message(msg)
    return True
