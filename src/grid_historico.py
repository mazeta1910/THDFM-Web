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
CLASSIF_B_CSV = ROOT_DIR / "data" / "torneios" / "classificacoes_serie_b.csv"
CLASSIF_C_CSV = ROOT_DIR / "data" / "torneios" / "classificacoes_serie_c.csv"
ARTILH_CSV = ROOT_DIR / "data" / "torneios" / "artilheiros_serie_a.csv"
GOLEADAS_CSV = ROOT_DIR / "data" / "torneios" / "goleadas_serie_a.csv"
GOLEADAS_LIGAS_CSV = ROOT_DIR / "data" / "torneios" / "goleadas_ligas.csv"
GOLEADAS_COPA_CSV = ROOT_DIR / "data" / "torneios" / "goleadas_copa_do_brasil.csv"
CAMPEOES_COPA_CSV = ROOT_DIR / "data" / "torneios" / "campeoes_copa_do_brasil.csv"

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


def _zona_rebaixamento(ano: int, n_clubes: int, *, competicao: str = "serie_a") -> int:
    """Quantos clubes na zona de rebaixamento da edição (heurística Grid)."""
    if competicao == "serie_d":
        return 0  # divisão mais baixa — sem rebaixamento
    if n_clubes < 16:
        return 0
    # B/C pontos corridos modernos: zona típica dos últimos 4
    if competicao in {"serie_b", "serie_c"}:
        return 4 if n_clubes >= 20 else (2 if n_clubes >= 16 else 0)
    if ano >= 2003:
        return 4 if n_clubes >= 20 else 2
    if ano >= 1988:
        return 4 if n_clubes >= 20 else 2
    return 0


def _carregar_goleadas_por_competicao(
    path: Path, competicao: str | None = None, *, por_edicao: bool = True
) -> tuple[set[str], set[str], set[str]]:
    """Goleadas → presente / aplicou / sofreu.

    por_edicao=True: maior diff de cada ano.
    por_edicao=False: todos os jogos do arquivo (ex.: ranking histórico da Copa).
    """
    presente: set[str] = set()
    aplicou: set[str] = set()
    sofreu: set[str] = set()
    if not path.is_file():
        return presente, aplicou, sofreu

    by_ano: dict[int, list[tuple[str, str, int]]] = defaultdict(list)
    avulsos: list[tuple[str, str, int]] = []
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f, delimiter=";"):
            if competicao and (row.get("competicao") or "") != competicao:
                continue
            ano = _to_int(row.get("ano"))
            diff = _to_int(row.get("diff"))
            if diff is None or diff <= 0:
                continue
            venc = resolver_clube_fm(row.get("vencedor") or "")
            perd = resolver_clube_fm(row.get("perdedor") or "")
            if not venc or not perd:
                continue
            if por_edicao and ano is not None:
                by_ano[ano].append((venc["id"], perd["id"], diff))
            else:
                avulsos.append((venc["id"], perd["id"], diff))

    def _add(vid: str, pid: str) -> None:
        presente.add(vid)
        presente.add(pid)
        aplicou.add(vid)
        sofreu.add(pid)

    if por_edicao:
        for _ano, lst in by_ano.items():
            mx = max(x[2] for x in lst)
            for vid, pid, diff in lst:
                if diff == mx:
                    _add(vid, pid)
    else:
        for vid, pid, _diff in avulsos:
            _add(vid, pid)
    return presente, aplicou, sofreu


def _carregar_goleadas_serie_a() -> tuple[set[str], set[str], set[str]]:
    src = GOLEADAS_LIGAS_CSV if GOLEADAS_LIGAS_CSV.is_file() else GOLEADAS_CSV
    comp = "serie_a" if src == GOLEADAS_LIGAS_CSV else None
    return _carregar_goleadas_por_competicao(src, comp, por_edicao=True)


def _agregar_classificacao(
    path: Path,
    *,
    competicao: str,
    com_stats: bool = True,
    com_rebaixamento: bool = True,
    com_paridade: bool = False,
    long_anos: tuple[int, ...] = (),
) -> dict[str, set[str]]:
    """Lê CSV de classificação e devolve sets sem prefixo de categoria."""
    out: dict[str, set[str]] = {
        "campeao": set(),
        "vice": set(),
        "g4": set(),
        "lanterna": set(),
        "particip": set(),
        "ataque": set(),
        "defesa": set(),
        "pior_defesa": set(),
        "mais_vitorias": set(),
        "mais_empates": set(),
        "mais_derrotas": set(),
        "rebaixado": set(),
        "camp_impar": set(),
        "camp_par": set(),
    }
    if not path.is_file():
        return out

    anos_por: dict[str, set[int]] = {}
    by_ano: dict[int, list[tuple[str, int, int, int, int, int, int, int]]] = {}

    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f, delimiter=";"):
            clube = resolver_clube_fm(row.get("nome") or "")
            if not clube:
                continue
            fid = clube["id"]
            ano = _to_int(row.get("ano"))
            pos = _to_int(row.get("posicao"))
            n_clubes = _to_int(row.get("n_clubes")) or 0
            gp = _to_int(row.get("gp"))
            gc = _to_int(row.get("gc"))
            v = _to_int(row.get("v"))
            e = _to_int(row.get("e"))
            d = _to_int(row.get("d"))
            if ano is None or pos is None:
                continue
            out["particip"].add(fid)
            anos_por.setdefault(fid, set()).add(ano)
            if pos == 1:
                out["campeao"].add(fid)
                if com_paridade:
                    (out["camp_impar"] if ano % 2 else out["camp_par"]).add(fid)
            if pos == 2:
                out["vice"].add(fid)
            if pos <= 4:
                out["g4"].add(fid)
            if n_clubes and pos == n_clubes:
                out["lanterna"].add(fid)
            if com_rebaixamento:
                zona = _zona_rebaixamento(ano, n_clubes, competicao=competicao)
                if zona and pos > n_clubes - zona:
                    out["rebaixado"].add(fid)
            if com_stats and gp is not None and gc is not None:
                by_ano.setdefault(ano, []).append(
                    (fid, pos, n_clubes, gp, gc, v or 0, e or 0, d or 0)
                )

    if com_stats:
        for _ano, lst in by_ano.items():
            if not lst:
                continue
            mx_gp = max(x[3] for x in lst)
            mn_gc = min(x[4] for x in lst)
            mx_gc = max(x[4] for x in lst)
            mx_v = max(x[5] for x in lst)
            mx_e = max(x[6] for x in lst)
            mx_d = max(x[7] for x in lst)
            for fid, _pos, _n, gp, gc, v, e, d in lst:
                if gp == mx_gp:
                    out["ataque"].add(fid)
                if gc == mn_gc:
                    out["defesa"].add(fid)
                if gc == mx_gc:
                    out["pior_defesa"].add(fid)
                if v == mx_v:
                    out["mais_vitorias"].add(fid)
                if e == mx_e:
                    out["mais_empates"].add(fid)
                if d == mx_d:
                    out["mais_derrotas"].add(fid)

    for n in long_anos:
        out[f"long_{n}"] = {fid for fid, ys in anos_por.items() if len(ys) >= n}
    return out


def _mapear_serie_a(agg: dict[str, set[str]]) -> dict[str, frozenset[str]]:
    return {
        "titulo:campeao_br": frozenset(agg["campeao"]),
        "titulo:vice_br": frozenset(agg["vice"]),
        "premio:g4": frozenset(agg["g4"]),
        "premio:melhor_ataque": frozenset(agg["ataque"]),
        "premio:melhor_defesa": frozenset(agg["defesa"]),
        "premio:pior_defesa": frozenset(agg["pior_defesa"]),
        "premio:lanterna": frozenset(agg["lanterna"]),
        "premio:mais_vitorias": frozenset(agg["mais_vitorias"]),
        "premio:mais_empates": frozenset(agg["mais_empates"]),
        "premio:mais_derrotas": frozenset(agg["mais_derrotas"]),
        "premio:rebaixado": frozenset(agg["rebaixado"]),
        "participacao:serie_a": frozenset(agg["particip"]),
        "longevidade:serie_a_10": frozenset(agg.get("long_10") or ()),
        "longevidade:serie_a_20": frozenset(agg.get("long_20") or ()),
        "paridade:campeao_impar": frozenset(agg["camp_impar"]),
        "paridade:campeao_par": frozenset(agg["camp_par"]),
    }


def _mapear_serie(
    agg: dict[str, set[str]],
    *,
    tag: str,
    com_stats: bool,
    com_rebaixamento: bool,
) -> dict[str, frozenset[str]]:
    out: dict[str, frozenset[str]] = {
        f"titulo:campeao_{tag}": frozenset(agg["campeao"]),
        f"titulo:vice_{tag}": frozenset(agg["vice"]),
        f"premio:g4_{tag}": frozenset(agg["g4"]),
        f"participacao:{tag}": frozenset(agg["particip"]),
    }
    if com_stats:
        out.update(
            {
                f"premio:melhor_ataque_{tag}": frozenset(agg["ataque"]),
                f"premio:melhor_defesa_{tag}": frozenset(agg["defesa"]),
                f"premio:pior_defesa_{tag}": frozenset(agg["pior_defesa"]),
                f"premio:lanterna_{tag}": frozenset(agg["lanterna"]),
                f"premio:mais_vitorias_{tag}": frozenset(agg["mais_vitorias"]),
                f"premio:mais_empates_{tag}": frozenset(agg["mais_empates"]),
                f"premio:mais_derrotas_{tag}": frozenset(agg["mais_derrotas"]),
            }
        )
    if com_rebaixamento:
        out[f"premio:rebaixado_{tag}"] = frozenset(agg["rebaixado"])
    for key, val in list(agg.items()):
        if key.startswith("long_"):
            n = key.split("_", 1)[1]
            out[f"longevidade:{tag}_{n}"] = frozenset(val)
    return out


def _carregar_copa() -> dict[str, frozenset[str]]:
    campeoes: set[str] = set()
    vices: set[str] = set()
    if CAMPEOES_COPA_CSV.is_file():
        with CAMPEOES_COPA_CSV.open(encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f, delimiter=";"):
                c = resolver_clube_fm(row.get("campeao") or "")
                v = resolver_clube_fm(row.get("vice") or "")
                if c:
                    campeoes.add(c["id"])
                if v:
                    vices.add(v["id"])
    presente, aplicou, sofreu = _carregar_goleadas_por_competicao(
        GOLEADAS_COPA_CSV, por_edicao=False
    )
    return {
        "titulo:campeao_cdb": frozenset(campeoes),
        "titulo:vice_cdb": frozenset(vices),
        "goleada:presente_cdb": frozenset(presente),
        "goleada:aplicou_cdb": frozenset(aplicou),
        "goleada:sofreu_cdb": frozenset(sofreu),
    }


@lru_cache(maxsize=1)
def historico_serie_a() -> dict[str, frozenset[str]]:
    """Mapas categoria_id → clubes FM (Série A/B/C/D + Copa do Brasil)."""
    out: dict[str, frozenset[str]] = {}

    if CLASSIF_CSV.is_file():
        agg_a = _agregar_classificacao(
            CLASSIF_CSV,
            competicao="serie_a",
            com_stats=True,
            com_rebaixamento=True,
            com_paridade=True,
            long_anos=(10, 20),
        )
        out.update(_mapear_serie_a(agg_a))

    artilheiros: set[str] = set()
    if ARTILH_CSV.is_file():
        with ARTILH_CSV.open(encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f, delimiter=";"):
                clube = resolver_clube_fm(row.get("clube") or "")
                if clube:
                    artilheiros.add(clube["id"])
    out["premio:artilheiro"] = frozenset(artilheiros)

    g_a = _carregar_goleadas_serie_a()
    out["goleada:presente"] = frozenset(g_a[0])
    out["goleada:aplicou"] = frozenset(g_a[1])
    out["goleada:sofreu"] = frozenset(g_a[2])

    # Série B — dump local só traz top 4 (Detalhes); sem tabela completa → sem stats/rebaixamento
    if CLASSIF_B_CSV.is_file():
        agg_b = _agregar_classificacao(
            CLASSIF_B_CSV,
            competicao="serie_b",
            com_stats=False,
            com_rebaixamento=False,
            long_anos=(),
        )
        out.update(
            {
                "titulo:campeao_serie_b": frozenset(agg_b["campeao"]),
                "titulo:vice_serie_b": frozenset(agg_b["vice"]),
                "premio:g4_serie_b": frozenset(agg_b["g4"]),
            }
        )
    g_b = _carregar_goleadas_por_competicao(
        GOLEADAS_LIGAS_CSV if GOLEADAS_LIGAS_CSV.is_file() else GOLEADAS_CSV,
        "serie_b",
        por_edicao=True,
    )
    out["goleada:presente_serie_b"] = frozenset(g_b[0])
    out["goleada:aplicou_serie_b"] = frozenset(g_b[1])
    out["goleada:sofreu_serie_b"] = frozenset(g_b[2])

    # Série C — classificações do xlsx/CSV local
    if CLASSIF_C_CSV.is_file():
        agg_c = _agregar_classificacao(
            CLASSIF_C_CSV,
            competicao="serie_c",
            com_stats=True,
            com_rebaixamento=True,
            long_anos=(5,),
        )
        out.update(
            _mapear_serie(
                agg_c, tag="serie_c", com_stats=True, com_rebaixamento=True
            )
        )

    # Série D: sem CSV local em data/torneios — omitido de propósito

    out.update(_carregar_copa())
    return out


def _meta_serie(tag: str, rotulo: str, *, com_stats: bool, com_rebaixamento: bool, longs: tuple[int, ...]) -> list[tuple[str, str, str, str]]:
    rows: list[tuple[str, str, str, str]] = [
        (f"titulo:campeao_{tag}", "titulo", f"campeao_{tag}", f"Já foi campeão da {rotulo}"),
        (f"titulo:vice_{tag}", "titulo", f"vice_{tag}", f"Já foi vice da {rotulo}"),
        (f"premio:g4_{tag}", "premio", f"g4_{tag}", f"Já ficou no G4 da {rotulo}"),
        (f"participacao:{tag}", "participacao", tag, f"Já disputou a {rotulo}"),
    ]
    if com_stats:
        rows.extend(
            [
                (f"premio:melhor_ataque_{tag}", "premio", f"melhor_ataque_{tag}", f"Já teve o melhor ataque da {rotulo}"),
                (f"premio:melhor_defesa_{tag}", "premio", f"melhor_defesa_{tag}", f"Já teve a melhor defesa da {rotulo}"),
                (f"premio:pior_defesa_{tag}", "premio", f"pior_defesa_{tag}", f"Já teve a pior defesa da {rotulo}"),
                (f"premio:lanterna_{tag}", "premio", f"lanterna_{tag}", f"Já foi lanterna da {rotulo}"),
                (f"premio:mais_vitorias_{tag}", "premio", f"mais_vitorias_{tag}", f"Já foi o time com mais vitórias numa edição da {rotulo}"),
                (f"premio:mais_empates_{tag}", "premio", f"mais_empates_{tag}", f"Já foi o time com mais empates numa edição da {rotulo}"),
                (f"premio:mais_derrotas_{tag}", "premio", f"mais_derrotas_{tag}", f"Já foi o time com mais derrotas numa edição da {rotulo}"),
            ]
        )
    if com_rebaixamento:
        rows.append(
            (f"premio:rebaixado_{tag}", "premio", f"rebaixado_{tag}", f"Já foi rebaixado da {rotulo}")
        )
    for n in longs:
        rows.append(
            (f"longevidade:{tag}_{n}", "longevidade", f"{tag}_{n}", f"≥{n} participações na {rotulo}")
        )
    return rows


HISTORICO_META: list[tuple[str, str, str, str]] = [
    # Série A (chaves estáveis)
    ("titulo:campeao_br", "titulo", "campeao_br", "Já foi campeão do Brasileirão"),
    ("titulo:vice_br", "titulo", "vice_br", "Já foi vice do Brasileirão"),
    ("premio:g4", "premio", "g4", "Já ficou no G4 do Brasileirão"),
    ("premio:melhor_ataque", "premio", "melhor_ataque", "Já teve o melhor ataque do Brasileirão"),
    ("premio:melhor_defesa", "premio", "melhor_defesa", "Já teve a melhor defesa do Brasileirão"),
    ("premio:pior_defesa", "premio", "pior_defesa", "Já teve a pior defesa do Brasileirão"),
    ("premio:artilheiro", "premio", "artilheiro", "Já teve artilheiro do Brasileirão"),
    ("premio:lanterna", "premio", "lanterna", "Já foi lanterna do Brasileirão"),
    ("premio:mais_vitorias", "premio", "mais_vitorias", "Já foi o time com mais vitórias numa edição da Série A"),
    ("premio:mais_empates", "premio", "mais_empates", "Já foi o time com mais empates numa edição da Série A"),
    ("premio:mais_derrotas", "premio", "mais_derrotas", "Já foi o time com mais derrotas numa edição da Série A"),
    ("premio:rebaixado", "premio", "rebaixado", "Já foi rebaixado da Série A"),
    ("goleada:presente", "goleada", "presente", "Já esteve na maior goleada de uma edição da Série A"),
    ("goleada:aplicou", "goleada", "aplicou", "Já aplicou a maior goleada de uma edição da Série A"),
    ("goleada:sofreu", "goleada", "sofreu", "Já sofreu a maior goleada de uma edição da Série A"),
    ("participacao:serie_a", "participacao", "serie_a", "Já disputou a Série A"),
    ("longevidade:serie_a_10", "longevidade", "serie_a_10", "≥10 participações na Série A"),
    ("longevidade:serie_a_20", "longevidade", "serie_a_20", "≥20 participações na Série A"),
    ("paridade:campeao_impar", "paridade", "campeao_impar", "Campeão do Brasileirão em ano ímpar"),
    ("paridade:campeao_par", "paridade", "campeao_par", "Campeão do Brasileirão em ano par"),
    # Série B (top 4 + goleadas do Goleadas.xlsx local)
    ("titulo:campeao_serie_b", "titulo", "campeao_serie_b", "Já foi campeão da Série B"),
    ("titulo:vice_serie_b", "titulo", "vice_serie_b", "Já foi vice da Série B"),
    ("premio:g4_serie_b", "premio", "g4_serie_b", "Já ficou no G4 da Série B"),
    ("goleada:presente_serie_b", "goleada", "presente_serie_b", "Já esteve na maior goleada de uma edição da Série B"),
    ("goleada:aplicou_serie_b", "goleada", "aplicou_serie_b", "Já aplicou a maior goleada de uma edição da Série B"),
    ("goleada:sofreu_serie_b", "goleada", "sofreu_serie_b", "Já sofreu a maior goleada de uma edição da Série B"),
    # Série C (classificações do xlsx local)
    *_meta_serie("serie_c", "Série C", com_stats=True, com_rebaixamento=True, longs=(5,)),
    # Copa do Brasil (títulos + goleadas históricas)
    ("titulo:campeao_cdb", "titulo", "campeao_cdb", "Já foi campeão da Copa do Brasil"),
    ("titulo:vice_cdb", "titulo", "vice_cdb", "Já foi vice da Copa do Brasil"),
    ("goleada:presente_cdb", "goleada", "presente_cdb", "Já esteve em uma das maiores goleadas da Copa do Brasil"),
    ("goleada:aplicou_cdb", "goleada", "aplicou_cdb", "Já aplicou uma das maiores goleadas da Copa do Brasil"),
    ("goleada:sofreu_cdb", "goleada", "sofreu_cdb", "Já sofreu uma das maiores goleadas da Copa do Brasil"),
]


def limpar_caches_historico() -> None:
    historico_serie_a.cache_clear()
    _indice_catalogo.cache_clear()
