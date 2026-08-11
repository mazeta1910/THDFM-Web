"""ETL de classificações/artilheiros da Série A → sets de clubes FM para o Grid."""

from __future__ import annotations

import csv
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any

from src.clubes_catalogo import carregar_clubes
from src.config import ROOT_DIR

CLASSIF_CSV = ROOT_DIR / "data" / "torneios" / "classificacoes_serie_a.csv"
ARTILH_CSV = ROOT_DIR / "data" / "torneios" / "artilheiros_serie_a.csv"

# Aliases Wikipedia → nome canônico no catálogo FM (sem UF).
_ALIAS_NOME: dict[str, str] = {
    "vasco da gama": "vasco",
    "america mineiro": "america",
    "américa mineiro": "america",
    "red bull bragantino": "rb bragantino",
    "rb bragantino": "rb bragantino",
    "bragantino": "rb bragantino",
    "atletico paranaense": "athletico paranaense",
    "atletico-pr": "athletico paranaense",
    "atletico pr": "athletico paranaense",
    "atletico goianiense": "atletico goianiense",
    "atletico mineiro": "atletico mineiro",
}

# Quando o alias aponta a um nome compartilhado, desambiguar por UF.
_ALIAS_UF: dict[str, str] = {
    "america mineiro": "MG",
    "américa mineiro": "MG",
    "america de natal": "RN",
    "américa de natal": "RN",
    "rb bragantino": "SP",
    "red bull bragantino": "SP",
    "bragantino": "SP",
}


def _strip_acc(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c))


def normalizar_nome(s: str) -> str:
    s = _strip_acc(s).casefold()
    s = re.sub(r"\([^)]*\)", " ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _to_int(raw: str | None) -> int | None:
    s = (raw or "").strip().replace("−", "-").replace("–", "-")
    if not s or s in "-—":
        return None
    m = re.search(r"-?\d+", s)
    return int(m.group()) if m else None


def _score_candidato(c: dict[str, Any]) -> int:
    nome = c.get("nome") or ""
    div = (c.get("divisao") or "").casefold()
    s = 0
    if c.get("tem_emblema"):
        s += 20
    if "série a" in div or "serie a" in div or "assaí" in div or "assai" in div:
        s += 100
    elif "série b" in div or "serie b" in div:
        s += 50
    elif "série c" in div or "serie c" in div:
        s += 25
    # Preferir nome “nu” (Flamengo) a Flamengo (SP)
    if not re.search(r"\([A-Z]{2}\)\s*$", nome):
        s += 15
    if nome.endswith(" B"):
        s -= 40
    return s


@lru_cache(maxsize=1)
def _indice_catalogo() -> dict[str, list[dict[str, Any]]]:
    by: dict[str, list[dict[str, Any]]] = {}
    for c in carregar_clubes():
        if not c.get("tem_emblema"):
            continue
        key = normalizar_nome(c.get("nome") or "")
        by.setdefault(key, []).append(c)
        # também indexa sem sufixo textual já removido por normalizar
    return by


def resolver_clube_fm(nome_wiki: str, uf_hint: str | None = None) -> dict[str, Any] | None:
    raw = nome_wiki or ""
    n = normalizar_nome(raw)
    if not n:
        return None
    uf = uf_hint or _ALIAS_UF.get(n) or _ALIAS_UF.get(raw.casefold())
    alvo = _ALIAS_NOME.get(n, n)
    by = _indice_catalogo()
    cands = list(by.get(alvo) or [])
    if not cands and alvo != n:
        cands = list(by.get(n) or [])
    if not cands:
        # contém / contido (mín. 5 chars)
        for k, vs in by.items():
            if len(alvo) >= 5 and (alvo == k or alvo in k or k in alvo):
                cands.extend(vs)
    if not cands:
        return None
    if uf:
        filtrados = [c for c in cands if (c.get("uf") or "") == uf]
        if filtrados:
            cands = filtrados
    # unique by id
    uniq = {c["id"]: c for c in cands}
    return max(uniq.values(), key=_score_candidato)


@lru_cache(maxsize=1)
def historico_serie_a() -> dict[str, frozenset[str]]:
    """
    Retorna maps categoria_id → frozenset de club ids FM.

    Chaves:
      titulo:campeao_br, titulo:vice_br, premio:g4, premio:melhor_ataque,
      premio:melhor_defesa, premio:artilheiro, premio:lanterna,
      participacao:serie_a, longevidade:serie_a_10, longevidade:serie_a_20,
      paridade:campeao_impar, paridade:campeao_par
    """
    if not CLASSIF_CSV.is_file():
        return {}

    campeoes: set[str] = set()
    vices: set[str] = set()
    g4: set[str] = set()
    lanterna: set[str] = set()
    particip: set[str] = set()
    ataque: set[str] = set()
    defesa: set[str] = set()
    camp_impar: set[str] = set()
    camp_par: set[str] = set()
    anos_por: dict[str, set[int]] = {}
    by_ano: dict[int, list[tuple[str, int, int]]] = {}

    with CLASSIF_CSV.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f, delimiter=";"):
            clube = resolver_clube_fm(row.get("nome") or "")
            if not clube:
                continue
            fid = clube["id"]
            ano = _to_int(row.get("ano"))
            pos = _to_int(row.get("posicao"))
            n_clubes = _to_int(row.get("n_clubes")) or 0
            gp = _to_int(row.get("gp")) or 0
            gc = _to_int(row.get("gc"))
            if ano is None or pos is None:
                continue
            if gc is None:
                gc = 10**9
            particip.add(fid)
            anos_por.setdefault(fid, set()).add(ano)
            if pos == 1:
                campeoes.add(fid)
                (camp_impar if ano % 2 else camp_par).add(fid)
            if pos == 2:
                vices.add(fid)
            if pos <= 4:
                g4.add(fid)
            if n_clubes and pos == n_clubes:
                lanterna.add(fid)
            by_ano.setdefault(ano, []).append((fid, gp, gc))

    for _ano, lst in by_ano.items():
        mx = max(x[1] for x in lst)
        mn = min(x[2] for x in lst)
        for fid, gp, gc in lst:
            if gp == mx:
                ataque.add(fid)
            if gc == mn:
                defesa.add(fid)

    artilheiros: set[str] = set()
    if ARTILH_CSV.is_file():
        with ARTILH_CSV.open(encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f, delimiter=";"):
                clube = resolver_clube_fm(row.get("clube") or "")
                if clube:
                    artilheiros.add(clube["id"])

    long10 = {fid for fid, ys in anos_por.items() if len(ys) >= 10}
    long20 = {fid for fid, ys in anos_por.items() if len(ys) >= 20}

    return {
        "titulo:campeao_br": frozenset(campeoes),
        "titulo:vice_br": frozenset(vices),
        "premio:g4": frozenset(g4),
        "premio:melhor_ataque": frozenset(ataque),
        "premio:melhor_defesa": frozenset(defesa),
        "premio:artilheiro": frozenset(artilheiros),
        "premio:lanterna": frozenset(lanterna),
        "participacao:serie_a": frozenset(particip),
        "longevidade:serie_a_10": frozenset(long10),
        "longevidade:serie_a_20": frozenset(long20),
        "paridade:campeao_impar": frozenset(camp_impar),
        "paridade:campeao_par": frozenset(camp_par),
    }


HISTORICO_META: list[tuple[str, str, str, str]] = [
    # id, tipo, valor, rotulo
    ("titulo:campeao_br", "titulo", "campeao_br", "Já foi campeão do Brasileirão"),
    ("titulo:vice_br", "titulo", "vice_br", "Já foi vice do Brasileirão"),
    ("premio:g4", "premio", "g4", "Já ficou no G4 do Brasileirão"),
    ("premio:melhor_ataque", "premio", "melhor_ataque", "Já teve o melhor ataque do Brasileirão"),
    ("premio:melhor_defesa", "premio", "melhor_defesa", "Já teve a melhor defesa do Brasileirão"),
    ("premio:artilheiro", "premio", "artilheiro", "Já teve artilheiro do Brasileirão"),
    ("premio:lanterna", "premio", "lanterna", "Já foi lanterna do Brasileirão"),
    ("participacao:serie_a", "participacao", "serie_a", "Já disputou a Série A"),
    ("longevidade:serie_a_10", "longevidade", "serie_a_10", "≥10 participações na Série A"),
    ("longevidade:serie_a_20", "longevidade", "serie_a_20", "≥20 participações na Série A"),
    ("paridade:campeao_impar", "paridade", "campeao_impar", "Campeão do Brasileirão em ano ímpar"),
    ("paridade:campeao_par", "paridade", "campeao_par", "Campeão do Brasileirão em ano par"),
]


def limpar_caches_historico() -> None:
    historico_serie_a.cache_clear()
    _indice_catalogo.cache_clear()
