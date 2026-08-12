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


def extract_xlsx_classif() -> list[dict]:
    wb = openpyxl.load_workbook(SRC, read_only=True, data_only=True)
    rows = list(wb["Planilha1"].iter_rows(values_only=True))
    wb.close()

    out: list[dict] = []
    i = 0
    while i < len(rows):
        y = is_year(rows[i][0])
        if not y or y > 2025:
            i += 1
            continue
        header_idx = None
        for j in range(i, min(i + 8, len(rows))):
            cells = [
                (str(c).casefold().strip() if c is not None else "")
                for c in rows[j][:11]
            ]
            if cells[0] in ("pos", "posição", "posicao") and any(
                c in ("times", "time", "equipes", "equipe", "clubes", "clube")
                for c in cells
            ):
                header_idx = j
                break
            if cells[0] == "time" and any(c in ("pts", "pg") for c in cells):
                header_idx = j
                break
        if header_idx is None:
            i += 1
            continue

        hdr = [
            (str(c).casefold().strip() if c is not None else "")
            for c in rows[header_idx][:12]
        ]

        def col(*names: str) -> int | None:
            for n in names:
                for k, h in enumerate(hdr):
                    if h == n:
                        return k
            return None

        c_pos = col("pos", "posição", "posicao") or 0
        c_nome = col("times", "time", "equipes", "equipe", "clubes", "clube") or 1
        c_pts = col("pts", "pg")
        c_j = col("j")
        c_v = col("v")
        c_e = col("e")
        c_d = col("d")
        c_gp = col("gp", "gf", "gm")
        c_gc = col("gc", "gs")

        block: list[dict] = []
        for j in range(header_idx + 1, min(header_idx + 80, len(rows))):
            r = rows[j]
            if is_year(r[0]):
                break
            pos = to_int(r[c_pos] if c_pos < len(r) else None)
            nome = clean_name(r[c_nome] if c_nome < len(r) else None)
            if pos is None or not nome:
                if block and all(x is None for x in r[:8]):
                    break
                continue
            if nome.isdigit() or re.match(r"^\d+$", nome):
                continue
            if pos < 1 or pos > 64:
                continue
            gp = to_int(r[c_gp]) if c_gp is not None else None
            gc = to_int(r[c_gc]) if c_gc is not None else None
            block.append(
                {
                    "competicao": "serie_c",
                    "ano": y,
                    "posicao": pos,
                    "n_clubes": 0,
                    "nome": nome,
                    "pts": to_int(r[c_pts]) if c_pts is not None else "",
                    "j": to_int(r[c_j]) if c_j is not None else "",
                    "v": to_int(r[c_v]) if c_v is not None else "",
                    "e": to_int(r[c_e]) if c_e is not None else "",
                    "d": to_int(r[c_d]) if c_d is not None else "",
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

        ok = (
            8 <= len(block) <= 40
            and len({b["posicao"] for b in block}) == len(block)
            and all(b["nome"] and not b["nome"][0].isdigit() for b in block)
        )
        with_stats = sum(1 for b in block if b["gp"] != "" and b["gc"] != "")
        if ok and with_stats >= max(4, len(block) // 2):
            n = max(b["posicao"] for b in block)
            for b in block:
                b["n_clubes"] = n
            out.extend(sorted(block, key=lambda x: x["posicao"]))
            print(f"OK {y}: {len(block)} champ={block[0]['nome']!r}")
        else:
            print(f"SKIP {y} n={len(block)} stats={with_stats}")
        i = header_idx + 1
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
        # Linha de participante: Clube ; Cidade ; UF ; …
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
    # Anexa edições listadas no CSV sem tabela final (ex.: 2026 em andamento)
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
