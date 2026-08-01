"""Acervos da Listra THDFM por ano."""

from __future__ import annotations

import json
from pathlib import Path

LISTRA_ANO_ATUAL = 2026
LISTRA_ANOS = (2026, 2025, 2024)

_DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "listra"


def _carregar_arquivo(ano: int) -> tuple[str, ...]:
    path = _DATA_DIR / f"{ano}.json"
    if not path.is_file():
        return ()
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        return ()
    out: list[str] = []
    for item in raw:
        texto = str(item).strip()
        if texto:
            out.append(texto)
    return tuple(out)


def listra_titulo(ano: int) -> str:
    return f"LISTRA THDFM {ano}"


def listra_seed_por_ano(ano: int) -> tuple[str, ...]:
    return _carregar_arquivo(int(ano))


def __getattr__(name: str):
    if name == "LISTRA_SEED_FRASES":
        return listra_seed_por_ano(LISTRA_ANO_ATUAL)
    if name == "LISTRA_TITULO":
        return listra_titulo(LISTRA_ANO_ATUAL)
    raise AttributeError(name)
