"""THDFM Grid — puzzle diário 3×3 de clubes BR (estilo Hoops Grid)."""

from __future__ import annotations

import hashlib
import json
import math
import random
import re
from dataclasses import dataclass
from datetime import date, datetime
from functools import lru_cache
from typing import Any
from zoneinfo import ZoneInfo

from src.clubes_catalogo import carregar_clubes

TZ_SP = ZoneInfo("America/Sao_Paulo")
GRID_SIZE = 3
DENSIDADE_MIN = 4
BUSCA_LIMITE = 12
BUSCA_MIN_CHARS = 3
# Só sugere clube depois de digitar ~70% do nome (sem sufixo de UF).
SUGESTAO_FRACAO = 0.70
_UF_SUFFIX_RE = re.compile(r"\s*\([a-z]{2}\)\s*$", re.I)

REGIOES: dict[str, set[str]] = {
    "Norte": {"AC", "AP", "AM", "PA", "RO", "RR", "TO"},
    "Nordeste": {"AL", "BA", "CE", "MA", "PB", "PE", "PI", "RN", "SE"},
    "Centro-Oeste": {"DF", "GO", "MT", "MS"},
    "Sudeste": {"ES", "MG", "RJ", "SP"},
    "Sul": {"PR", "RS", "SC"},
}
UF_PARA_REGIAO = {uf: reg for reg, ufs in REGIOES.items() for uf in ufs}

_SERIE_A_MARKERS = ("assaí", "assai", "série a", "serie a")
_SERIE_B_MARKERS = ("série b", "serie b")
_SERIE_C_MARKERS = ("série c", "serie c")
_SERIE_D_MARKERS = ("série d", "serie d")
_SEM_MARKERS = ("sem divisão", "sem divisao")


def dia_grid(agora: datetime | None = None) -> str:
    """Dia do puzzle em America/Sao_Paulo (YYYY-MM-DD). Vira à 00:00 SP."""
    now = agora or datetime.now(TZ_SP)
    if now.tzinfo is None:
        now = now.replace(tzinfo=TZ_SP)
    else:
        now = now.astimezone(TZ_SP)
    return now.date().isoformat()


def rotulo_dia(dia: str) -> str:
    try:
        return date.fromisoformat(dia).strftime("%d/%m/%Y")
    except ValueError:
        return dia


def ms_ate_proxima_virada(agora: datetime | None = None) -> int:
    """Milissegundos até a próxima 00:00 em America/Sao_Paulo."""
    from datetime import time, timedelta

    now = agora or datetime.now(TZ_SP)
    if now.tzinfo is None:
        now = now.replace(tzinfo=TZ_SP)
    else:
        now = now.astimezone(TZ_SP)
    amanha = now.date() + timedelta(days=1)
    virada = datetime.combine(amanha, time.min, tzinfo=TZ_SP)
    return max(0, int((virada - now).total_seconds() * 1000))


def normalizar_serie(divisao: str | None) -> str | None:
    d = (divisao or "").casefold()
    if not d:
        return None
    if any(m in d for m in _SEM_MARKERS):
        return "SEM"
    if any(m in d for m in _SERIE_A_MARKERS):
        return "A"
    if any(m in d for m in _SERIE_B_MARKERS):
        return "B"
    if any(m in d for m in _SERIE_C_MARKERS):
        return "C"
    if any(m in d for m in _SERIE_D_MARKERS):
        return "D"
    return None


@dataclass(frozen=True)
class Categoria:
    id: str
    tipo: str
    valor: str
    rotulo: str

    def to_public(self) -> dict[str, str]:
        return {"id": self.id, "tipo": self.tipo, "valor": self.valor, "rotulo": self.rotulo}


def _clube_enriquecido(c: dict[str, Any]) -> dict[str, Any]:
    nome = c["nome"]
    letra = nome[:1].upper() if nome and nome[0].isalpha() else ""
    return {
        **c,
        "serie": normalizar_serie(c.get("divisao")),
        "regiao": UF_PARA_REGIAO.get(c.get("uf") or ""),
        "letra": letra,
        "nome_norm": nome.casefold(),
    }


@lru_cache(maxsize=1)
def clubes_grid() -> tuple[dict[str, Any], ...]:
    """Só clubes BR (UF em região) entram no puzzle — exterior fica no perfil/times."""
    return tuple(
        _clube_enriquecido(dict(c))
        for c in carregar_clubes()
        if c.get("tem_emblema") and (c.get("uf") or "") in UF_PARA_REGIAO
    )


@lru_cache(maxsize=1)
def clubes_por_id() -> dict[str, dict[str, Any]]:
    return {c["id"]: c for c in clubes_grid()}


def clube_bate_categoria(clube: dict[str, Any], cat: Categoria) -> bool:
    if cat.tipo == "uf":
        return clube.get("uf") == cat.valor
    if cat.tipo == "regiao":
        return clube.get("regiao") == cat.valor
    if cat.tipo == "serie":
        return clube.get("serie") == cat.valor
    if cat.tipo == "letra":
        return clube.get("letra") == cat.valor
    return False


def categorias_compativeis(a: Categoria, b: Categoria) -> bool:
    """False quando a interseção é logicamente impossível."""
    if a.id == b.id:
        return False
    if a.tipo == b.tipo and a.valor != b.valor:
        # dois UFs / duas séries / duas letras distintas nunca intersectam
        return False
    if a.tipo == "uf" and b.tipo == "regiao":
        return a.valor in REGIOES.get(b.valor, set())
    if a.tipo == "regiao" and b.tipo == "uf":
        return b.valor in REGIOES.get(a.valor, set())
    return True


def pool_celula(row: Categoria, col: Categoria) -> list[dict[str, Any]]:
    if not categorias_compativeis(row, col):
        return []
    return [
        c
        for c in clubes_grid()
        if clube_bate_categoria(c, row) and clube_bate_categoria(c, col)
    ]


def _montar_categorias() -> list[Categoria]:
    clubes = clubes_grid()
    cats: list[Categoria] = []

    ufs = sorted({c["uf"] for c in clubes if c.get("uf")})
    for uf in ufs:
        n = sum(1 for c in clubes if c["uf"] == uf)
        if n >= DENSIDADE_MIN:
            cats.append(Categoria(f"uf:{uf}", "uf", uf, f"Clube de {uf}"))

    for reg in REGIOES:
        n = sum(1 for c in clubes if c.get("regiao") == reg)
        if n >= DENSIDADE_MIN:
            cats.append(Categoria(f"regiao:{reg}", "regiao", reg, f"Região {reg}"))

    serie_labels = {
        "A": "Brasileirão Série A",
        "B": "Brasileirão Série B",
        "C": "Brasileirão Série C",
        "D": "Brasileirão Série D",
        "SEM": "Sem divisão nacional",
    }
    for key, rotulo in serie_labels.items():
        n = sum(1 for c in clubes if c.get("serie") == key)
        if n >= DENSIDADE_MIN:
            cats.append(Categoria(f"serie:{key}", "serie", key, rotulo))

    for letra in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        n = sum(1 for c in clubes if c.get("letra") == letra)
        if n >= DENSIDADE_MIN:
            cats.append(
                Categoria(f"letra:{letra}", "letra", letra, f"Nome começa com {letra}")
            )

    return cats


@lru_cache(maxsize=1)
def categorias_disponiveis() -> tuple[Categoria, ...]:
    return tuple(_montar_categorias())


def _rng_dia(dia: str) -> random.Random:
    digest = hashlib.sha256(f"thdfm-grid-v1|{dia}".encode("utf-8")).hexdigest()
    return random.Random(int(digest[:16], 16))


def gerar_puzzle(dia: str | None = None) -> dict[str, Any]:
    """Gera grade 3×3 determinística para o dia; cada célula com ≥ DENSIDADE_MIN clubes."""
    dia_s = dia or dia_grid()
    cats = list(categorias_disponiveis())
    if len(cats) < GRID_SIZE * 2:
        raise RuntimeError("catálogo insuficiente para o grid")

    rng = _rng_dia(dia_s)
    by_tipo: dict[str, list[Categoria]] = {}
    for c in cats:
        by_tipo.setdefault(c.tipo, []).append(c)
        rng.shuffle(by_tipo[c.tipo])

    # Estratégia estável: um eixo "atributo geográfico/série", outro "letra"
    geo = list(by_tipo.get("uf") or []) + list(by_tipo.get("regiao") or []) + list(
        by_tipo.get("serie") or []
    )
    letras = list(by_tipo.get("letra") or [])
    rng.shuffle(geo)
    rng.shuffle(letras)

    templates = [
        ("geo", "letra"),
        ("letra", "geo"),
        ("mix", "letra"),
        ("letra", "mix"),
    ]
    rng.shuffle(templates)

    def montar_eixo(kind: str) -> list[list[Categoria]]:
        if kind == "letra":
            return [list(x) for x in _combinacoes(letras, GRID_SIZE, rng, limite=40)]
        if kind == "geo":
            return [list(x) for x in _combinacoes(geo, GRID_SIZE, rng, limite=60)]
        # mix: tenta misturar tipos
        pool = list(cats)
        rng.shuffle(pool)
        return [list(x) for x in _combinacoes(pool, GRID_SIZE, rng, limite=80)]

    for left_kind, right_kind in templates:
        left_opts = montar_eixo(left_kind)
        right_opts = montar_eixo(right_kind)
        rng.shuffle(left_opts)
        rng.shuffle(right_opts)
        for rows in left_opts:
            for cols in right_opts:
                ids_row = {c.id for c in rows}
                ids_col = {c.id for c in cols}
                if ids_row & ids_col:
                    continue
                densidades: list[list[int]] = []
                ok = True
                for r in rows:
                    linha_d: list[int] = []
                    for c in cols:
                        if not categorias_compativeis(r, c):
                            ok = False
                            break
                        n = len(pool_celula(r, c))
                        if n < DENSIDADE_MIN:
                            ok = False
                            break
                        linha_d.append(n)
                    if not ok:
                        break
                    densidades.append(linha_d)
                if not ok:
                    continue
                return {
                    "dia": dia_s,
                    "linhas": [c.to_public() for c in rows],
                    "colunas": [c.to_public() for c in cols],
                    "densidades": densidades,
                    "tamanho": GRID_SIZE,
                }

    raise RuntimeError(f"não foi possível gerar grid jogável para {dia_s}")


def _combinacoes(
    itens: list[Categoria],
    k: int,
    rng: random.Random,
    *,
    limite: int,
) -> list[tuple[Categoria, ...]]:
    if len(itens) < k:
        return []
    # amostra combinações sem explodir
    out: list[tuple[Categoria, ...]] = []
    visto: set[tuple[str, ...]] = set()
    for _ in range(limite * 3):
        pick = tuple(rng.sample(itens, k))
        key = tuple(sorted(c.id for c in pick))
        if key in visto:
            continue
        # no mesmo eixo, tipos exclusivos não podem repetir valor distinto do mesmo tipo
        # (já garantido por ids distintos); evita 3 UFs que depois travam com regiões
        visto.add(key)
        out.append(pick)
        if len(out) >= limite:
            break
    return out


def _sortear_eixo(
    rng: random.Random,
    by_tipo: dict[str, list[Categoria]],
    todas: list[Categoria],
) -> list[Categoria]:
    tipos = [t for t, lst in by_tipo.items() if lst]
    rng.shuffle(tipos)
    escolhidas: list[Categoria] = []
    usados: set[str] = set()
    for tipo in tipos:
        if len(escolhidas) >= GRID_SIZE:
            break
        opcoes = [c for c in by_tipo[tipo] if c.id not in usados]
        if not opcoes:
            continue
        pick = rng.choice(opcoes)
        escolhidas.append(pick)
        usados.add(pick.id)
    while len(escolhidas) < GRID_SIZE:
        opcoes = [c for c in todas if c.id not in usados]
        if not opcoes:
            break
        pick = rng.choice(opcoes)
        escolhidas.append(pick)
        usados.add(pick.id)
    rng.shuffle(escolhidas)
    return escolhidas[:GRID_SIZE]


def categoria_por_id(cat_id: str) -> Categoria | None:
    for c in categorias_disponiveis():
        if c.id == cat_id:
            return c
    return None


def puzzle_publico(dia: str | None = None) -> dict[str, Any]:
    p = gerar_puzzle(dia)
    dia_s = p["dia"]
    return {
        **p,
        "rotulo": rotulo_dia(dia_s),
        "virada_em_ms": ms_ate_proxima_virada(),
        "tz": "America/Sao_Paulo",
    }


def nome_core_norm(nome_norm: str) -> str:
    """Nome sem sufixo '(UF)' — base do limiar de sugestão."""
    return _UF_SUFFIX_RE.sub("", (nome_norm or "").strip()).strip()


def min_chars_sugestao(nome_norm: str) -> int:
    core = nome_core_norm(nome_norm)
    n = max(len(core), 1)
    return max(BUSCA_MIN_CHARS, math.ceil(n * SUGESTAO_FRACAO))


def _clube_elegivel_sugestao(clube: dict[str, Any], query: str) -> bool:
    """True se a query já cobre ~70% do nome e casa com o clube."""
    if len(query) < BUSCA_MIN_CHARS:
        return False
    nome = clube.get("nome_norm") or ""
    core = nome_core_norm(nome)
    if not (core.startswith(query) or nome.startswith(query) or query in core):
        return False
    return len(query) >= min_chars_sugestao(nome)


def buscar_celula(
    *,
    dia: str,
    linha: int,
    coluna: int,
    q: str,
    limite: int = BUSCA_LIMITE,
) -> dict[str, Any]:
    """Sugestões do catálogo completo após ~70% do nome (não só o pool certo)."""
    puzzle = gerar_puzzle(dia)
    if not (0 <= linha < GRID_SIZE and 0 <= coluna < GRID_SIZE):
        raise ValueError("célula inválida")
    row = categoria_por_id(puzzle["linhas"][linha]["id"])
    col = categoria_por_id(puzzle["colunas"][coluna]["id"])
    if not row or not col:
        raise ValueError("categoria inválida")
    pool = pool_celula(row, col)
    total = len(pool)
    query = (q or "").strip().casefold()
    pronto = len(query) >= BUSCA_MIN_CHARS
    itens: list[dict[str, Any]] = []
    if pronto:
        candidatos = [c for c in clubes_grid() if _clube_elegivel_sugestao(c, query)]
        candidatos.sort(
            key=lambda c: (
                0 if nome_core_norm(c["nome_norm"]).startswith(query) else 1,
                len(nome_core_norm(c["nome_norm"])),
                c["nome_norm"],
            )
        )
        lim = max(1, min(int(limite), 30))
        itens = [
            {
                "id": c["id"],
                "nome": c["nome"],
                "emblema": c["emblema"],
            }
            for c in candidatos[:lim]
        ]
    return {
        "total": total,
        "filtrados": len(itens),
        "itens": itens,
        "query": q or "",
        "min_chars": BUSCA_MIN_CHARS,
        "fracao_sugestao": SUGESTAO_FRACAO,
        "pronto": pronto,
        "sugestoes": True,
    }


def resolver_clube_por_nome(nome: str) -> dict[str, Any]:
    """Resolve chute digitado → clube do catálogo.

    Prefere match exato; senão, único candidato elegível pela regra dos ~70%.
    """
    query = (nome or "").strip().casefold()
    if len(query) < BUSCA_MIN_CHARS:
        raise ValueError(f"Digite pelo menos {BUSCA_MIN_CHARS} letras do nome")
    exatos = [c for c in clubes_grid() if c["nome_norm"] == query]
    if len(exatos) == 1:
        return exatos[0]
    if len(exatos) > 1:
        raise ValueError("Nome ambíguo — escolha na lista de sugestões")
    # Core exato (ex.: "santos" com vários "Santos (UF)")
    core_exatos = [c for c in clubes_grid() if nome_core_norm(c["nome_norm"]) == query]
    if len(core_exatos) == 1:
        return core_exatos[0]
    elegiveis = [c for c in clubes_grid() if _clube_elegivel_sugestao(c, query)]
    if len(elegiveis) == 1:
        return elegiveis[0]
    if not elegiveis:
        raise ValueError(
            "Clube não encontrado — continue digitando até aparecer na lista"
        )
    raise ValueError("Vários clubes batem — escolha na lista de sugestões")


def validar_chute(
    *,
    dia: str,
    linha: int,
    coluna: int,
    clube_id: str,
) -> dict[str, Any]:
    puzzle = gerar_puzzle(dia)
    if not (0 <= linha < GRID_SIZE and 0 <= coluna < GRID_SIZE):
        raise ValueError("célula inválida")
    row = categoria_por_id(puzzle["linhas"][linha]["id"])
    col = categoria_por_id(puzzle["colunas"][coluna]["id"])
    if not row or not col:
        raise ValueError("categoria inválida")
    clube = clubes_por_id().get(clube_id)
    if not clube:
        raise ValueError("clube inválido")
    ok = clube_bate_categoria(clube, row) and clube_bate_categoria(clube, col)
    return {
        "ok": ok,
        "clube": {
            "id": clube["id"],
            "nome": clube["nome"],
            "uf": clube["uf"],
            "emblema": clube["emblema"],
        },
        "linha": linha,
        "coluna": coluna,
    }


def texto_share(
    *,
    dia: str,
    celulas: list[list[dict[str, Any] | None]],
    url: str = "https://thdfm.com.br/grid",
) -> str:
    """Texto estilo Wordle/Hoops para Twitter/WhatsApp.

    Usa escapes explícitos dos quadrados coloridos (Unicode 12) para o
    texto não depender de charset do arquivo-fonte no cliente.
    """
    sq_ok = "\U0001f7e9"  # 🟩
    sq_miss = "\U0001f7e5"  # 🟥
    sq_empty = "\u2b1c"  # ⬜
    linhas_emoji: list[str] = []
    acertos = 0
    tentadas = 0
    for r in range(GRID_SIZE):
        row_e = []
        for c in range(GRID_SIZE):
            cell = celulas[r][c] if r < len(celulas) and c < len(celulas[r]) else None
            if not cell:
                row_e.append(sq_empty)
                continue
            tentadas += 1
            if cell.get("ok"):
                row_e.append(sq_ok)
                acertos += 1
            else:
                row_e.append(sq_miss)
        # Espaço entre quadrados: alguns clientes WhatsApp renderizam melhor
        linhas_emoji.append(" ".join(row_e))
    try:
        d = date.fromisoformat(dia)
        rotulo = d.strftime("%d/%m/%Y")
    except ValueError:
        rotulo = dia
    return (
        f"THDFM Grid — {rotulo}\n"
        f"{acertos}/{GRID_SIZE * GRID_SIZE}\n"
        + "\n".join(linhas_emoji)
        + f"\n{url}"
    )


def parse_celulas_progresso(raw: Any) -> list[list[dict[str, Any] | None]]:
    out: list[list[dict[str, Any] | None]] = [
        [None for _ in range(GRID_SIZE)] for _ in range(GRID_SIZE)
    ]
    if not isinstance(raw, list):
        return out
    for r, row in enumerate(raw[:GRID_SIZE]):
        if not isinstance(row, list):
            continue
        for c, cell in enumerate(row[:GRID_SIZE]):
            if isinstance(cell, dict) and cell.get("clube"):
                out[r][c] = cell
    return out


def celulas_completas(celulas: list[list[dict[str, Any] | None]]) -> bool:
    for r in range(GRID_SIZE):
        for c in range(GRID_SIZE):
            if not celulas[r][c]:
                return False
    return True


def dump_celulas(celulas: list[list[dict[str, Any] | None]]) -> str:
    return json.dumps(celulas, ensure_ascii=False)
