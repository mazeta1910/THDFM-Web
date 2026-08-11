"""Confrontos iniciais das oitavas (mandante da ida = clube_a)."""

from __future__ import annotations

from datetime import datetime, timedelta
from urllib.parse import quote

from src.config import TRAVA_PALPITE_ANTES_MIN, _TZ_SP

# Horários oficiais (tabela / Google). Formato: YYYY-MM-DD HH:MM
# Ida: clube_a mandante. Volta: clube_b mandante.
OITAVAS = [
    {
        "id": 1,
        "clube_a": "Vasco",
        "clube_b": "Fluminense",
        "ida_em": "2026-08-01 17:30",
        "volta_em": "2026-08-05 21:30",
    },
    {
        "id": 2,
        "clube_a": "Atlético-MG",
        "clube_b": "Juventude",
        "ida_em": "2026-08-01 19:30",
        "volta_em": "2026-08-04 19:30",
    },
    {
        "id": 3,
        "clube_a": "Santos",
        "clube_b": "Remo",
        "ida_em": "2026-08-01 21:00",
        "volta_em": "2026-08-04 21:30",
    },
    {
        "id": 4,
        "clube_a": "Palmeiras",
        "clube_b": "Fortaleza",
        "ida_em": "2026-08-02 16:00",
        "volta_em": "2026-08-05 21:30",
    },
    {
        "id": 5,
        "clube_a": "Mirassol",
        "clube_b": "Grêmio",
        "ida_em": "2026-08-02 18:00",
        "volta_em": "2026-08-05 19:30",
    },
    {
        "id": 6,
        "clube_a": "Chapecoense",
        "clube_b": "Cruzeiro",
        "ida_em": "2026-08-02 18:30",
        "volta_em": "2026-08-05 19:00",
    },
    {
        "id": 7,
        "clube_a": "Internacional",
        "clube_b": "Corinthians",
        "ida_em": "2026-08-02 19:30",
        "volta_em": "2026-08-06 20:00",
    },
    {
        "id": 8,
        "clube_a": "Athletico-PR",
        "clube_b": "Vitória",
        "ida_em": "2026-08-03 21:00",
        "volta_em": "2026-08-06 20:00",
    },
]

# Quartas 2026: clube_a manda na ida; clube_b decide em casa na volta.
# Ordem das chaves = foto oficial (quartas 1–4).
QUARTAS = [
    {"clube_a": "Internacional", "clube_b": "Grêmio"},  # GRE decide em casa
    {"clube_a": "Cruzeiro", "clube_b": "Atlético-MG"},  # Galo decide em casa
    {"clube_a": "Vasco", "clube_b": "Vitória"},  # Vitória decide em casa
    {"clube_a": "Palmeiras", "clube_b": "Santos"},  # Santos decide em casa
]

_WEEKDAYS_PT = ("Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom")

# Nomes curtos para grids compactos (mobile 2 colunas). Emblemas usam o nome completo.
CLUBE_NOME_CURTO = {
    "Internacional": "Inter",
    "Corinthians": "Corinthians",
    "Chapecoense": "Chape",
    "Fluminense": "Flu",
    "Athletico-PR": "Athletico",
    "Atlético-MG": "Atlético-MG",
    "Fortaleza": "Fortaleza",
    "Juventude": "Juventude",
}


def nome_clube_curto(clube: str | None) -> str:
    """Rótulo curto para UI apertada; mantém o nome original se não houver mapa."""
    if not clube:
        return ""
    nome = str(clube).strip()
    return CLUBE_NOME_CURTO.get(nome, nome)


def emblema_url(clube: str) -> str:
    """Arquivos em data/emblemas usam o nome do clube (ex.: Vasco.png)."""
    return f"/emblemas/{quote(clube)}.png"


def parse_inicio_em(inicio_em: str | None) -> datetime | None:
    """Converte texto do banco/form em datetime aware (America/Sao_Paulo)."""
    if not inicio_em:
        return None
    raw = str(inicio_em).strip().replace("T", " ")
    for fmt, n in (("%Y-%m-%d %H:%M:%S", 19), ("%Y-%m-%d %H:%M", 16)):
        try:
            dt = datetime.strptime(raw[:n], fmt)
            return dt.replace(tzinfo=_TZ_SP)
        except ValueError:
            continue
    return None


def formatar_inicio_jogo(inicio_em: str | None) -> str:
    """Ex.: '2026-08-01 17:30' → 'Sáb 01/08 17:30'."""
    dt = parse_inicio_em(inicio_em)
    if dt is None:
        return str(inicio_em).strip() if inicio_em else ""
    return f"{_WEEKDAYS_PT[dt.weekday()]} {dt.strftime('%d/%m')} {dt.strftime('%H:%M')}"


def inicio_em_input_value(inicio_em: str | None) -> str:
    """Valor para <input type='datetime-local'>."""
    dt = parse_inicio_em(inicio_em)
    if dt is None:
        return ""
    return dt.strftime("%Y-%m-%dT%H:%M")


def jogo_palpite_travado(
    inicio_em: str | None,
    *,
    agora: datetime | None = None,
    janela: str | None = None,
) -> bool:
    """True se o placar daquele jogo não pode mais ser editado.

    - Janela fechado: tudo travado.
    - Com horário: trava TRAVA_PALPITE_ANTES_MIN antes do apito.
    - Sem horário: só a janela manda (compatível com jogos antigos).
    """
    if janela == "fechado":
        return True
    dt = parse_inicio_em(inicio_em)
    if dt is None:
        return False
    now = agora or datetime.now(_TZ_SP)
    if now.tzinfo is None:
        now = now.replace(tzinfo=_TZ_SP)
    return now >= (dt - timedelta(minutes=TRAVA_PALPITE_ANTES_MIN))


def normalizar_inicio_em(valor: str | None) -> str | None:
    """Aceita datetime-local ou 'YYYY-MM-DD HH:MM' e grava no formato do banco."""
    dt = parse_inicio_em(valor)
    if dt is None:
        return None
    return dt.strftime("%Y-%m-%d %H:%M")
