"""Confrontos iniciais das oitavas (mandante da ida = clube_a)."""

from __future__ import annotations

from urllib.parse import quote

OITAVAS = [
    {"id": 1, "clube_a": "Vasco", "clube_b": "Fluminense"},
    {"id": 2, "clube_a": "Atlético-MG", "clube_b": "Juventude"},
    {"id": 3, "clube_a": "Santos", "clube_b": "Remo"},
    {"id": 4, "clube_a": "Palmeiras", "clube_b": "Fortaleza"},
    {"id": 5, "clube_a": "Mirassol", "clube_b": "Grêmio"},
    {"id": 6, "clube_a": "Chapecoense", "clube_b": "Cruzeiro"},
    {"id": 7, "clube_a": "Internacional", "clube_b": "Corinthians"},
    {"id": 8, "clube_a": "Athletico-PR", "clube_b": "Vitória"},
]


def emblema_url(clube: str) -> str:
    """Arquivos em data/emblemas usam o nome do clube (ex.: Vasco.png)."""
    return f"/emblemas/{quote(clube)}.png"
