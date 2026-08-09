"""Catálogo de clubes BR (FM24) com UF e emblema por Unique ID."""

from __future__ import annotations

import csv
import re
from functools import lru_cache
from pathlib import Path

from src.config import CLUBES_CSV_PATH, EMBLEMAS_FM_DIR


def unique_id_arquivo(unique_id: str) -> str:
    """301.260 → 301260"""
    return re.sub(r"\D", "", unique_id or "")


def emblema_fm_url(unique_id: str) -> str:
    dig = unique_id_arquivo(unique_id)
    return f"/emblemas-fm/{dig}.png" if dig else ""


@lru_cache(maxsize=1)
def carregar_clubes() -> tuple[dict, ...]:
    path = Path(CLUBES_CSV_PATH)
    if not path.is_file():
        return tuple()
    text = path.read_text(encoding="utf-8-sig")
    rows = list(csv.DictReader(text.splitlines(), delimiter=";"))
    out: list[dict] = []
    for r in rows:
        uid = (r.get("Unique ID") or "").strip()
        name = (r.get("Name") or "").strip()
        uf = (r.get("UF") or "").strip().upper()
        if not uid or not name or not uf:
            continue
        dig = unique_id_arquivo(uid)
        out.append(
            {
                "id": uid,
                "id_arquivo": dig,
                "nome": name,
                "uf": uf,
                "divisao": (r.get("Division") or "").strip(),
                "emblema": f"/emblemas-fm/{dig}.png",
                "tem_emblema": (EMBLEMAS_FM_DIR / f"{dig}.png").is_file(),
            }
        )
    out.sort(key=lambda c: (c["nome"].casefold(), c["uf"]))
    return tuple(out)


def contagem_por_uf() -> dict[str, int]:
    counts: dict[str, int] = {}
    for c in carregar_clubes():
        counts[c["uf"]] = counts.get(c["uf"], 0) + 1
    return counts
