"""Lembretes automáticos por e-mail para quem ainda não palpitou.

Cadência em faixas (sem flood):
  - 14d: prazo − 14 dias ≤ agora < prazo − 7 dias
  - 7d:  prazo − 7 dias  ≤ agora < prazo − 24 horas
  - 24h: prazo − 24h     ≤ agora < prazo

`prazo` = início do jogo mais próximo entre os que ainda faltam ao participante
(America/São_Paulo). Um e-mail por marco / fase / perna; admin pode forçar
`manual` (cooldown 24h).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from typing import Any, Callable

from src.config import FASES, TRAVA_PALPITE_ANTES_MIN, _TZ_SP, fase_formato
from src import db
from src.mail import enviar_email
from src.seed_data import parse_inicio_em

log = logging.getLogger("thdfm.lembrete_palpites")

MARCOS_AUTO = ("14d", "7d", "24h")
MARCO_MANUAL = "manual"

# (marco, delta_inicio_janela, delta_fim_janela_exclusivo)
_BANDAS: tuple[tuple[str, timedelta, timedelta], ...] = (
    ("14d", timedelta(days=14), timedelta(days=7)),
    ("7d", timedelta(days=7), timedelta(hours=24)),
    ("24h", timedelta(hours=24), timedelta(0)),
)

MARCO_LABEL = {
    "14d": "faltam cerca de 14 dias",
    "7d": "faltam cerca de 7 dias",
    "24h": "faltam menos de 24 horas",
    "manual": "lembrete do admin",
}


def cron_secret() -> str:
    return (os.environ.get("CRON_SECRET") or "").strip()


def _agora_sp(agora: datetime | None = None) -> datetime:
    now = agora or datetime.now(_TZ_SP)
    if now.tzinfo is None:
        now = now.replace(tzinfo=_TZ_SP)
    return now.astimezone(_TZ_SP)


def prazo_mais_proximo(faltando: list[dict[str, Any]]) -> datetime | None:
    """Menor `inicio_em` parseável entre os jogos que faltam."""
    datas: list[datetime] = []
    for j in faltando or []:
        dt = parse_inicio_em(j.get("inicio_em"))
        if dt is None:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_TZ_SP)
        datas.append(dt.astimezone(_TZ_SP))
    return min(datas) if datas else None


def marco_na_banda(prazo: datetime, agora: datetime | None = None) -> str | None:
    """Devolve o marco da faixa atual, ou None se fora de todas."""
    now = _agora_sp(agora)
    if now >= prazo:
        return None
    for marco, inicio, fim in _BANDAS:
        t0 = prazo - inicio
        t1 = prazo - fim
        if t0 <= now < t1:
            return marco
    return None


def fase_label(fase: str) -> str:
    return next((f["label"] for f in FASES if f["id"] == fase), fase)


def perna_label(perna: str) -> str:
    return {"ida": "Ida", "volta": "Volta", "unico": "Jogo"}.get(perna, perna)


def montar_texto_email(
    *,
    nome: str,
    base_url: str,
    token: str,
    fase: str,
    perna: str,
    n_feitos: int,
    n_jogos: int,
    marco: str,
    jogos: list[dict[str, Any]] | None = None,
    agora: datetime | None = None,
) -> tuple[str, str]:
    """Assunto + corpo texto puro."""
    fl = fase_label(fase)
    pl = perna_label(perna)
    primeiro = (nome or "").strip().split()[0] if (nome or "").strip() else ""
    oi = f"Olá, {primeiro}!" if primeiro else "Olá!"
    link = f"{base_url.rstrip('/')}/p/{token}"
    quando = MARCO_LABEL.get(marco, "lembrete")
    assunto = f"THDFM — palpites da {fl} ({quando})"

    if n_jogos > 0 and 0 < n_feitos < n_jogos:
        situacao = (
            f"Você já fez {n_feitos} de {n_jogos} palpites da {fl} ({pl}), "
            "mas ainda falta completar."
        )
    else:
        situacao = (
            f"Ainda não registramos seus palpites da {fl} ({pl}) no Bolão THDFM."
        )

    bloco = db.texto_jogos_proximos_cobranca(jogos or [], agora=agora)
    if bloco:
        jogos_txt = (
            f"{bloco}\n\n"
            f"Os palpites ficam abertos até {TRAVA_PALPITE_ANTES_MIN} min "
            "antes do início de cada partida."
        )
    else:
        jogos_txt = (
            "Os jogos estão próximos — os palpites ficam abertos até "
            f"{TRAVA_PALPITE_ANTES_MIN} min antes do início de cada partida."
        )

    texto = (
        f"{oi}\n\n"
        f"{situacao}\n\n"
        f"{jogos_txt}\n\n"
        f"Acesse seu link pessoal:\n{link}\n\n"
        "Se já palpitou, pode ignorar este e-mail.\n\n"
        "— THDFM\n"
    )
    return assunto, texto


def _email_do_item(item: dict[str, Any]) -> str:
    e = (item.get("email") or "").strip()
    if e and "@" in e:
        return e
    part = db.get_participante(int(item["id"]))
    if not part:
        return ""
    e = (part.get("email") or "").strip()
    return e if e and "@" in e else ""


def _enrich_email(status: dict[str, Any]) -> None:
    """Garante `email` nos incompletos (lookup em lote leve)."""
    for p in status.get("incompletos") or []:
        if p.get("email"):
            continue
        part = db.get_participante(int(p["id"]))
        p["email"] = (part or {}).get("email") or ""


def pernas_da_fase(fase: str) -> tuple[str, ...]:
    if fase_formato(fase) == "unico":
        return ("unico",)
    return ("ida", "volta")


def processar_fase_perna(
    fase: str,
    perna: str,
    *,
    base_url: str,
    agora: datetime | None = None,
    forcar_manual: bool = False,
    enviar: Callable[..., bool] | None = None,
) -> dict[str, Any]:
    """Processa uma fase+perna. Retorna contagens."""
    send = enviar or enviar_email
    now = _agora_sp(agora)
    janela = db.get_janela()
    status = db.status_palpites_liberados(
        fase, perna, so_abertos=True, janela=janela
    )
    _enrich_email(status)

    enviados = 0
    pulados = 0
    sem_email = 0
    erros = 0
    detalhes: list[dict[str, Any]] = []

    for item in status.get("incompletos") or []:
        pid = int(item["id"])
        email = _email_do_item(item)
        if not email:
            sem_email += 1
            continue

        faltando = item.get("faltando_jogos") or []
        prazo = prazo_mais_proximo(faltando)
        if prazo is None:
            pulados += 1
            continue

        if forcar_manual:
            if db.lembrete_palpites_enviado_recente(
                pid, fase, perna, MARCO_MANUAL, horas=24
            ):
                pulados += 1
                continue
            marco = MARCO_MANUAL
        else:
            if now >= prazo:
                pulados += 1
                continue
            marco = marco_na_banda(prazo, agora=now)
            if not marco:
                pulados += 1
                continue
            if db.lembrete_palpites_ja_enviado(pid, fase, perna, marco):
                pulados += 1
                continue

        assunto, texto = montar_texto_email(
            nome=item.get("nome") or "",
            base_url=base_url,
            token=item.get("token") or "",
            fase=fase,
            perna=perna,
            n_feitos=int(item.get("n_feitos") or 0),
            n_jogos=int(item.get("n_jogos") or 0),
            marco=marco,
            jogos=faltando,
            agora=now,
        )
        try:
            ok = send(para=email, assunto=assunto, texto=texto)
            if not ok:
                erros += 1
                continue
            db.registrar_lembrete_palpites(
                participante_id=pid,
                fase=fase,
                perna=perna,
                marco=marco,
                email=email,
                prazo_inicio_em=prazo.strftime("%Y-%m-%d %H:%M"),
            )
            enviados += 1
            detalhes.append(
                {
                    "participante_id": pid,
                    "email": email,
                    "marco": marco,
                    "fase": fase,
                    "perna": perna,
                }
            )
        except Exception as exc:  # noqa: BLE001 — job não pode morrer no 1º erro
            log.exception("falha ao enviar lembrete pid=%s: %s", pid, exc)
            erros += 1

    return {
        "fase": fase,
        "perna": perna,
        "n_incompletos": int(status.get("n_incompletos") or 0),
        "enviados": enviados,
        "pulados": pulados,
        "sem_email": sem_email,
        "erros": erros,
        "detalhes": detalhes,
    }


def rodar_job(
    *,
    base_url: str,
    agora: datetime | None = None,
    forcar_manual: bool = False,
    fase: str | None = None,
    perna: str | None = None,
    enviar: Callable[..., bool] | None = None,
) -> dict[str, Any]:
    """Job completo: fase atual (ou escopo admin) × pernas relevantes."""
    base = (base_url or "").rstrip("/") or "https://thdfm.com.br"
    fase_alvo = (fase or db.get_fase_atual() or "oitavas").strip()
    por_perna: list[dict[str, Any]] = []

    if perna:
        alvos = (perna,)
    else:
        alvos = pernas_da_fase(fase_alvo)

    total = {
        "enviados": 0,
        "pulados": 0,
        "sem_email": 0,
        "erros": 0,
    }
    for p in alvos:
        r = processar_fase_perna(
            fase_alvo,
            p,
            base_url=base,
            agora=agora,
            forcar_manual=forcar_manual,
            enviar=enviar,
        )
        por_perna.append(r)
        for k in total:
            total[k] += int(r.get(k) or 0)

    return {
        "ok": True,
        "fase": fase_alvo,
        "forcar_manual": forcar_manual,
        "agora": _agora_sp(agora).isoformat(),
        **total,
        "por_perna": por_perna,
    }
