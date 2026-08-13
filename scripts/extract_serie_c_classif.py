#!/usr/bin/env python3
"""Extrai classificações finais da Série C (xlsx wiki dump) → CSV do Grid.

Também anexa participantes da edição em andamento (lista do Serie C.CSV),
sem estatísticas — só para participação/longevidade no Grid.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "torneios" / "Série C.xlsx"
CSV_SRC = ROOT / "data" / "torneios" / "Serie C.CSV"
OUT = ROOT / "data" / "torneios" / "classificacoes_serie_c.csv"

FIELDS = [
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


def is_year(v) -> int | None:
    if isinstance(v, int) and 1970 <= v <= 2030:
        return v
    if isinstance(v, str) and re.match(r"^\d{4}$", v.strip()):
        return int(v)
    return None


def to_int(v) -> int | None:
    if v is None:
        return None
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return int(v)
    s = str(v).strip().replace("–", "-").replace("−", "-")
    if not s or s in "-—":
        return None
    m = re.search(r"-?\d+", s)
    return int(m.group()) if m else None


def clean_name(v) -> str:
    if v is None:
        return ""
    s = str(v).replace("\xa0", " ").strip()
    s = re.sub(r"\[[^\]]*\]", "", s)
    s = re.sub(r"\s*\([^)]*\)\s*", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _cells(row, n: int = 12) -> list[str]:
    return [(str(c).casefold().strip() if c is not None else "") for c in row[:n]]


def _is_header(cells: list[str]) -> bool:
    c0 = cells[0] if cells else ""
    clubish = any(
        c in ("times", "time", "equipes", "equipe", "clubes", "clube", "team")
        for c in cells
    )
    # Pos / Posição + clube
    if c0 in ("pos", "posição", "posicao", "pos.") and clubish:
        return True
    # Time/Team + Pts/PG (1998/1999/2006)
    if c0 in ("time", "team") and any(c in ("pts", "pg", "p") for c in cells):
        return True
    # C. / C + Time (1988–2003)
    if c0 in ("c", "c.", "class.", "class") and clubish:
        return True
    # 2013 wiki quebrado: Pos | v | Pts ...
    if c0 in ("pos", "posição", "posicao") and any(c in ("pts", "pg", "p") for c in cells):
        return True
    return False


def _parse_header_map(hdr: list[str]) -> dict[str, int]:
    def col(*names: str, after: int | None = None) -> int | None:
        for n in names:
            for k, h in enumerate(hdr):
                if h == n and (after is None or k > after):
                    return k
        return None

    c_pos = col("pos", "posição", "posicao", "pos.", "c", "c.", "class.", "class")
    c_nome = col("times", "time", "equipes", "equipe", "clubes", "clube", "team")
    # Cabeçalho "Time | (vazio) | Pts" — posição na col 0 dos dados, clube na col 1.
    if c_nome == 0 and len(hdr) > 1 and hdr[1] == "" and c_pos is None:
        c_pos = 0
        c_nome = 1
    # 2013: coluna do clube aparece algumas linhas abaixo como "Equipes"
    if c_nome is None and len(hdr) > 1 and hdr[1] in {"v", "d", "e", ""}:
        c_nome = 1
    c_pts = col("pts", "pg", "p")
    # Em 2013 o header traz "v" lixo antes de Pts; pegar V/E/D depois de Pts.
    anchor = c_pts if c_pts is not None else (c_nome or 0)
    return {
        "posicao": c_pos if c_pos is not None else 0,
        "nome": c_nome if c_nome is not None else 1,
        "pts": c_pts,
        "j": col("j", after=anchor - 1 if c_pts is not None else None),
        "v": col("v", after=anchor),
        "e": col("e", after=anchor),
        "d": col("d", after=anchor),
        "gp": col("gp", "gf", "gm", after=anchor),
        "gc": col("gc", "gs", after=anchor),
    }


def _read_block(rows, header_idx: int, mapping: dict[str, int], until_year: bool = True) -> list[dict]:
    block: list[dict] = []
    c_pos = mapping["posicao"]
    c_nome = mapping["nome"]
    started = False
    for j in range(header_idx + 1, min(header_idx + 120, len(rows))):
        r = rows[j]
        if until_year and is_year(r[0]):
            break
        # Próximo cabeçalho de grupo (mesmo ano)
        cells = _cells(r)
        if started and _is_header(cells):
            break
        # Pula linhas de lixo do header quebrado (2013: v/d/e/Equipes)
        raw_nome = r[c_nome] if c_nome < len(r) else None
        nome = clean_name(raw_nome)
        if nome.casefold() in {"equipes", "equipe", "times", "time", "v", "d", "e", "clubes", "clube"}:
            continue
        pos = to_int(r[c_pos] if c_pos < len(r) else None)
        if pos is None or not nome:
            # Separador em branco no meio da tabela (ex.: 2013) — continua.
            if all(x is None or str(x).strip() == "" for x in r[:8]):
                continue
            continue
        if re.fullmatch(r"\d+", nome):
            continue
        if nome.casefold().startswith("grupo ") or nome.casefold() in {
            "primeira fase",
            "segunda fase",
            "classificação geral",
            "classificacao geral",
            "promovidos à série b",
            "promovidos a serie b",
        }:
            continue
        if pos < 1 or pos > 80:
            continue
        # Exige ao menos pts ou gp para não engolir títulos de seção
        pts_v = to_int(r[mapping["pts"]]) if mapping["pts"] is not None else None
        gp = to_int(r[mapping["gp"]]) if mapping["gp"] is not None else None
        gc = to_int(r[mapping["gc"]]) if mapping["gc"] is not None else None
        if pts_v is None and gp is None:
            continue
        block.append(
            {
                "competicao": "serie_c",
                "ano": 0,  # preenchido pelo caller
                "posicao": pos,
                "n_clubes": 0,
                "nome": nome,
                "pts": pts_v if pts_v is not None else "",
                "j": to_int(r[mapping["j"]]) if mapping["j"] is not None else "",
                "v": to_int(r[mapping["v"]]) if mapping["v"] is not None else "",
                "e": to_int(r[mapping["e"]]) if mapping["e"] is not None else "",
                "d": to_int(r[mapping["d"]]) if mapping["d"] is not None else "",
                "gp": gp if gp is not None else "",
                "gc": gc if gc is not None else "",
                "sg": (
                    f"{gp - gc:+d}"
                    if gp is not None and gc is not None and gp - gc != 0
                    else ("0" if gp is not None and gc is not None else "")
                ),
                "fonte_url": "",
            }
        )
        started = True
    return block


def extract_xlsx_classif() -> list[dict]:
    wb = openpyxl.load_workbook(SRC, read_only=True, data_only=True)
    rows = list(wb["Planilha1"].iter_rows(values_only=True))
    wb.close()

    # Índices de anos
    year_rows: list[tuple[int, int]] = []
    for i, r in enumerate(rows):
        y = is_year(r[0]) if r else None
        if y and y <= 2025:
            year_rows.append((i, y))

    out: list[dict] = []
    for idx, (i, y) in enumerate(year_rows):
        end = year_rows[idx + 1][0] if idx + 1 < len(year_rows) else len(rows)
        # Todos os cabeçalhos de tabela neste ano (final ou grupos)
        headers: list[int] = []
        for j in range(i, end):
            if _is_header(_cells(rows[j])):
                headers.append(j)

        merged: list[dict] = []
        seen: set[str] = set()
        for hi in headers:
            hdr = _cells(rows[hi])
            mapping = _parse_header_map(hdr)
            block = _read_block(rows, hi, mapping, until_year=True)
            for b in block:
                k = b["nome"].casefold()
                if k in seen:
                    # Preferir linha com mais stats se duplicar entre grupos
                    prev = next(x for x in merged if x["nome"].casefold() == k)
                    if prev["gp"] == "" and b["gp"] != "":
                        merged.remove(prev)
                        seen.discard(k)
                    else:
                        continue
                seen.add(k)
                nb = dict(b)
                nb["ano"] = y
                merged.append(nb)

        with_stats = sum(1 for b in merged if b["gp"] != "" and b["gc"] != "")
        # Tabela final típica 8–40; fases de grupo podem passar de 40 (ex.: 2008).
        ok = (
            len(merged) >= 8
            and with_stats >= max(4, len(merged) // 2)
            and all(bool(b["nome"]) for b in merged)
        )
        if ok:
            # Reindexa só quando veio de várias tabelas de grupo.
            if len(headers) > 1:
                def sort_key(b: dict):
                    pts = b["pts"] if isinstance(b["pts"], int) else -1
                    gp = b["gp"] if isinstance(b["gp"], int) else -1
                    return (-pts, -gp, b["nome"])

                merged = sorted(merged, key=sort_key)
                for n, b in enumerate(merged, start=1):
                    b["posicao"] = n
            n = max(b["posicao"] for b in merged)
            for b in merged:
                b["n_clubes"] = n
            out.extend(sorted(merged, key=lambda x: x["posicao"]))
            print(f"OK {y}: {len(merged)} champ={merged[0]['nome']!r} headers={len(headers)}")
        else:
            bad = [
                b["nome"]
                for b in merged
                if not b["nome"] or (b["nome"] and b["nome"][0].isdigit())
            ]
            print(
                f"SKIP {y} n={len(merged)} stats={with_stats} headers={len(headers)} bad={bad[:5]}"
            )
    return out


_UF_RE = re.compile(r"^[A-Z]{2}$")


def extract_csv_participantes_ano(ano: int) -> list[dict]:
    """Lista de participantes (sem pts) a partir do dump Serie C.CSV."""
    if not CSV_SRC.is_file():
        return []
    text = CSV_SRC.read_text(encoding="latin-1")
    rows = [list(csv.reader([ln], delimiter=";"))[0] for ln in text.splitlines()]
    start = None
    for i, r in enumerate(rows):
        if r and is_year(r[0]) == ano:
            start = i
            break
    if start is None:
        return []
    nomes: list[str] = []
    for r in rows[start + 1 :]:
        if r and is_year(r[0]):
            break
        if len(r) < 3:
            continue
        nome = clean_name(r[0])
        uf = (r[2] or "").replace("\xa0", " ").strip().upper()
        if not nome or not _UF_RE.match(uf):
            continue
        if nome.isdigit():
            continue
        nomes.append(nome)
    out: list[dict] = []
    n = len(nomes)
    for i, nome in enumerate(nomes, start=1):
        out.append(
            {
                "competicao": "serie_c",
                "ano": ano,
                "posicao": i,
                "n_clubes": n,
                "nome": nome,
                "pts": "",
                "j": "",
                "v": "",
                "e": "",
                "d": "",
                "gp": "",
                "gc": "",
                "sg": "",
                "fonte_url": "",
            }
        )
    return out


def main() -> None:
    out = extract_xlsx_classif()
    anos_com_tabela = {int(r["ano"]) for r in out}
    for ano in range(2026, 2031):
        if ano in anos_com_tabela:
            continue
        part = extract_csv_participantes_ano(ano)
        if len(part) >= 16:
            out.extend(part)
            print(f"PARTICIPANTES {ano}: {len(part)} (sem estatísticas)")
            print("  " + ", ".join(p["nome"] for p in part))
    with OUT.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, delimiter=";")
        w.writeheader()
        w.writerows(out)
    print(f"wrote {OUT} rows={len(out)} anos={len({r['ano'] for r in out})}")


if __name__ == "__main__":
    main()
