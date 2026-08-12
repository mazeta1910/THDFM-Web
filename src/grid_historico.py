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
PARTICIP_COPA_CSV = ROOT_DIR / "data" / "torneios" / "participacoes_copa_do_brasil.csv"

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
    long_anos_le: tuple[int, ...] = (),
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
    reb_counts: dict[str, int] = {}
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
            pts = _to_int(row.get("pts"))
            j_jogos = _to_int(row.get("j"))
            gp = _to_int(row.get("gp"))
            gc = _to_int(row.get("gc"))
            v = _to_int(row.get("v"))
            e = _to_int(row.get("e"))
            d = _to_int(row.get("d"))
            if ano is None or pos is None:
                continue
            out["particip"].add(fid)
            anos_por.setdefault(fid, set()).add(ano)
            # Temporada ainda sem tabela (só lista de participantes): conta
            # participação/longevidade, mas não inventa campeão/G4/rebaixamento.
            temporada_com_resultado = (
                pts is not None
                or j_jogos is not None
                or (gp is not None and gc is not None)
            )
            if not temporada_com_resultado:
                continue
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
                    reb_counts[fid] = reb_counts.get(fid, 0) + 1
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
    for n in long_anos_le:
        # Quem tem no máximo N edições entre os que disputaram (0 entra depois,
        # ao unir com participacao:nunca_* no histórico completo).
        out[f"long_le_{n}"] = {
            fid for fid, ys in anos_por.items() if 1 <= len(ys) <= n
        }
    # Metadados internos para variantes (yo-yo, décadas, eras).
    out["_anos_por"] = anos_por  # type: ignore[assignment]
    out["_reb_counts"] = reb_counts  # type: ignore[assignment]
    return out


def _mapear_serie_a(agg: dict[str, set[str]]) -> dict[str, frozenset[str]]:
    out: dict[str, frozenset[str]] = {
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
        "paridade:campeao_impar": frozenset(agg["camp_impar"]),
        "paridade:campeao_par": frozenset(agg["camp_par"]),
    }
    for key, val in list(agg.items()):
        if key.startswith("long_le_"):
            n = key.split("_", 2)[2]
            out[f"longevidade:serie_a_le_{n}"] = frozenset(val)
        elif key.startswith("long_"):
            n = key.split("_", 1)[1]
            out[f"longevidade:serie_a_{n}"] = frozenset(val)
    return out


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
        if key.startswith("long_le_"):
            n = key.split("_", 2)[2]
            out[f"longevidade:{tag}_le_{n}"] = frozenset(val)
        elif key.startswith("long_"):
            n = key.split("_", 1)[1]
            out[f"longevidade:{tag}_{n}"] = frozenset(val)
    return out


def _carregar_participacoes_copa(
    long_anos: tuple[int, ...] = (5, 10, 15, 20, 25),
    long_anos_le: tuple[int, ...] = (3, 5, 10),
) -> dict[str, frozenset[str]]:
    """Participação / longevidade na Copa do Brasil a partir do CSV limpo."""
    out: dict[str, frozenset[str]] = {}
    if not PARTICIP_COPA_CSV.is_file():
        return out
    anos_por: dict[str, set[int]] = {}
    with PARTICIP_COPA_CSV.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f, delimiter=";"):
            clube = resolver_clube_fm(row.get("nome") or "")
            ano = _to_int(row.get("ano"))
            if not clube or ano is None:
                continue
            anos_por.setdefault(clube["id"], set()).add(ano)
    if not anos_por:
        return out
    particip = frozenset(anos_por)
    out["participacao:cdb"] = particip
    for n in long_anos:
        out[f"longevidade:cdb_{n}"] = frozenset(
            fid for fid, ys in anos_por.items() if len(ys) >= n
        )
    for n in long_anos_le:
        # 1..N entre quem disputou; 0 (nunca) é unido depois no histórico completo.
        out[f"longevidade:cdb_le_{n}"] = frozenset(
            fid for fid, ys in anos_por.items() if 1 <= len(ys) <= n
        )
    for dec in range(1990, 2030, 10):
        out[f"participacao:cdb_dec_{dec}"] = frozenset(
            fid for fid, ys in anos_por.items() if any(dec <= y < dec + 10 for y in ys)
        )
    for corte in (1995, 2000, 2010, 2016, 2020):
        out[f"participacao:cdb_antes_{corte}"] = frozenset(
            fid for fid, ys in anos_por.items() if any(y < corte for y in ys)
        )
        out[f"participacao:cdb_desde_{corte}"] = frozenset(
            fid for fid, ys in anos_por.items() if any(y >= corte for y in ys)
        )
        out[f"participacao:cdb_so_desde_{corte}"] = frozenset(
            fid for fid, ys in anos_por.items() if ys and all(y >= corte for y in ys)
        )
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
    out: dict[str, frozenset[str]] = {
        "titulo:campeao_cdb": frozenset(campeoes),
        "titulo:vice_cdb": frozenset(vices),
        "goleada:presente_cdb": frozenset(presente),
        "goleada:aplicou_cdb": frozenset(aplicou),
        "goleada:sofreu_cdb": frozenset(sofreu),
    }
    out.update(_carregar_participacoes_copa())
    return out


@lru_cache(maxsize=1)
def historico_serie_a() -> dict[str, frozenset[str]]:
    """Mapas categoria_id → clubes FM (Série A/B/C/D + Copa do Brasil)."""
    out: dict[str, frozenset[str]] = {}
    anos_a: dict[str, set[int]] = {}
    anos_b: dict[str, set[int]] = {}
    reb_a: dict[str, int] = {}

    if CLASSIF_CSV.is_file():
        agg_a = _agregar_classificacao(
            CLASSIF_CSV,
            competicao="serie_a",
            com_stats=True,
            com_rebaixamento=True,
            com_paridade=True,
            long_anos=(5, 10, 15, 20, 30),
            long_anos_le=(3, 5, 10),
        )
        anos_a = dict(agg_a.pop("_anos_por", {}) or {})  # type: ignore[arg-type]
        reb_a = dict(agg_a.pop("_reb_counts", {}) or {})  # type: ignore[arg-type]
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

    if CLASSIF_B_CSV.is_file():
        agg_b = _agregar_classificacao(
            CLASSIF_B_CSV,
            competicao="serie_b",
            com_stats=True,
            com_rebaixamento=True,
            long_anos=(3, 4, 5, 6, 8, 10),
            long_anos_le=(2, 3, 5),
        )
        anos_b = dict(agg_b.pop("_anos_por", {}) or {})  # type: ignore[arg-type]
        agg_b.pop("_reb_counts", None)
        out.update(
            _mapear_serie(agg_b, tag="serie_b", com_stats=True, com_rebaixamento=True)
        )
    g_b = _carregar_goleadas_por_competicao(
        GOLEADAS_LIGAS_CSV if GOLEADAS_LIGAS_CSV.is_file() else GOLEADAS_CSV,
        "serie_b",
        por_edicao=True,
    )
    out["goleada:presente_serie_b"] = frozenset(g_b[0])
    out["goleada:aplicou_serie_b"] = frozenset(g_b[1])
    out["goleada:sofreu_serie_b"] = frozenset(g_b[2])

    if CLASSIF_C_CSV.is_file():
        agg_c = _agregar_classificacao(
            CLASSIF_C_CSV,
            competicao="serie_c",
            com_stats=True,
            com_rebaixamento=True,
            long_anos=(3, 5, 8),
            long_anos_le=(2, 3, 5),
        )
        agg_c.pop("_anos_por", None)
        agg_c.pop("_reb_counts", None)
        out.update(
            _mapear_serie(agg_c, tag="serie_c", com_stats=True, com_rebaixamento=True)
        )

    out.update(_carregar_copa())

    camp_br = set(out.get("titulo:campeao_br") or ())
    vice_br = set(out.get("titulo:vice_br") or ())
    g4 = set(out.get("premio:g4") or ())
    camp_cdb = set(out.get("titulo:campeao_cdb") or ())
    vice_cdb = set(out.get("titulo:vice_cdb") or ())
    final_cdb = camp_cdb | vice_cdb

    out["premio:g4_sem_titulo"] = frozenset(g4 - camp_br)
    out["titulo:vice_sem_campeao"] = frozenset(vice_br - camp_br)
    out["titulo:vice_cdb_sem_campeao"] = frozenset(vice_cdb - camp_cdb)
    out["titulo:final_cdb"] = frozenset(final_cdb)
    out["titulo:campeao_cdb_sem_br"] = frozenset(camp_cdb - camp_br)
    out["titulo:campeao_br_sem_cdb"] = frozenset(camp_br - camp_cdb)

    for n in (2, 3, 4, 5):
        out[f"premio:rebaixado_{n}x"] = frozenset(
            fid for fid, q in reb_a.items() if q >= n
        )

    for dec in range(1970, 2030, 10):
        out[f"participacao:serie_a_dec_{dec}"] = frozenset(
            fid for fid, ys in anos_a.items() if any(dec <= y < dec + 10 for y in ys)
        )
        out[f"participacao:serie_b_dec_{dec}"] = frozenset(
            fid for fid, ys in anos_b.items() if any(dec <= y < dec + 10 for y in ys)
        )

    for corte in (1988, 1995, 2003, 2010, 2015, 2020):
        out[f"participacao:serie_a_antes_{corte}"] = frozenset(
            fid for fid, ys in anos_a.items() if any(y < corte for y in ys)
        )
        out[f"participacao:serie_a_desde_{corte}"] = frozenset(
            fid for fid, ys in anos_a.items() if any(y >= corte for y in ys)
        )
        out[f"participacao:serie_a_so_desde_{corte}"] = frozenset(
            fid for fid, ys in anos_a.items() if ys and all(y >= corte for y in ys)
        )

    if anos_a:
        ano_max = max(max(ys) for ys in anos_a.values())
        ano_min_janela = max(1959, ano_max - 10)
        for inicio in range(ano_min_janela, ano_max + 1):
            for fim in range(inicio, ano_max + 1):
                if fim - inicio > 7:
                    continue
                precisa = set(range(inicio, fim + 1))
                out[f"participacao:serie_a_seq_{inicio}_{fim}"] = frozenset(
                    fid for fid, ys in anos_a.items() if precisa <= ys
                )

    todos = _ids_clubes_grid()
    pares = (
        ("titulo:campeao_br", "titulo:nunca_campeao_br"),
        ("premio:artilheiro", "premio:nunca_artilheiro"),
        ("premio:melhor_defesa", "premio:nunca_melhor_defesa"),
        ("premio:rebaixado", "premio:nunca_rebaixado"),
        ("titulo:campeao_cdb", "titulo:nunca_campeao_cdb"),
        ("titulo:final_cdb", "titulo:nunca_final_cdb"),
        ("participacao:serie_a", "participacao:nunca_serie_a"),
        ("participacao:serie_b", "participacao:nunca_serie_b"),
        ("participacao:serie_c", "participacao:nunca_serie_c"),
        ("participacao:cdb", "participacao:nunca_cdb"),
    )
    for pos_id, neg_id in pares:
        pos = out.get(pos_id) or frozenset()
        out[neg_id] = frozenset(cid for cid in todos if cid not in pos)

    # ≤N participações = 0..N (inclui quem nunca disputou). Sem isso o rótulo
    # “≤5 na Série C” só pegava estreantes/poucas edições e excluía a maioria do catálogo.
    for tag in ("serie_a", "serie_b", "serie_c", "cdb"):
        nunca = out.get(f"participacao:nunca_{tag}") or frozenset()
        if not nunca:
            continue
        for key, val in list(out.items()):
            if key.startswith(f"longevidade:{tag}_le_"):
                out[key] = frozenset(val) | nunca

    return out


def _ids_clubes_grid() -> set[str]:
    """IDs FM com emblema e UF brasileira (mesmo critério do Grid)."""
    ufs_br = {
        "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS",
        "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC",
        "SP", "SE", "TO",
    }
    return {
        c["id"]
        for c in carregar_clubes()
        if c.get("tem_emblema") and (c.get("uf") or "") in ufs_br
    }


def _meta_serie(
    tag: str,
    rotulo: str,
    *,
    com_stats: bool,
    com_rebaixamento: bool,
    longs: tuple[int, ...] = (),
    longs_le: tuple[int, ...] = (),
) -> list[tuple[str, str, str, str]]:
    rows: list[tuple[str, str, str, str]] = [
        (f"titulo:campeao_{tag}", "titulo", f"campeao_{tag}", f"Já foi campeão da {rotulo}"),
        (f"titulo:vice_{tag}", "titulo", f"vice_{tag}", f"Já foi vice da {rotulo}"),
        (f"premio:g4_{tag}", "premio", f"g4_{tag}", f"Já ficou no G4 da {rotulo}"),
        (f"participacao:{tag}", "participacao", tag, f"Já disputou a {rotulo}"),
        (
            f"participacao:nunca_{tag}",
            "participacao",
            f"nunca_{tag}",
            f"Nunca jogou a {rotulo}",
        ),
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
    for n in longs_le:
        rows.append(
            (
                f"longevidade:{tag}_le_{n}",
                "longevidade",
                f"{tag}_le_{n}",
                f"≤{n} participações na {rotulo}",
            )
        )
    return rows


HISTORICO_META_BASE: list[tuple[str, str, str, str]] = [
    ("titulo:campeao_br", "titulo", "campeao_br", "Já foi campeão do Brasileirão"),
    ("titulo:vice_br", "titulo", "vice_br", "Já foi vice do Brasileirão"),
    ("premio:g4", "premio", "g4", "Já ficou no G4 do Brasileirão"),
    ("premio:g4_sem_titulo", "premio", "g4_sem_titulo", "Já foi G4 e nunca campeão do Brasileirão"),
    ("titulo:vice_sem_campeao", "titulo", "vice_sem_campeao", "Já foi vice e nunca campeão do Brasileirão"),
    ("premio:melhor_ataque", "premio", "melhor_ataque", "Já teve o melhor ataque do Brasileirão"),
    ("premio:melhor_defesa", "premio", "melhor_defesa", "Já teve a melhor defesa do Brasileirão"),
    ("premio:pior_defesa", "premio", "pior_defesa", "Já teve a pior defesa do Brasileirão"),
    ("premio:artilheiro", "premio", "artilheiro", "Já teve artilheiro do Brasileirão"),
    ("premio:lanterna", "premio", "lanterna", "Já foi lanterna do Brasileirão"),
    ("premio:mais_vitorias", "premio", "mais_vitorias", "Já foi o time com mais vitórias numa edição da Série A"),
    ("premio:mais_empates", "premio", "mais_empates", "Já foi o time com mais empates numa edição da Série A"),
    ("premio:mais_derrotas", "premio", "mais_derrotas", "Já foi o time com mais derrotas numa edição da Série A"),
    ("premio:rebaixado", "premio", "rebaixado", "Já foi rebaixado da Série A"),
    ("premio:nunca_rebaixado", "premio", "nunca_rebaixado", "Nunca foi rebaixado da Série A"),
    ("titulo:nunca_campeao_br", "titulo", "nunca_campeao_br", "Nunca foi campeão do Brasileirão"),
    ("premio:nunca_artilheiro", "premio", "nunca_artilheiro", "Nunca teve artilheiro do Brasileirão"),
    ("premio:nunca_melhor_defesa", "premio", "nunca_melhor_defesa", "Nunca foi melhor defesa do Brasileirão"),
    ("goleada:presente", "goleada", "presente", "Já esteve na maior goleada de uma edição da Série A"),
    ("goleada:aplicou", "goleada", "aplicou", "Já aplicou a maior goleada de uma edição da Série A"),
    ("goleada:sofreu", "goleada", "sofreu", "Já sofreu a maior goleada de uma edição da Série A"),
    ("participacao:serie_a", "participacao", "serie_a", "Já disputou a Série A"),
    (
        "participacao:nunca_serie_a",
        "participacao",
        "nunca_serie_a",
        "Nunca jogou a Série A",
    ),
    ("longevidade:serie_a_5", "longevidade", "serie_a_5", "≥5 participações na Série A"),
    ("longevidade:serie_a_10", "longevidade", "serie_a_10", "≥10 participações na Série A"),
    ("longevidade:serie_a_15", "longevidade", "serie_a_15", "≥15 participações na Série A"),
    ("longevidade:serie_a_20", "longevidade", "serie_a_20", "≥20 participações na Série A"),
    ("longevidade:serie_a_30", "longevidade", "serie_a_30", "≥30 participações na Série A"),
    ("longevidade:serie_a_le_3", "longevidade", "serie_a_le_3", "≤3 participações na Série A"),
    ("longevidade:serie_a_le_5", "longevidade", "serie_a_le_5", "≤5 participações na Série A"),
    ("longevidade:serie_a_le_10", "longevidade", "serie_a_le_10", "≤10 participações na Série A"),
    ("paridade:campeao_impar", "paridade", "campeao_impar", "Campeão do Brasileirão em ano ímpar"),
    ("paridade:campeao_par", "paridade", "campeao_par", "Campeão do Brasileirão em ano par"),
    *_meta_serie(
        "serie_b",
        "Série B",
        com_stats=True,
        com_rebaixamento=True,
        longs=(3, 4, 5, 6, 8, 10),
        longs_le=(2, 3, 5),
    ),
    ("goleada:presente_serie_b", "goleada", "presente_serie_b", "Já esteve na maior goleada de uma edição da Série B"),
    ("goleada:aplicou_serie_b", "goleada", "aplicou_serie_b", "Já aplicou a maior goleada de uma edição da Série B"),
    ("goleada:sofreu_serie_b", "goleada", "sofreu_serie_b", "Já sofreu a maior goleada de uma edição da Série B"),
    *_meta_serie(
        "serie_c",
        "Série C",
        com_stats=True,
        com_rebaixamento=True,
        longs=(3, 5, 8),
        longs_le=(2, 3, 5),
    ),
    ("titulo:campeao_cdb", "titulo", "campeao_cdb", "Já foi campeão da Copa do Brasil"),
    ("titulo:vice_cdb", "titulo", "vice_cdb", "Já foi vice da Copa do Brasil"),
    ("titulo:vice_cdb_sem_campeao", "titulo", "vice_cdb_sem_campeao", "Já foi vice e nunca campeão da Copa do Brasil"),
    ("titulo:final_cdb", "titulo", "final_cdb", "Já foi à final da Copa do Brasil"),
    ("titulo:nunca_campeao_cdb", "titulo", "nunca_campeao_cdb", "Nunca ganhou a Copa do Brasil"),
    ("titulo:nunca_final_cdb", "titulo", "nunca_final_cdb", "Nunca foi à final da Copa do Brasil"),
    ("titulo:campeao_cdb_sem_br", "titulo", "campeao_cdb_sem_br", "Campeão da Copa e nunca do Brasileirão"),
    ("titulo:campeao_br_sem_cdb", "titulo", "campeao_br_sem_cdb", "Campeão do Brasileirão e nunca da Copa"),
    ("goleada:presente_cdb", "goleada", "presente_cdb", "Já esteve em uma das maiores goleadas da Copa do Brasil"),
    ("goleada:aplicou_cdb", "goleada", "aplicou_cdb", "Já aplicou uma das maiores goleadas da Copa do Brasil"),
    ("goleada:sofreu_cdb", "goleada", "sofreu_cdb", "Já sofreu uma das maiores goleadas da Copa do Brasil"),
    ("participacao:cdb", "participacao", "cdb", "Já disputou a Copa do Brasil"),
    ("participacao:nunca_cdb", "participacao", "nunca_cdb", "Nunca jogou a Copa do Brasil"),
    ("longevidade:cdb_5", "longevidade", "cdb_5", "≥5 participações na Copa do Brasil"),
    ("longevidade:cdb_10", "longevidade", "cdb_10", "≥10 participações na Copa do Brasil"),
    ("longevidade:cdb_15", "longevidade", "cdb_15", "≥15 participações na Copa do Brasil"),
    ("longevidade:cdb_20", "longevidade", "cdb_20", "≥20 participações na Copa do Brasil"),
    ("longevidade:cdb_25", "longevidade", "cdb_25", "≥25 participações na Copa do Brasil"),
    ("longevidade:cdb_le_3", "longevidade", "cdb_le_3", "≤3 participações na Copa do Brasil"),
    ("longevidade:cdb_le_5", "longevidade", "cdb_le_5", "≤5 participações na Copa do Brasil"),
    ("longevidade:cdb_le_10", "longevidade", "cdb_le_10", "≤10 participações na Copa do Brasil"),
]


def _meta_dinamico(hist: dict[str, frozenset[str]]) -> list[tuple[str, str, str, str]]:
    """Variantes com limiares/datas — só entram se o set existir e for denso o bastante."""
    rows: list[tuple[str, str, str, str]] = []
    for n in (2, 3, 4, 5):
        cid = f"premio:rebaixado_{n}x"
        if len(hist.get(cid) or ()) >= 4:
            rows.append((cid, "premio", f"rebaixado_{n}x", f"≥{n} rebaixamentos da Série A"))
    for dec in range(1970, 2030, 10):
        for tag, rot in (("serie_a", "Série A"), ("serie_b", "Série B"), ("cdb", "Copa do Brasil")):
            cid = f"participacao:{tag}_dec_{dec}"
            if len(hist.get(cid) or ()) >= 4:
                # 1990 → "anos 90"; 2000 → "anos 2000"
                label = f"anos {str(dec)[2:]}" if dec < 2000 else f"anos {dec}"
                rows.append(
                    (cid, "participacao", f"{tag}_dec_{dec}", f"Disputou a {rot} nos {label}")
                )
    for corte in (1988, 1995, 2003, 2010, 2015, 2020):
        specs = (
            (f"participacao:serie_a_antes_{corte}", f"Jogou a Série A antes de {corte}"),
            (f"participacao:serie_a_desde_{corte}", f"Jogou a Série A em {corte} ou depois"),
            (f"participacao:serie_a_so_desde_{corte}", f"Só jogou a Série A a partir de {corte}"),
        )
        for cid, rotulo in specs:
            if len(hist.get(cid) or ()) >= 4:
                rows.append((cid, "participacao", cid.split(":", 1)[1], rotulo))
    for corte in (1995, 2000, 2010, 2016, 2020):
        specs = (
            (f"participacao:cdb_antes_{corte}", f"Jogou a Copa do Brasil antes de {corte}"),
            (f"participacao:cdb_desde_{corte}", f"Jogou a Copa do Brasil em {corte} ou depois"),
            (f"participacao:cdb_so_desde_{corte}", f"Só jogou a Copa do Brasil a partir de {corte}"),
        )
        for cid, rotulo in specs:
            if len(hist.get(cid) or ()) >= 4:
                rows.append((cid, "participacao", cid.split(":", 1)[1], rotulo))
    for cid, membros in hist.items():
        if not cid.startswith("participacao:serie_a_seq_"):
            continue
        if len(membros) < 4:
            continue
        _, resto = cid.split(":", 1)
        # serie_a_seq_2020_2022 → anos nos dois últimos tokens (não em parts[2]="seq")
        parts = resto.split("_")
        if len(parts) < 4:
            continue
        inicio, fim = parts[-2], parts[-1]
        if not (inicio.isdigit() and fim.isdigit()):
            continue
        if inicio == fim:
            rotulo = f"Jogou a Série A em {inicio}"
        else:
            rotulo = f"Jogou a Série A em todos os anos de {inicio} a {fim}"
        rows.append((cid, "participacao", resto, rotulo))
    return rows


@lru_cache(maxsize=1)
def historico_meta() -> tuple[tuple[str, str, str, str], ...]:
    """META base + variantes dinâmicas densas."""
    hist = historico_serie_a()
    return tuple(HISTORICO_META_BASE + _meta_dinamico(hist))


# Compat: testes/código legado que iteram HISTORICO_META.
HISTORICO_META = HISTORICO_META_BASE


def limpar_caches_historico() -> None:
    historico_serie_a.cache_clear()
    historico_meta.cache_clear()
    _indice_catalogo.cache_clear()
