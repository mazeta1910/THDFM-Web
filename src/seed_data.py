"""Confrontos iniciais das oitavas (mandante da ida = clube_a)."""

from __future__ import annotations

from datetime import datetime
from urllib.parse import quote

# Horários da ida (tabela oficial / Google). Formato: YYYY-MM-DD HH:MM
OITAVAS = [
    {"id": 1, "clube_a": "Vasco", "clube_b": "Fluminense", "ida_em": "2026-08-01 17:30"},
    {"id": 2, "clube_a": "Atlético-MG", "clube_b": "Juventude", "ida_em": "2026-08-01 19:30"},
    {"id": 3, "clube_a": "Santos", "clube_b": "Remo", "ida_em": "2026-08-01 21:00"},
    {"id": 4, "clube_a": "Palmeiras", "clube_b": "Fortaleza", "ida_em": "2026-08-02 16:00"},
    {"id": 5, "clube_a": "Mirassol", "clube_b": "Grêmio", "ida_em": "2026-08-02 18:00"},
    {"id": 6, "clube_a": "Chapecoense", "clube_b": "Cruzeiro", "ida_em": "2026-08-02 18:30"},
    {"id": 7, "clube_a": "Internacional", "clube_b": "Corinthians", "ida_em": "2026-08-02 19:30"},
    {"id": 8, "clube_a": "Athletico-PR", "clube_b": "Vitória", "ida_em": "2026-08-03 21:00"},
]

_WEEKDAYS_PT = ("Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom")


def emblema_url(clube: str) -> str:
    """Arquivos em data/emblemas usam o nome do clube (ex.: Vasco.png)."""
    return f"/emblemas/{quote(clube)}.png"


def formatar_inicio_jogo(inicio_em: str | None) -> str:
    """Ex.: '2026-08-01 17:30' → 'Sáb 01/08 17:30'."""
    if not inicio_em:
        return ""
    raw = str(inicio_em).strip().replace("T", " ")
    dt = None
    for fmt, n in (("%Y-%m-%d %H:%M:%S", 19), ("%Y-%m-%d %H:%M", 16)):
        try:
            dt = datetime.strptime(raw[:n], fmt)
            break
        except ValueError:
            continue
    if dt is None:
        return raw
    return f"{_WEEKDAYS_PT[dt.weekday()]} {dt.strftime('%d/%m')} {dt.strftime('%H:%M')}"
