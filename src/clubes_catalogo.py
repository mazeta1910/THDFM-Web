"""Catálogo de clubes BR (FM24) com UF, emblema e reputação por Unique ID."""

from __future__ import annotations

import csv
import re
from functools import lru_cache
from pathlib import Path

from src.config import CLUBES_BRASIL_CSV_PATH, CLUBES_CSV_PATH, EMBLEMAS_FM_DIR

# Teto levemente acima do máximo FM (~7750) para o score inverso de desempate.
REP_TETO = 8000


def unique_id_arquivo(unique_id: str) -> str:
    """301.260 → 301260"""
    return re.sub(r"\D", "", unique_id or "")


def emblema_fm_url(unique_id: str) -> str:
    dig = unique_id_arquivo(unique_id)
    return f"/emblemas-fm/{dig}.png" if dig else ""


def parse_rep_fm(raw: str | None) -> int:
    """'1.450' / '7750' / '400' → int (pontos de reputação FM)."""
    s = (raw or "").strip().replace(".", "").replace(",", "")
    if not s or not s.isdigit():
        return 0
    return int(s)


def pontos_rep_desempate(rep: int | None) -> int:
    """Quanto menor a reputação FM, mais pontos no desempate do ranking.

    Flamengo (~7750) → poucos pontos; clube obscuro (~400) → muitos.
    """
    r = max(0, int(rep or 0))
    return max(1, REP_TETO - r)


@lru_cache(maxsize=1)
def _mapa_rep_brasil() -> dict[str, int]:
    path = Path(CLUBES_BRASIL_CSV_PATH)
    if not path.is_file():
        return {}
    # Dump FM costuma vir em latin-1 / cp1252.
    for enc in ("latin-1", "cp1252", "utf-8-sig"):
        try:
            text = path.read_text(encoding=enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        return {}
    out: dict[str, int] = {}
    for r in csv.DictReader(text.splitlines(), delimiter=";"):
        uid = (r.get("Unique ID") or "").strip()
        if not uid:
            continue
        rep = parse_rep_fm(r.get("Rep"))
        if rep > 0:
            out[uid] = rep
    return out


@lru_cache(maxsize=1)
def carregar_clubes() -> tuple[dict, ...]:
    path = Path(CLUBES_CSV_PATH)
    if not path.is_file():
        return tuple()
    text = path.read_text(encoding="utf-8-sig")
    rows = list(csv.DictReader(text.splitlines(), delimiter=";"))
    reps = _mapa_rep_brasil()
    out: list[dict] = []
    for r in rows:
        uid = (r.get("Unique ID") or "").strip()
        name = (r.get("Name") or "").strip()
        uf = (r.get("UF") or "").strip().upper()
        if not uid or not name or not uf:
            continue
        dig = unique_id_arquivo(uid)
        rep = int(reps.get(uid) or 0)
        out.append(
            {
                "id": uid,
                "id_arquivo": dig,
                "nome": name,
                "uf": uf,
                "divisao": (r.get("Division") or "").strip(),
                "emblema": f"/emblemas-fm/{dig}.png",
                "tem_emblema": (EMBLEMAS_FM_DIR / f"{dig}.png").is_file(),
                "rep": rep,
            }
        )
    out.sort(key=lambda c: (c["nome"].casefold(), c["uf"]))
    return tuple(out)


def contagem_por_uf() -> dict[str, int]:
    counts: dict[str, int] = {}
    for c in carregar_clubes():
        counts[c["uf"]] = counts.get(c["uf"], 0) + 1
    return counts


def limpar_cache_clubes() -> None:
    carregar_clubes.cache_clear()
    _mapa_rep_brasil.cache_clear()
