"""Hall das Lendas — constantes e formatação."""

from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo

TZ_SP = ZoneInfo("America/Sao_Paulo")

BORDAS: tuple[dict[str, str], ...] = (
    {"id": "anel", "rotulo": "Anel ouro", "sample": "A"},
    {"id": "duplo", "rotulo": "Traço duplo", "sample": "D"},
    {"id": "brilho", "rotulo": "Brilho", "sample": "B"},
    {"id": "laurel", "rotulo": "Laureado", "sample": "L"},
)
BORDA_IDS = frozenset(b["id"] for b in BORDAS)
BORDA_PADRAO = "anel"
HALL_POR_PAGINA = 10


def borda_ok(borda: str | None) -> str:
    b = (borda or "").strip().lower()
    return b if b in BORDA_IDS else BORDA_PADRAO


def borda_rotulo(borda: str | None) -> str:
    bid = borda_ok(borda)
    for item in BORDAS:
        if item["id"] == bid:
            return item["rotulo"]
    return "Anel ouro"


def parse_valor_centavos(raw: str | int | float | None) -> int:
    """Aceita 500, '500', '500,00', 'R$ 500.00' → centavos."""
    if raw is None:
        raise ValueError("informe o valor da doação")
    if isinstance(raw, bool):
        raise ValueError("valor inválido")
    if isinstance(raw, int):
        if raw < 0:
            raise ValueError("valor não pode ser negativo")
        # int já em centavos se >= 1000? Treat plain int as reais when small API...
        # Admin forms send reais as string. If int from JSON, treat as centavos only if explicit.
        return raw
    if isinstance(raw, float):
        if raw < 0:
            raise ValueError("valor não pode ser negativo")
        return int(round(raw * 100))
    s = str(raw).strip()
    if not s:
        raise ValueError("informe o valor da doação")
    s = re.sub(r"[Rr]\$\s*", "", s).strip()
    s = s.replace(" ", "")
    if re.fullmatch(r"\d+", s):
        return int(s) * 100
    if "," in s and "." in s:
        # 1.234,56
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        reais = float(s)
    except ValueError as exc:
        raise ValueError("valor inválido") from exc
    if reais < 0:
        raise ValueError("valor não pode ser negativo")
    return int(round(reais * 100))


def format_valor_brl(centavos: int) -> str:
    v = max(0, int(centavos))
    reais = v // 100
    cents = v % 100
    corpo = f"{reais:,}".replace(",", ".")
    return f"R$ {corpo},{cents:02d}"


def format_quando(iso_local: str | None) -> str:
    raw = (iso_local or "").strip()
    if not raw:
        return "—"
    try:
        # 'YYYY-MM-DD HH:MM:SS' ou ISO
        if "T" in raw:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=TZ_SP)
            else:
                dt = dt.astimezone(TZ_SP)
        else:
            dt = datetime.strptime(raw[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=TZ_SP)
        return dt.strftime("%d/%m/%Y · %H:%M")
    except ValueError:
        return raw


def agora_local_iso() -> str:
    return datetime.now(TZ_SP).strftime("%Y-%m-%d %H:%M:%S")
