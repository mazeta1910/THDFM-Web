#!/usr/bin/env python3
"""Scrape Série A final standings (2003–2025) and all-time artilheiros from pt.wikipedia."""

from __future__ import annotations

import csv
import html as htmllib
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

UA = "THDFM-GridBot/1.0 (THDFM Grid historical data; https://github.com/mazeta1910)"
API = "https://pt.wikipedia.org/w/api.php"
ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "torneios"
PAUSE_S = 0.6

YEAR_PAGES = {
    y: f"Campeonato Brasileiro de Futebol de {y}" for y in range(2003, 2026)
}


def api_get(params: dict) -> dict:
    q = urllib.parse.urlencode({**params, "format": "json"})
    req = urllib.request.Request(API + "?" + q, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.load(r)


def api_parse_html(title: str) -> str:
    data = api_get({"action": "parse", "page": title, "prop": "text", "redirects": 1})
    if "error" in data:
        raise RuntimeError(f"{title}: {data['error']}")
    return data["parse"]["text"]["*"]


def clean(s: str) -> str:
    s = htmllib.unescape(s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"\[[^\]]*\]", "", s)
    s = s.replace("\xa0", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def strip_club_noise(name: str) -> str:
    name = re.sub(r"\s*\([^)]*\)\s*", " ", name)
    name = re.sub(r"[§†#]+", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    # drop trailing (C) already removed via parens; also " (C)" variants
    name = re.sub(r"\s+$", "", name)
    return name


def table_rows(html_table: str) -> list[list[str]]:
    rows_raw = re.findall(r"<tr[^>]*>(.*?)</tr>", html_table, re.S | re.I)
    out: list[list[str]] = []
    for r in rows_raw:
        cells = [clean(c) for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", r, re.S | re.I)]
        if cells:
            out.append(cells)
    return out


def find_standings_table(page_html: str) -> list[list[str]] | None:
    """Pick the main final league table: Pos + Equipe/Time + Pts + ~20 rows."""
    candidates: list[tuple[int, list[list[str]]]] = []
    for m in re.finditer(r"<table[^>]*>(.*?)</table>", page_html, re.S | re.I):
        rows = table_rows(m.group(0))
        if len(rows) < 10:
            continue
        head = " ".join(rows[0]).lower()
        # skip style-noise headers by also checking row1
        head2 = " ".join(rows[1]).lower() if len(rows) > 1 else ""
        blob = head + " " + head2
        # Pts / PG / bare "P" (common on older PT wiki tables)
        if not (
            re.search(r"\bpts\b|\bpg\b", blob)
            or re.search(r"(^|[\s|/])p([\s|/]|$)", " ".join(rows[0]).lower())
            or any(c.strip().lower() in ("p", "pts", "pg") for c in rows[0])
        ):
            continue
        if not re.search(r"pos|equipe|time|clube|classif", blob):
            continue
        # prefer tables with GP/GC or SG
        score = len(rows)
        if re.search(r"\bgp\b|\bgf\b|gols pró|gols pro|\bgm\b", blob):
            score += 50
        if re.search(r"\bgc\b|\bga\b|gols contra|\bgs\b", blob):
            score += 20
        # data rows looking like rank numbers
        n_ranked = sum(
            1 for r in rows[1:] if r and re.fullmatch(r"\d{1,2}", r[0].rstrip("."))
        )
        score += n_ranked
        if n_ranked >= 16:
            candidates.append((score, rows))
    if not candidates:
        return None
    candidates.sort(key=lambda x: -x[0])
    return candidates[0][1]


def map_standings_columns(header: list[str]) -> dict[str, int]:
    idxs: dict[str, int] = {}
    for i, h in enumerate(header):
        # strip embedded CSS / mediawiki style noise, keep trailing label
        hl = re.sub(r"\.mw-parser-output\b.*?\{.*?\}", " ", h, flags=re.S)
        hl = re.sub(r"\{[^}]*\}", " ", hl)
        hl = re.sub(r"@media[^{]*\{.*?\}", " ", hl, flags=re.S)
        hl = re.sub(r"\s+", " ", hl).strip().lower()
        # if still huge, keep last token-ish words
        if len(hl) > 40:
            m = re.search(r"(pos\.?|equipes?|times?|clubes?|pts|pg|p|j|v|e|d|gp|gc|sg|gm|gs)\s*$", hl)
            if m:
                hl = m.group(1)
        if "pos" not in idxs and (hl.startswith("pos") or hl in ("pos", "pos.")):
            idxs["pos"] = i
        elif "nome" not in idxs and re.search(r"equipe|time|clube", hl):
            idxs["nome"] = i
        elif "pts" not in idxs and (hl in ("pts", "pg", "p") or hl.startswith("pts")):
            idxs["pts"] = i
        elif "j" not in idxs and hl in ("j", "jogos", "partidas", "pld"):
            idxs["j"] = i
        elif "v" not in idxs and hl in ("v", "vitórias", "vitorias", "w"):
            idxs["v"] = i
        elif "e" not in idxs and hl in ("e", "empates"):
            idxs["e"] = i
        elif "d" not in idxs and hl in ("d", "derrotas", "l"):
            idxs["d"] = i
        elif "gp" not in idxs and hl in ("gp", "gf", "gols pró", "gols pro", "gm"):
            idxs["gp"] = i
        elif "gc" not in idxs and hl in ("gc", "ga", "gols contra", "gs"):
            idxs["gc"] = i
        elif "sg" not in idxs and (hl in ("sg", "gd") or hl.startswith("saldo")):
            idxs["sg"] = i
    if "pos" not in idxs:
        idxs["pos"] = 0
    if "nome" not in idxs and len(header) > 1:
        idxs["nome"] = 1
    if "v" not in idxs and "pts" in idxs and "j" in idxs:
        j = idxs["j"]
        if j + 3 < len(header):
            idxs.setdefault("v", j + 1)
            idxs.setdefault("e", j + 2)
            idxs.setdefault("d", j + 3)
    return idxs


def parse_standings(rows: list[list[str]], ano: int, fonte: str) -> list[dict]:
    # Find header row: first with Pts/P
    header_i = 0
    for i, r in enumerate(rows[:3]):
        joined = " ".join(r)
        if re.search(r"\bPts\b|\bPG\b", joined, re.I) or any(
            c.strip().lower() in ("p", "pts", "pg") for c in r
        ):
            header_i = i
            break
    header = rows[header_i]
    col = map_standings_columns(header)
    out: list[dict] = []
    for r in rows[header_i + 1 :]:
        if not r:
            continue
        pos_s = r[col["pos"]] if col["pos"] < len(r) else ""
        pos_s = pos_s.rstrip(".")
        if not re.fullmatch(r"\d{1,2}", pos_s):
            continue
        nome_raw = r[col["nome"]] if col["nome"] < len(r) else ""
        nome = strip_club_noise(nome_raw)
        if not nome or len(nome) < 2:
            continue

        def cell(key: str) -> str:
            i = col.get(key)
            if i is None or i >= len(r):
                return ""
            return re.sub(r"[^\d+\-]", "", r[i].replace("−", "-").replace("–", "-"))

        out.append(
            {
                "competicao": "serie_a",
                "ano": ano,
                "posicao": int(pos_s),
                "n_clubes": 0,
                "nome": nome,
                "pts": cell("pts"),
                "j": cell("j"),
                "v": cell("v"),
                "e": cell("e"),
                "d": cell("d"),
                "gp": cell("gp"),
                "gc": cell("gc"),
                "sg": cell("sg"),
                "fonte_url": fonte,
            }
        )
    n = len(out)
    for row in out:
        row["n_clubes"] = n
    return out


def scrape_year_standings(ano: int) -> list[dict]:
    title = YEAR_PAGES[ano]
    url = "https://pt.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_"))
    html = api_parse_html(title)
    table = find_standings_table(html)
    if not table:
        raise RuntimeError(f"Nenhuma tabela de classificação encontrada em {title}")
    return parse_standings(table, ano, url)


def expand_table_grid(table) -> list[list[str]]:
    """Expand BeautifulSoup table rowspan/colspan into a rectangular grid."""
    grid: list[list[str]] = []
    pending: dict[int, tuple[str, int]] = {}
    for tr in table.find_all("tr"):
        cells = tr.find_all(["td", "th"])
        row: list[str] = []
        col = 0
        cell_i = 0
        while cell_i < len(cells) or any(
            c >= col and pending.get(c, ("", 0))[1] > 0 for c in list(pending)
        ):
            if pending.get(col, ("", 0))[1] > 0:
                text, left = pending[col]
                row.append(text)
                pending[col] = (text, left - 1)
                if pending[col][1] == 0:
                    del pending[col]
                col += 1
                continue
            if cell_i >= len(cells):
                break
            cell = cells[cell_i]
            cell_i += 1
            text = clean(cell.get_text())
            rs = int(cell.get("rowspan", 1) or 1)
            cs = int(cell.get("colspan", 1) or 1)
            for dc in range(cs):
                row.append(text if dc == 0 else "")
                if rs > 1 and dc == 0:
                    pending[col + dc] = (text, rs - 1)
            col += cs
        if row:
            grid.append(row)
    return grid


def keep_top_scorers(rows: list[dict]) -> list[dict]:
    """Per year keep only players tied for the season max goals; dedupe jogador+clube."""
    from collections import defaultdict

    by_ano: dict[int, list[dict]] = defaultdict(list)
    for r in rows:
        by_ano[int(r["ano"])].append(r)
    out: list[dict] = []
    for ano in sorted(by_ano):
        rs = by_ano[ano]
        mx = max(int(r["gols"]) for r in rs)
        seen: set[tuple[str, str]] = set()
        for r in rs:
            if int(r["gols"]) != mx:
                continue
            key = (r["jogador"], r["clube"])
            if key in seen:
                continue
            seen.add(key)
            out.append(r)
    return out


def scrape_artilheiros_from_list() -> list[dict]:
    from bs4 import BeautifulSoup

    title = "Lista de artilheiros do Campeonato Brasileiro de Futebol"
    url = "https://pt.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_"))
    html = api_parse_html(title)
    soup = BeautifulSoup(html, "html.parser")

    target = None
    for table in soup.find_all("table", class_=re.compile(r"wikitable")):
        headers = [clean(th.get_text()) for th in table.find_all("th")]
        head_l = " ".join(headers).lower()
        if "edição" in head_l and "jogador" in head_l and "gols" in head_l and "clube" in head_l:
            target = table
            break
    if target is None:
        raise RuntimeError("Tabela de artilheiros por edição não encontrada")

    grid = expand_table_grid(target)
    if not grid:
        raise RuntimeError("Grid de artilheiros vazio")

    header = [h.lower() for h in grid[0]]

    def idx(*opts: str) -> int | None:
        for o in opts:
            for i, h in enumerate(header):
                if o in h:
                    return i
        return None

    i_ano = idx("edição", "edicao", "ano")
    i_jog = idx("jogador")
    i_nac = idx("nacionalidade")
    i_clube = idx("clube")
    i_gols = idx("gols")
    i_jogos = idx("jogos")
    if None in (i_ano, i_jog, i_clube, i_gols):
        raise RuntimeError(f"Colunas não mapeadas: {header}")

    out: list[dict] = []
    for r in grid[1:]:
        while len(r) < len(header):
            r.append("")
        ano_raw = r[i_ano].strip()
        m_ano = re.match(r"^(\d{4})", ano_raw) or re.search(r"(\d{4})", ano_raw)
        if not m_ano:
            continue
        jogador = strip_club_noise(r[i_jog])
        jogador = re.sub(r"\s*\(\d+\)#?\s*$", "", jogador).strip().rstrip("#").strip()
        clube = strip_club_noise(r[i_clube])
        gols_s = re.sub(r"[^\d]", "", r[i_gols])
        jogos_s = re.sub(r"[^\d]", "", r[i_jogos]) if i_jogos is not None else ""
        nac = r[i_nac] if i_nac is not None else ""
        if not jogador or not gols_s or re.fullmatch(r"\d+", jogador):
            continue
        out.append(
            {
                "competicao": "serie_a",
                "ano": int(m_ano.group(1)),
                "jogador": jogador,
                "clube": clube,
                "gols": int(gols_s),
                "jogos": int(jogos_s) if jogos_s else "",
                "nacionalidade": nac,
                "fonte_url": url,
            }
        )
    return keep_top_scorers(out)


def scrape_artilheiros_year(ano: int) -> list[dict]:
    """Artilheiros da página anual (corrige erros da lista agregada, ex. 2016)."""
    from bs4 import BeautifulSoup

    title = YEAR_PAGES[ano]
    url = "https://pt.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_"))
    html = api_parse_html(title)
    soup = BeautifulSoup(html, "html.parser")

    candidates: list[tuple[int, list[list[str]]]] = []
    for table in soup.find_all("table", class_=re.compile(r"wikitable")):
        grid = expand_table_grid(table)
        if len(grid) < 2 or len(grid) > 25:
            continue
        head = " ".join(grid[0]).lower()
        if not re.search(r"gol", head):
            continue
        if not re.search(r"jogador|artilh", head):
            continue
        if not re.search(r"time|clube|equipe", head):
            continue
        # skip "mais gols em uma partida" style
        if re.search(r"adversário|placar|data", head):
            continue
        score = 0
        # prefer tables under/near Artilharia: first column mostly goal counts
        gols_like = 0
        for r in grid[1:]:
            if r and re.fullmatch(r"\d{1,2}", re.sub(r"[^\d]", "", r[0]) or ""):
                gols_like += 1
        score += gols_like * 10
        if "artilh" in head:
            score += 50
        if gols_like >= 1:
            candidates.append((score, grid))

    if not candidates:
        return []
    candidates.sort(key=lambda x: -x[0])
    grid = candidates[0][1]
    header = [h.lower() for h in grid[0]]

    def idx(*opts: str) -> int | None:
        for o in opts:
            for i, h in enumerate(header):
                if o in h:
                    return i
        return None

    i_gols = idx("gol")
    i_jog = idx("jogador")
    i_clube = idx("time", "clube", "equipe")
    if None in (i_gols, i_jog, i_clube):
        return []

    rows: list[dict] = []
    for r in grid[1:]:
        while len(r) < len(header):
            r.append("")
        gols_s = re.sub(r"[^\d]", "", r[i_gols])
        jogador = strip_club_noise(r[i_jog])
        jogador = re.sub(r"\s*\(\d+\)#?\s*$", "", jogador).strip().rstrip("#").strip()
        clube = strip_club_noise(r[i_clube])
        if not jogador or not gols_s or re.fullmatch(r"\d+", jogador):
            continue
        rows.append(
            {
                "competicao": "serie_a",
                "ano": ano,
                "jogador": jogador,
                "clube": clube,
                "gols": int(gols_s),
                "jogos": "",
                "nacionalidade": "",
                "fonte_url": url,
            }
        )
    return keep_top_scorers(rows)


def scrape_artilheiros() -> list[dict]:
    """Lista histórica + override 2003–2025 pelas páginas anuais (mais confiáveis)."""
    from_list = scrape_artilheiros_from_list()
    by_ano: dict[int, list[dict]] = {}
    for r in from_list:
        by_ano.setdefault(int(r["ano"]), []).append(r)

    for ano in sorted(YEAR_PAGES):
        try:
            year_rows = scrape_artilheiros_year(ano)
        except Exception as e:
            print(f"WARN artilheiros {ano}: {e}")
            year_rows = []
        if year_rows:
            by_ano[ano] = year_rows
            nomes = ", ".join(f"{r['jogador']} ({r['clube']}) {r['gols']}" for r in year_rows)
            print(f"Artilheiros {ano}: {nomes}")
        else:
            print(f"Artilheiros {ano}: mantido da lista agregada")
        time.sleep(PAUSE_S)

    out: list[dict] = []
    for ano in sorted(by_ano):
        out.extend(by_ano[ano])
    return out


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";")
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fieldnames})


def main() -> None:
    classif: list[dict] = []
    errors: list[str] = []
    for ano in sorted(YEAR_PAGES):
        try:
            rows = scrape_year_standings(ano)
            print(f"OK {ano}: {len(rows)} clubes — 1º={rows[0]['nome'] if rows else '?'}")
            if len(rows) < 16:
                errors.append(f"{ano}: só {len(rows)} linhas")
            classif.extend(rows)
        except Exception as e:
            errors.append(f"{ano}: {e}")
            print(f"FAIL {ano}: {e}")
        time.sleep(PAUSE_S)

    art = scrape_artilheiros()
    print(f"Artilheiros: {len(art)} linhas ({art[0]['ano']}–{art[-1]['ano']})")

    write_csv(
        OUT_DIR / "classificacoes_serie_a.csv",
        classif,
        [
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
        ],
    )
    write_csv(
        OUT_DIR / "artilheiros_serie_a.csv",
        art,
        [
            "competicao",
            "ano",
            "jogador",
            "clube",
            "gols",
            "jogos",
            "nacionalidade",
            "fonte_url",
        ],
    )
    readme = OUT_DIR / "LEIA-ME_serie_a_wiki.md"
    readme.write_text(
        f"""# Série A — classificações e artilheiros (Wikipedia)

Gerado por `scripts/scrape_serie_a_wiki.py` via API da pt.wikipedia.

## Arquivos

- `classificacoes_serie_a.csv` — tabelas finais **2003–2025** (pontos corridos), UTF-8 BOM, `;`
- `artilheiros_serie_a.csv` — artilheiros por edição (1937–2025), UTF-8 BOM, `;`

## Notas

- Classificações: era pontos corridos; anos pré-2003 não inclusos neste scrape.
- Artilheiros: base na lista agregada da Wikipedia; **2003–2025** sobrescritos pelas páginas anuais (a lista agregada tem erros pontuais, ex. 2016).
- Empates de artilharia: uma linha por jogador empatado no máximo de gols da edição.
- Nomes podem precisar de aliases no join FM (`Atlético-MG` vs `Atlético Mineiro`, etc.).
- Dependência: `beautifulsoup4` (rowspan nas tabelas).
- Erros do scrape de classificação: {errors or "nenhum"}
""",
        encoding="utf-8",
    )
    print("Wrote CSVs to", OUT_DIR)
    if errors:
        print("WARNINGS:", *errors, sep="\n  ")


if __name__ == "__main__":
    main()
