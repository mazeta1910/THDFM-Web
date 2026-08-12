"""ETL de classificações/artilheiros/goleadas da Série A → sets de clubes FM para o Grid."""

from __future__ import annotations

import csv
import re
import unicodedata
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Any

from src.clubes_catalogo import carregar_clubes
from src.config import ROOT_DIR

CLASSIF_CSV = ROOT_DIR / "data" / "torneios" / "classificacoes_serie_a.csv"
ARTILH_CSV = ROOT_DIR / "data" / "torneios" / "artilheiros_serie_a.csv"
GOLEADAS_CSV = ROOT_DIR / "data" / "torneios" / "goleadas_serie_a.csv"

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
    "athletico pr": "athletico paranaense",
    "athletico-pr": "athletico paranaense",
    "atletico goianiense": "atletico goianiense",
    "atletico mineiro": "atletico mineiro",
    "atletico mg": "atletico mineiro",
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
    "atletico mineiro": "MG",
    "atletico mg": "MG",
    "athletico paranaense": "PR",
    "athletico-pr": "PR",
    "athletico pr": "PR",
    "atletico paranaense": "PR",
    "atletico-pr": "PR",
    "atletico pr": "PR",
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


def _zona_rebaixamento(ano: int, n_clubes: int) -> int:
    """Quantos clubes na zona de rebaixamento da edição (heurística Grid).

    Pontos corridos modernos (2003+): últimos 4.
    1988–2002 com ≥20 clubes: últimos 4; com 16–19: últimos 2.
    Edições anteriores (mata-mata / Taça Brasil): sem rebaixamento formal.
    """
    if n_clubes < 16:
        return 0
    if ano >= 2003:
        return 4 if n_clubes >= 20 else 2
    if ano >= 1988:
        return 4 if n_clubes >= 20 else 2
    return 0


def _carregar_goleadas_serie_a() -> tuple[set[str], set[str], set[str]]:
    """Maior goleada por edição → presente / aplicou / sofreu."""
    presente: set[str] = set()
    aplicou: set[str] = set()
    sofreu: set[str] = set()
    if not GOLEADAS_CSV.is_file():
        return presente, aplicou, sofreu

    by_ano: dict[int, list[tuple[str, str, int]]] = defaultdict(list)
    with GOLEADAS_CSV.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f, delimiter=";"):
            ano = _to_int(row.get("ano"))
            diff = _to_int(row.get("diff"))
            if ano is None or diff is None or diff <= 0:
                continue
            venc = resolver_clube_fm(row.get("vencedor") or "")
            perd = resolver_clube_fm(row.get("perdedor") or "")
            if not venc or not perd:
                continue
            by_ano[ano].append((venc["id"], perd["id"], diff))

    for _ano, lst in by_ano.items():
        mx = max(x[2] for x in lst)
        for vid, pid, diff in lst:
            if diff != mx:
                continue
            presente.add(vid)
            presente.add(pid)
            aplicou.add(vid)
            sofreu.add(pid)
    return presente, aplicou, sofreu


@lru_cache(maxsize=1)
def historico_serie_a() -> dict[str, frozenset[str]]:
    """
    Retorna maps categoria_id → frozenset de club ids FM.

    Chaves:
      titulo:campeao_br, titulo:vice_br, premio:g4, premio:melhor_ataque,
      premio:melhor_defesa, premio:pior_defesa, premio:artilheiro, premio:lanterna,
      premio:mais_vitorias, premio:mais_empates, premio:mais_derrotas,
      premio:rebaixado, goleada:presente, goleada:aplicou, goleada:sofreu,
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
    pior_defesa: set[str] = set()
    mais_vitorias: set[str] = set()
    mais_empates: set[str] = set()
    mais_derrotas: set[str] = set()
    rebaixados: set[str] = set()
    camp_impar: set[str] = set()
    camp_par: set[str] = set()
    anos_por: dict[str, set[int]] = {}
    by_ano: dict[int, list[tuple[str, int, int, int, int, int, int, int]]] = {}
    # fid, pos, n_clubes, gp, gc, v, e, d

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
            v = _to_int(row.get("v")) or 0
            e = _to_int(row.get("e")) or 0
            d = _to_int(row.get("d")) or 0
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
            zona = _zona_rebaixamento(ano, n_clubes)
            if zona and pos > n_clubes - zona:
                rebaixados.add(fid)
            by_ano.setdefault(ano, []).append((fid, pos, n_clubes, gp, gc, v, e, d))

    for _ano, lst in by_ano.items():
        mx_gp = max(x[3] for x in lst)
        mn_gc = min(x[4] for x in lst)
        mx_gc = max(x[4] for x in lst)
        mx_v = max(x[5] for x in lst)
        mx_e = max(x[6] for x in lst)
        mx_d = max(x[7] for x in lst)
        for fid, _pos, _n, gp, gc, v, e, d in lst:
            if gp == mx_gp:
                ataque.add(fid)
            if gc == mn_gc:
                defesa.add(fid)
            if gc == mx_gc and gc < 10**9:
                pior_defesa.add(fid)
            if v == mx_v:
                mais_vitorias.add(fid)
            if e == mx_e:
                mais_empates.add(fid)
            if d == mx_d:
                mais_derrotas.add(fid)

    artilheiros: set[str] = set()
    if ARTILH_CSV.is_file():
        with ARTILH_CSV.open(encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f, delimiter=";"):
                clube = resolver_clube_fm(row.get("clube") or "")
                if clube:
                    artilheiros.add(clube["id"])

    goleada_presente, goleada_aplicou, goleada_sofreu = _carregar_goleadas_serie_a()

    long10 = {fid for fid, ys in anos_por.items() if len(ys) >= 10}
    long20 = {fid for fid, ys in anos_por.items() if len(ys) >= 20}

    return {
        "titulo:campeao_br": frozenset(campeoes),
        "titulo:vice_br": frozenset(vices),
        "premio:g4": frozenset(g4),
        "premio:melhor_ataque": frozenset(ataque),
        "premio:melhor_defesa": frozenset(defesa),
        "premio:pior_defesa": frozenset(pior_defesa),
        "premio:artilheiro": frozenset(artilheiros),
        "premio:lanterna": frozenset(lanterna),
        "premio:mais_vitorias": frozenset(mais_vitorias),
        "premio:mais_empates": frozenset(mais_empates),
        "premio:mais_derrotas": frozenset(mais_derrotas),
        "premio:rebaixado": frozenset(rebaixados),
        "goleada:presente": frozenset(goleada_presente),
        "goleada:aplicou": frozenset(goleada_aplicou),
        "goleada:sofreu": frozenset(goleada_sofreu),
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
    ("premio:pior_defesa", "premio", "pior_defesa", "Já teve a pior defesa do Brasileirão"),
    ("premio:artilheiro", "premio", "artilheiro", "Já teve artilheiro do Brasileirão"),
    ("premio:lanterna", "premio", "lanterna", "Já foi lanterna do Brasileirão"),
    ("premio:mais_vitorias", "premio", "mais_vitorias", "Já foi o time com mais vitórias numa edição"),
    ("premio:mais_empates", "premio", "mais_empates", "Já foi o time com mais empates numa edição"),
    ("premio:mais_derrotas", "premio", "mais_derrotas", "Já foi o time com mais derrotas numa edição"),
    ("premio:rebaixado", "premio", "rebaixado", "Já foi rebaixado da Série A"),
    ("goleada:presente", "goleada", "presente", "Já esteve na maior goleada de uma edição"),
    ("goleada:aplicou", "goleada", "aplicou", "Já aplicou a maior goleada de uma edição"),
    ("goleada:sofreu", "goleada", "sofreu", "Já sofreu a maior goleada de uma edição"),
    ("participacao:serie_a", "participacao", "serie_a", "Já disputou a Série A"),
    ("longevidade:serie_a_10", "longevidade", "serie_a_10", "≥10 participações na Série A"),
    ("longevidade:serie_a_20", "longevidade", "serie_a_20", "≥20 participações na Série A"),
    ("paridade:campeao_impar", "paridade", "campeao_impar", "Campeão do Brasileirão em ano ímpar"),
    ("paridade:campeao_par", "paridade", "campeao_par", "Campeão do Brasileirão em ano par"),
]


def limpar_caches_historico() -> None:
    historico_serie_a.cache_clear()
    _indice_catalogo.cache_clear()
