#!/usr/bin/env python3
"""Extrai classificacao completa da Serie B a partir de Serie B.xlsx.

O arquivo tem a aba 'Brasileirao Serie B' com blocos por ano espalhados
em linhas/colunas (dump de tabelas), nao uma aba por temporada.
"""
from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

try:
    import openpyxl
except ImportError:
    print("Instale openpyxl: pip install openpyxl", file=sys.stderr)
    raise SystemExit(1)

ROOT = Path(__file__).resolve().parents[1]
XLSX = ROOT / "data" / "torneios" / "Serie B.xlsx"
SHEET = "Brasileirao Serie B"
OUT = ROOT / "data" / "torneios" / "classificacoes_serie_b.csv"
FIELDNAMES = [
    "competicao",
    "ano",
    "posicao",
    "n_clubes",
    "nome",
    "pts",
    "j",
    "v",
    "e",
    "d",
    "gp",
    "gc",
    "sg",
    "fonte_url",
]

HEADER_CLUB = {"time", "equipe", "equipes", "clube"}
HEADER_PTS = {"pts", "pontos", "pg", "p"}
STOP_CLUB = {
    "clube",
    "time",
    "equipe",
    "equipes",
    "pos",
    "campeão",
    "campeao",
    "vice-campeão",
    "vice-campeao",
    "promovido(s)",
    "rebaixado(s)",
    "estatísticas",
    "estatisticas",
    "colocações finais",
    "colocacoes finais",
    "melhor marcador",
    "melhor ataque",
    "melhor defesa",
    "maior goleada",
    "(diferença)",
    "(diferenca)",
    "tabela de classificação",
    "tabela de classificacao",
}


def _norm(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    if isinstance(v, int) and not isinstance(v, bool):
        return str(v)
    s = str(v).replace("\xa0", " ").strip()
    return s.replace("–", "-").replace("—", "-").replace("−", "-")


def _as_int(s: str) -> int | None:
    s = _norm(s)
    if re.fullmatch(r"-?\d+", s):
        return int(s)
    return None


def _is_year(s: str) -> bool:
    return bool(re.fullmatch(r"(19|20)\d{2}", s)) and 1971 <= int(s) <= 2030


def _looks_club(name: str) -> bool:
    if not name or len(name) < 2:
        return False
    low = name.lower()
    if low in STOP_CLUB:
        return False
    if re.fullmatch(r"\d+", name):
        return False
    return bool(re.search(r"[A-Za-zÀ-ÿ]", name))


def _clean_club(name: str) -> str:
    name = re.sub(r"\s*\(C\)\s*$", "", name, flags=re.I).strip()
    name = re.sub(r"\s*\(.*?\)\s*$", "", name).strip()
    name = re.sub(r"\d+$", "", name).strip()
    return name


def _fmt_sg(sg: int | None) -> str:
    if sg is None:
        return ""
    return f"+{sg}" if sg > 0 else str(sg)


def _load_grid(path: Path) -> list[list[str]]:
    wb = openpyxl.load_workbook(path, data_only=True, read_only=False)
    if SHEET not in wb.sheetnames:
        wb.close()
        raise FileNotFoundError(f"Aba '{SHEET}' nao encontrada em {path.name}")
    ws = wb[SHEET]
    grid = [
        [_norm(ws.cell(r, c).value) for c in range(1, ws.max_column + 1)]
        for r in range(1, ws.max_row + 1)
    ]
    wb.close()
    return grid


def _map_header_row(row: list[str], yc: int) -> dict[str, int] | None:
    mapping: dict[str, int] = {}
    for j in range(max(0, yc - 2), min(len(row), yc + 22)):
        t = row[j].lower()
        if not t:
            continue
        if t in {"#", "pos", "posição", "posicao", "class."} or t.startswith("pos"):
            mapping.setdefault("posicao", j)
        elif t in HEADER_CLUB or "clube" in t or "time" in t or "equipe" in t:
            mapping.setdefault("clube", j)
        elif t in HEADER_PTS or t.startswith("pt"):
            mapping.setdefault("pts", j)
        elif t in {"j", "jogos", "pj"}:
            mapping.setdefault("j", j)
        elif t in {"v", "vit", "vitórias", "vitorias"}:
            mapping.setdefault("v", j)
        elif t in {"e", "emp", "empates"}:
            mapping.setdefault("e", j)
        elif t in {"d", "der", "derrotas"}:
            mapping.setdefault("d", j)
        elif t in {"gp", "gf", "gols pró", "gols pro"}:
            mapping.setdefault("gp", j)
        elif t in {"gc", "ga", "gols contra"}:
            mapping.setdefault("gc", j)
        elif t in {"sg", "saldo"}:
            mapping.setdefault("sg", j)
    if "pts" in mapping and "clube" in mapping:
        return mapping
    return None


def _find_header(grid: list[list[str]], yr: int, yc: int) -> tuple[int, dict[str, int]] | None:
    best: tuple[int, int, dict[str, int]] | None = None
    for r in range(yr, min(yr + 45, len(grid))):
        mapping = _map_header_row(grid[r], yc)
        if not mapping:
            continue
        dist = abs(mapping["clube"] - yc) + (r - yr)
        if best is None or dist < best[0]:
            best = (dist, r, mapping)
    if best is None:
        return None
    return best[1], best[2]


def _parse_block(
    grid: list[list[str]], ano: int, hr: int, mapping: dict[str, int]
) -> list[dict]:
    out: list[dict] = []
    for r in range(hr + 1, min(hr + 40, len(grid))):
        row = grid[r]
        ci = mapping["clube"]
        clube = row[ci] if ci < len(row) else ""
        if not _looks_club(clube):
            alt = row[ci + 1] if ci + 1 < len(row) else ""
            if _as_int(clube) is not None and _looks_club(alt):
                clube = alt
            else:
                if out:
                    break
                continue
        pts = _as_int(row[mapping["pts"]]) if mapping["pts"] < len(row) else None
        if pts is None:
            if out:
                break
            continue

        def grab(key: str) -> int | None:
            j = mapping.get(key)
            if j is None or j >= len(row):
                return None
            return _as_int(row[j])

        pos = grab("posicao")
        if pos is None and ci > 0:
            pos = _as_int(row[ci - 1])
        if pos is None and _as_int(row[ci]) is not None:
            pos = _as_int(row[ci])
        if pos is None:
            pos = len(out) + 1

        jg, v, e, d = grab("j"), grab("v"), grab("e"), grab("d")
        gp, gc, sg = grab("gp"), grab("gc"), grab("sg")
        if sg is None and gp is not None and gc is not None:
            sg = gp - gc
        if jg is None and None not in (v, e, d):
            jg = (v or 0) + (e or 0) + (d or 0)

        out.append(
            {
                "ano": ano,
                "posicao": pos,
                "nome": _clean_club(clube),
                "pts": pts,
                "j": jg,
                "v": v,
                "e": e,
                "d": d,
                "gp": gp,
                "gc": gc,
                "sg": sg,
            }
        )
        if len(out) >= 28:
            break
    return out


def _tabela_confiavel(block: list[dict]) -> bool:
    """Descarta fases de grupo / dumps incompletos da wiki."""
    if len(block) < 16:
        return False
    ano = int(block[0]["ano"])
    if ano >= 2006:
        return True
    js = [r["j"] for r in block if r.get("j") is not None]
    # Pré-2006: só tabelas em que todos jogaram o mesmo nº de partidas.
    return len(js) == len(block) and len(set(js)) == 1


def extract_rows(path: Path = XLSX) -> list[dict]:
    grid = _load_grid(path)
    years: list[tuple[int, int, int]] = []
    for r, row in enumerate(grid):
        for c, val in enumerate(row):
            if _is_year(val):
                years.append((r, c, int(val)))

    by_ano: dict[int, list[dict]] = {}
    for yr, yc, ano in years:
        found = _find_header(grid, yr, yc)
        if not found:
            continue
        hr, mapping = found
        block = _parse_block(grid, ano, hr, mapping)
        prev = by_ano.get(ano)
        if prev is None or len(block) > len(prev):
            by_ano[ano] = block

    rows: list[dict] = []
    for ano in sorted(by_ano):
        block = by_ano[ano]
        if not _tabela_confiavel(block):
            continue
        n = len(block)
        for r in block:
            sg = r["sg"]
            rows.append(
                {
                    "competicao": "serie_b",
                    "ano": ano,
                    "posicao": r["posicao"],
                    "n_clubes": n,
                    "nome": r["nome"],
                    "pts": r["pts"] if r["pts"] is not None else "",
                    "j": r["j"] if r["j"] is not None else "",
                    "v": r["v"] if r["v"] is not None else "",
                    "e": r["e"] if r["e"] is not None else "",
                    "d": r["d"] if r["d"] is not None else "",
                    "gp": r["gp"] if r["gp"] is not None else "",
                    "gc": r["gc"] if r["gc"] is not None else "",
                    "sg": _fmt_sg(sg) if isinstance(sg, int) else "",
                    "fonte_url": "",
                }
            )
    return rows


def main() -> int:
    if not XLSX.is_file():
        print(f"Arquivo nao encontrado: {XLSX}", file=sys.stderr)
        return 1
    rows = extract_rows()
    if not rows:
        print("Nenhuma tabela confiavel extraida do xlsx.", file=sys.stderr)
        return 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDNAMES, delimiter=";")
        w.writeheader()
        w.writerows(rows)
    anos = sorted({int(r["ano"]) for r in rows})
    print(
        f"OK {OUT.relative_to(ROOT)}: {len(rows)} linhas, "
        f"anos {anos[0]}-{anos[-1]} ({len(anos)} temporadas)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
