"""THDFM Grid — puzzle diário 3×3 de clubes BR (estilo Hoops Grid)."""

from __future__ import annotations

import hashlib
import json
import math
import random
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from functools import lru_cache
from typing import Any
from zoneinfo import ZoneInfo

from src.clubes_catalogo import carregar_clubes
from src.grid_historico import historico_meta, historico_serie_a

TZ_SP = ZoneInfo("America/Sao_Paulo")
GRID_SIZE = 3
DENSIDADE_MIN = 4
BUSCA_LIMITE = 12
BUSCA_MIN_CHARS = 3
# Só sugere clube depois de digitar ~70% do nome (sem sufixo de UF).
SUGESTAO_FRACAO = 0.70
_UF_SUFFIX_RE = re.compile(r"\s*\([a-z]{2}\)\s*$", re.I)


def fold_txt(s: str) -> str:
    """Minúsculas sem acento — busca/chute (Galícia ≈ galicia)."""
    base = unicodedata.normalize("NFKD", (s or "").strip())
    return "".join(c for c in base if not unicodedata.combining(c)).casefold()


# Categorias históricas (Brasileirão) só entram no puzzle a partir desta data
# (00:00 America/Sao_Paulo). Dias anteriores mantêm o pool antigo.
GRID_HISTORICO_DESDE = "2026-08-11"
# Gerador com variedade de tipos (v3). Dias anteriores ao cutover mantêm v1/v2.
# Regeneração admin (salt) em dia histórico também usa v3.
GRID_VARIEDADE_DESDE = "2026-08-12"
# Células por puzzle diário (3×3) — usado em barras do ranking.
GRID_CELULAS_POR_DIA = 9


def dias_totais_grid(ate: str | None = None) -> int:
    """Dias de calendário do Grid desde GRID_HISTORICO_DESDE até ate (inclusive)."""
    fim = date.fromisoformat(ate or dia_grid())
    ini = date.fromisoformat(GRID_HISTORICO_DESDE)
    if fim < ini:
        return 0
    return (fim - ini).days + 1


_TIPOS_HISTORICOS = frozenset(
    {"titulo", "premio", "participacao", "longevidade", "paridade", "goleada"}
)
_TIPOS_NOME = ("letra", "termina", "nome")
_TIPOS_GEO = (
    "uf",
    "nao_uf",
    "regiao",
    "nao_regiao",
    "serie",
    "titulo",
    "premio",
    "participacao",
    "longevidade",
    "paridade",
)
# No mesmo eixo: evita “só termina com…” / “só região” / “só Nome começa…”.
_MAX_POR_TIPO_EIXO: dict[str, int] = {
    "termina": 1,
    "regiao": 1,
    "nao_regiao": 1,
    "serie": 1,
    "letra": 1,
    "nome": 1,
    "uf": 1,
    "nao_uf": 1,
    "titulo": 1,
    "premio": 1,
    "participacao": 1,
    "longevidade": 1,
    "paridade": 1,
    "goleada": 1,
}

# Sufixos/sílabas comuns em nomes de clubes BR (pool do eixo "termina com").
TERMINACOES_SILABAS: tuple[str, ...] = (
    "ense",
    "ano",
    "ica",
    "rio",
    "eiro",
    "iro",
    "ria",
    "ina",
    "eira",
    "ara",
    "ico",
    "opolis",
    "olis",
    "inho",
    "cruz",
    "ista",
    "cano",
    "aba",
    "orte",
    "port",
    "ema",
    "elo",
)

REGIOES: dict[str, set[str]] = {
    "Norte": {"AC", "AP", "AM", "PA", "RO", "RR", "TO"},
    "Nordeste": {"AL", "BA", "CE", "MA", "PB", "PE", "PI", "RN", "SE"},
    "Centro-Oeste": {"DF", "GO", "MT", "MS"},
    "Sudeste": {"ES", "MG", "RJ", "SP"},
    "Sul": {"PR", "RS", "SC"},
}
UF_PARA_REGIAO = {uf: reg for reg, ufs in REGIOES.items() for uf in ufs}

# Gentílicos para rótulos do Grid (Time X / Não é X).
UF_GENTILICO: dict[str, str] = {
    "AC": "acreano",
    "AL": "alagoano",
    "AP": "amapaense",
    "AM": "amazonense",
    "BA": "baiano",
    "CE": "cearense",
    "DF": "brasiliense",
    "ES": "capixaba",
    "GO": "goiano",
    "MA": "maranhense",
    "MT": "mato-grossense",
    "MS": "sul-mato-grossense",
    "MG": "mineiro",
    "PA": "paraense",
    "PB": "paraibano",
    "PR": "paranaense",
    "PE": "pernambucano",
    "PI": "piauiense",
    "RJ": "carioca",
    "RN": "potiguar",
    "RS": "gaúcho",
    "RO": "rondoniano",
    "RR": "roraimense",
    "SC": "catarinense",
    "SP": "paulista",
    "SE": "sergipano",
    "TO": "tocantinense",
}


def rotulo_uf(uf: str) -> str:
    g = UF_GENTILICO.get(uf)
    return f"Time {g}" if g else f"Clube de {uf}"


def rotulo_nao_uf(uf: str) -> str:
    g = UF_GENTILICO.get(uf)
    return f"Não é {g}" if g else f"Não é de {uf}"

_SERIE_A_MARKERS = ("assaí", "assai", "série a", "serie a")
_SERIE_B_MARKERS = ("série b", "serie b")
_SERIE_C_MARKERS = ("série c", "serie c")
_SERIE_D_MARKERS = ("série d", "serie d")
_SEM_MARKERS = ("sem divisão", "sem divisao")


def get_virada_hm() -> tuple[int, int]:
    """(hora, minuto) da virada em America/Sao_Paulo. Padrão (0, 0)."""
    try:
        from src import db as dbmod

        return tuple(dbmod.get_grid_virada_hm())  # type: ignore[return-value]
    except Exception:
        return (0, 0)


def get_hora_virada() -> int:
    """Compat: só a hora (0–23) da virada."""
    return get_virada_hm()[0]


def _resolver_virada(
    hora_virada: int | tuple[int, int] | str | None = None,
    minuto_virada: int | None = None,
) -> tuple[int, int]:
    if hora_virada is None and minuto_virada is None:
        return get_virada_hm()
    if isinstance(hora_virada, tuple) and len(hora_virada) == 2:
        h, mi = int(hora_virada[0]), int(hora_virada[1])
    elif isinstance(hora_virada, str):
        from src import db as dbmod

        h, mi = dbmod.parse_grid_virada(hora_virada)
    elif hora_virada is None:
        h, mi = 0, int(minuto_virada or 0)
    else:
        h = int(hora_virada)
        mi = 0 if minuto_virada is None else int(minuto_virada)
    if not 0 <= h <= 23:
        h = 0
    if not 0 <= mi <= 59:
        mi = 0
    return (h, mi)


def rotulo_hora_virada(
    hora: int | tuple[int, int] | str | None = None,
    minuto: int | None = None,
) -> str:
    if hora is None and minuto is None:
        h, mi = get_virada_hm()
    else:
        h, mi = _resolver_virada(hora, minuto)
    return f"{h:02d}:{mi:02d}"


def dia_grid(
    agora: datetime | None = None,
    *,
    hora_virada: int | tuple[int, int] | str | None = None,
    minuto_virada: int | None = None,
) -> str:
    """Dia do puzzle em America/Sao_Paulo (YYYY-MM-DD).

    Meia-noite (00:00): o dia civil em SP.

    Outros horários: a virada abre o puzzle do *próximo* dia civil.
    Ex.: virada 22:20 — às 22:20 do dia 10 entra o puzzle 11/08;
    antes das 22:20 do dia 11 ainda é o puzzle 11/08.
    """
    from datetime import timedelta

    now = agora or datetime.now(TZ_SP)
    if now.tzinfo is None:
        now = now.replace(tzinfo=TZ_SP)
    else:
        now = now.astimezone(TZ_SP)
    h, mi = _resolver_virada(hora_virada, minuto_virada)
    # 00:00 = dia civil simples (comportamento clássico).
    if h == 0 and mi == 0:
        return now.date().isoformat()
    # Antes da virada: puzzle do dia civil corrente.
    # Na virada e depois: puzzle do dia seguinte (troca de fato).
    if (now.hour, now.minute) < (h, mi):
        return now.date().isoformat()
    return (now.date() + timedelta(days=1)).isoformat()


def rotulo_dia(dia: str) -> str:
    try:
        return date.fromisoformat(dia).strftime("%d/%m/%Y")
    except ValueError:
        return dia


def ms_ate_proxima_virada(
    agora: datetime | None = None,
    *,
    hora_virada: int | tuple[int, int] | str | None = None,
    minuto_virada: int | None = None,
) -> int:
    """Milissegundos até a próxima virada em America/Sao_Paulo."""
    from datetime import time, timedelta

    now = agora or datetime.now(TZ_SP)
    if now.tzinfo is None:
        now = now.replace(tzinfo=TZ_SP)
    else:
        now = now.astimezone(TZ_SP)
    h, mi = _resolver_virada(hora_virada, minuto_virada)
    alvo = datetime.combine(now.date(), time(hour=h, minute=mi), tzinfo=TZ_SP)
    if now >= alvo:
        alvo = alvo + timedelta(days=1)
    return max(0, int((alvo - now).total_seconds() * 1000))


def _salt_dia(dia: str) -> str:
    try:
        from src import db as dbmod

        return dbmod.get_grid_salt(dia) or ""
    except Exception:
        return ""


def variedade_ativa(dia: str | None = None) -> bool:
    """True a partir de GRID_VARIEDADE_DESDE, ou se o dia histórico foi regenerado."""
    dia_s = dia or dia_grid()
    if dia_s >= GRID_VARIEDADE_DESDE:
        return True
    return historico_ativo(dia_s) and bool(_salt_dia(dia_s))


def _rng_dia(dia: str) -> random.Random:
    # v1: pool clássico; v2: histórico; v3: histórico + variedade de tipos
    # salt opcional: regeneração admin de um dia sem afetar os demais
    if variedade_ativa(dia):
        # v6: pesos — UF positiva e Série C sobem; “Não é…” desce
        ver = "v6"
    elif historico_ativo(dia):
        ver = "v2"
    else:
        ver = "v1"
    salt = _salt_dia(dia)
    base = f"thdfm-grid-{ver}|{dia}"
    payload = f"{base}|{salt}" if salt else base
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return random.Random(int(digest[:16], 16))


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
    nome_norm = fold_txt(nome)
    core = nome_core_norm(nome_norm)
    sig = nome_sem_prefixo_juridico(nome_norm)
    letra = ""
    for ch in sig:
        if ch.isalpha():
            letra = ch.upper()
            break
    if not letra:
        letra = nome[:1].upper() if nome and nome[0].isalpha() else ""
    termina_letra = ""
    for ch in reversed(core):
        if ch.isalpha():
            termina_letra = ch.upper()
            break
    letras = [ch for ch in core if ch.isalpha()]
    vogais = sum(1 for ch in letras if ch in "aeiou")
    cons = len(letras) - vogais
    tam = len(letras)
    return {
        **c,
        "serie": normalizar_serie(c.get("divisao")),
        "regiao": UF_PARA_REGIAO.get(c.get("uf") or ""),
        "letra": letra,
        "nome_norm": nome_norm,
        "nome_core": core,
        "nome_sig": sig,
        "termina_letra": termina_letra,
        "nome_nvogais": vogais,
        "nome_ncons": cons,
        "nome_tam": tam,
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


def historico_ativo(dia: str | None = None) -> bool:
    """True a partir de GRID_HISTORICO_DESDE (virada 00:00 SP)."""
    dia_s = dia or dia_grid()
    return dia_s >= GRID_HISTORICO_DESDE


def clube_bate_categoria(clube: dict[str, Any], cat: Categoria) -> bool:
    if cat.tipo == "uf":
        return clube.get("uf") == cat.valor
    if cat.tipo == "nao_uf":
        return bool(clube.get("uf")) and clube.get("uf") != cat.valor
    if cat.tipo == "regiao":
        return clube.get("regiao") == cat.valor
    if cat.tipo == "nao_regiao":
        return bool(clube.get("regiao")) and clube.get("regiao") != cat.valor
    if cat.tipo == "serie":
        return clube.get("serie") == cat.valor
    if cat.tipo == "letra":
        return clube.get("letra") == cat.valor
    if cat.tipo == "termina":
        core = clube.get("nome_core") or nome_core_norm(clube.get("nome_norm") or "")
        suf = fold_txt(cat.valor)
        if not suf:
            return False
        if len(suf) == 1:
            return (clube.get("termina_letra") or "") == suf.upper()
        return core.endswith(suf)
    if cat.tipo == "nome":
        return _clube_bate_nome(clube, cat.valor)
    if cat.tipo in _TIPOS_HISTORICOS:
        ids = historico_serie_a().get(cat.id)
        return bool(ids) and clube.get("id") in ids
    return False


def _clube_bate_nome(clube: dict[str, Any], valor: str) -> bool:
    core = clube.get("nome_core") or ""
    if valor == "vogal":
        return bool(core) and core[0] in "aeiou"
    if valor == "kwy":
        return any(ch in core for ch in "kwy")
    if valor == "curto":
        return 0 < int(clube.get("nome_tam") or 0) <= 6
    if valor == "longo":
        return int(clube.get("nome_tam") or 0) >= 12
    if valor.startswith("nv:"):
        try:
            n = int(valor.split(":", 1)[1])
        except ValueError:
            return False
        return int(clube.get("nome_nvogais") or 0) == n
    if valor.startswith("nc:"):
        try:
            n = int(valor.split(":", 1)[1])
        except ValueError:
            return False
        return int(clube.get("nome_ncons") or 0) == n
    if valor.startswith("tem:"):
        ch = valor.split(":", 1)[1]
        return len(ch) == 1 and ch in core
    if valor.startswith("nao:"):
        ch = valor.split(":", 1)[1]
        return bool(core) and len(ch) == 1 and ch not in core
    return False


def _nomes_compativeis(va: str, vb: str) -> bool:
    """Regras de interseção entre filtros de nome."""
    if va == vb:
        return False

    def fam(v: str) -> str:
        return v.split(":", 1)[0] if ":" in v else v

    fa, fb = fam(va), fam(vb)
    if fa == "nv" and fb == "nv":
        return False
    if fa == "nc" and fb == "nc":
        return False
    if fa == "tem" and fb == "tem":
        return va != vb
    if fa == "nao" and fb == "nao":
        return va != vb
    if {fa, fb} == {"tem", "nao"}:
        return va.split(":", 1)[1] != vb.split(":", 1)[1]
    if {va, vb} == {"curto", "longo"}:
        return False
    return True


_PARES_COMPLEMENTO_HIST = frozenset(
    {
        frozenset({"titulo:campeao_br", "titulo:nunca_campeao_br"}),
        frozenset({"premio:artilheiro", "premio:nunca_artilheiro"}),
        frozenset({"premio:melhor_defesa", "premio:nunca_melhor_defesa"}),
        frozenset({"premio:rebaixado", "premio:nunca_rebaixado"}),
        frozenset({"titulo:campeao_cdb", "titulo:nunca_campeao_cdb"}),
        frozenset({"titulo:final_cdb", "titulo:nunca_final_cdb"}),
        frozenset({"participacao:serie_a", "participacao:nunca_serie_a"}),
        frozenset({"participacao:serie_b", "participacao:nunca_serie_b"}),
        frozenset({"participacao:serie_c", "participacao:nunca_serie_c"}),
        frozenset({"participacao:cdb", "participacao:nunca_cdb"}),
        frozenset({"titulo:campeao_br", "premio:g4_sem_titulo"}),
        frozenset({"titulo:campeao_br", "titulo:vice_sem_campeao"}),
        frozenset({"titulo:campeao_cdb", "titulo:vice_cdb_sem_campeao"}),
        frozenset({"titulo:campeao_br", "titulo:campeao_cdb_sem_br"}),
        frozenset({"titulo:campeao_cdb", "titulo:campeao_br_sem_cdb"}),
    }
)

_NUNCA_SERIE_RE = re.compile(r"^participacao:nunca_(serie_[abc]|cdb)$")


def _implica_participacao_serie(cat_id: str, tag: str) -> bool:
    """True se a categoria só faz sentido para quem já jogou aquela série/copa."""
    if cat_id.startswith(f"participacao:nunca_{tag}"):
        return False
    if cat_id.startswith(f"participacao:{tag}"):
        return True
    if cat_id.startswith(f"longevidade:{tag}"):
        return True
    if tag == "cdb":
        if cat_id.startswith(("participacao:cdb", "longevidade:cdb")):
            return True
        if "cdb" not in cat_id:
            return False
        if "nunca" in cat_id or cat_id.endswith("sem_cdb"):
            return False
        return cat_id.startswith(("titulo:", "goleada:", "premio:"))
    # título/prêmio/goleada específicos da série (…_serie_b) ou Série A “solta”
    if tag == "serie_a":
        if cat_id.startswith(
            (
                "titulo:campeao_br",
                "titulo:vice_br",
                "titulo:vice_sem_campeao",
                "titulo:nunca_campeao_br",
                "premio:g4",
                "premio:melhor_",
                "premio:pior_defesa",
                "premio:artilheiro",
                "premio:lanterna",
                "premio:mais_",
                "premio:rebaixado",
                "premio:nunca_",
                "goleada:presente",
                "goleada:aplicou",
                "goleada:sofreu",
                "paridade:",
            )
        ) and "_serie_b" not in cat_id and "_serie_c" not in cat_id and "_cdb" not in cat_id:
            # nunca_rebaixado etc. ainda pressupõem histórico de A? "Nunca rebaixado" includes never played A
            if cat_id.startswith("premio:nunca_") or cat_id.startswith("titulo:nunca_"):
                return False
            return True
        return False
    suf = f"_{tag}"
    return suf in cat_id


def categorias_compativeis(a: Categoria, b: Categoria) -> bool:
    """False quando a interseção é logicamente impossível."""
    if a.id == b.id:
        return False
    if frozenset({a.id, b.id}) in _PARES_COMPLEMENTO_HIST:
        return False
    for cat_n, cat_o in ((a, b), (b, a)):
        m = _NUNCA_SERIE_RE.match(cat_n.id)
        if m and _implica_participacao_serie(cat_o.id, m.group(1)):
            return False
    # Terminações: letras/sílabas distintas só cruzam se uma for sufixo da outra
    # (ex.: ense ∩ e; eiro ∩ iro). Caso contrário, vazio.
    if a.tipo == "termina" and b.tipo == "termina":
        va = fold_txt(a.valor)
        vb = fold_txt(b.valor)
        if not va or not vb or va == vb:
            return False
        return va.endswith(vb) or vb.endswith(va)
    if a.tipo == "nome" and b.tipo == "nome":
        return _nomes_compativeis(a.valor, b.valor)
    # Negacoes UF/regiao: valores distintos AINDA intersectam (nao-SP ∩ nao-RJ).
    if a.tipo == "nao_uf" and b.tipo == "nao_uf":
        return a.valor != b.valor
    if a.tipo == "nao_regiao" and b.tipo == "nao_regiao":
        return a.valor != b.valor
    if a.tipo == "uf" and b.tipo == "nao_uf":
        return a.valor != b.valor
    if a.tipo == "nao_uf" and b.tipo == "uf":
        return a.valor != b.valor
    if a.tipo == "regiao" and b.tipo == "nao_regiao":
        return a.valor != b.valor
    if a.tipo == "nao_regiao" and b.tipo == "regiao":
        return a.valor != b.valor
    if a.tipo == "nao_uf" and b.tipo == "regiao":
        # Ex.: nao-SP ∩ Sudeste ainda tem RJ/MG/ES.
        return True
    if a.tipo == "regiao" and b.tipo == "nao_uf":
        return True
    if a.tipo == "nao_regiao" and b.tipo == "uf":
        return b.valor not in REGIOES.get(a.valor, set())
    if a.tipo == "uf" and b.tipo == "nao_regiao":
        return a.valor not in REGIOES.get(b.valor, set())
    if a.tipo == "nao_uf" and b.tipo == "nao_regiao":
        return True
    if a.tipo == "nao_regiao" and b.tipo == "nao_uf":
        return True
    if a.tipo == b.tipo and a.valor != b.valor:
        # dois UFs / duas séries / duas letras distintas nunca intersectam
        return False
    if a.tipo == "uf" and b.tipo == "regiao":
        return a.valor in REGIOES.get(b.valor, set())
    if a.tipo == "regiao" and b.tipo == "uf":
        return b.valor in REGIOES.get(a.valor, set())
    # Subconjuntos históricos: longevidade 20 ⊂ 10 ⊂ participação
    if {a.id, b.id} == {"longevidade:serie_a_10", "longevidade:serie_a_20"}:
        return True
    if {a.id, b.id} == {"participacao:serie_a", "longevidade:serie_a_10"}:
        return True
    if {a.id, b.id} == {"participacao:serie_a", "longevidade:serie_a_20"}:
        return True
    # ≥N e ≤M da mesma competição: vazios se N > M
    ge_le = _longevidade_ge_le_incompativel(a.id, b.id)
    if ge_le is False:
        return False
    # Campeão ⊂ G4; vice não necessariamente ⊂ campeão
    if a.id == "titulo:campeao_br" and b.id == "premio:g4":
        return True
    if b.id == "titulo:campeao_br" and a.id == "premio:g4":
        return True
    # Paridade de campeão ∩ campeão = a própria paridade (ok, denso o bastante via outras)
    return True


_LONG_GE_RE = re.compile(r"^longevidade:(serie_[abc]|cdb)_(\d+)$")
_LONG_LE_RE = re.compile(r"^longevidade:(serie_[abc]|cdb)_le_(\d+)$")


def _longevidade_ge_le_incompativel(id_a: str, id_b: str) -> bool | None:
    """False se ≥N e ≤M da mesma liga com N > M (interseção vazia). None = não se aplica."""
    ga, gb = _LONG_GE_RE.match(id_a), _LONG_GE_RE.match(id_b)
    la, lb = _LONG_LE_RE.match(id_a), _LONG_LE_RE.match(id_b)
    if ga and lb and ga.group(1) == lb.group(1):
        return not (int(ga.group(2)) > int(lb.group(2)))
    if gb and la and gb.group(1) == la.group(1):
        return not (int(gb.group(2)) > int(la.group(2)))
    return None

def pool_celula(row: Categoria, col: Categoria) -> list[dict[str, Any]]:
    if not categorias_compativeis(row, col):
        return []
    return [
        c
        for c in clubes_grid()
        if clube_bate_categoria(c, row) and clube_bate_categoria(c, col)
    ]


def _montar_categorias(dia: str) -> list[Categoria]:
    clubes = clubes_grid()
    cats: list[Categoria] = []

    ufs = sorted({c["uf"] for c in clubes if c.get("uf")})
    for uf in ufs:
        n = sum(1 for c in clubes if c["uf"] == uf)
        if n >= DENSIDADE_MIN:
            cats.append(Categoria(f"uf:{uf}", "uf", uf, rotulo_uf(uf)))
        # Negacoes entram com o cutover historico para nao alterar puzzles antigos.
        if historico_ativo(dia):
            n_nao = sum(1 for c in clubes if c.get("uf") and c["uf"] != uf)
            if n_nao >= DENSIDADE_MIN:
                cats.append(
                    Categoria(f"nao_uf:{uf}", "nao_uf", uf, rotulo_nao_uf(uf))
                )

    for reg in REGIOES:
        n = sum(1 for c in clubes if c.get("regiao") == reg)
        if n >= DENSIDADE_MIN:
            cats.append(Categoria(f"regiao:{reg}", "regiao", reg, f"Região {reg}"))
        if historico_ativo(dia):
            n_nao = sum(1 for c in clubes if c.get("regiao") and c.get("regiao") != reg)
            if n_nao >= DENSIDADE_MIN:
                cats.append(
                    Categoria(
                        f"nao_regiao:{reg}",
                        "nao_regiao",
                        reg,
                        f"Não é da região {reg}",
                    )
                )

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

    for letra in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        n = sum(1 for c in clubes if c.get("termina_letra") == letra)
        if n >= DENSIDADE_MIN:
            cats.append(
                Categoria(
                    f"termina:{letra}",
                    "termina",
                    letra,
                    f"Nome termina com {letra}",
                )
            )

    for silaba in TERMINACOES_SILABAS:
        suf = fold_txt(silaba)
        if not suf:
            continue
        n = sum(1 for c in clubes if (c.get("nome_core") or "").endswith(suf))
        if n >= DENSIDADE_MIN:
            cats.append(
                Categoria(
                    f"termina:{suf}",
                    "termina",
                    suf,
                    f"Nome termina com {suf}",
                )
            )

    # Filtros de nome extras (cutover histórico — não altera puzzles antigos).
    if historico_ativo(dia):
        cats.extend(_categorias_nome(clubes))
        hist = historico_serie_a()
        ids_grid = {c["id"] for c in clubes}
        for cat_id, tipo, valor, rotulo in historico_meta():
            membros = hist.get(cat_id) or frozenset()
            n = sum(1 for cid in membros if cid in ids_grid)
            if n >= DENSIDADE_MIN:
                cats.append(Categoria(cat_id, tipo, valor, rotulo))

    return cats


def _categorias_nome(clubes: tuple[dict[str, Any], ...] | list[dict[str, Any]]) -> list[Categoria]:
    out: list[Categoria] = []

    def add(valor: str, rotulo: str, pred) -> None:
        n = sum(1 for c in clubes if pred(c))
        if n >= DENSIDADE_MIN:
            out.append(Categoria(f"nome:{valor}", "nome", valor, rotulo))

    add("vogal", "Nome começa com vogal", lambda c: bool(c.get("nome_core")) and c["nome_core"][0] in "aeiou")
    add("kwy", "Nome tem K, W ou Y", lambda c: any(ch in (c.get("nome_core") or "") for ch in "kwy"))
    add("curto", "Nome curto (≤6 letras)", lambda c: 0 < int(c.get("nome_tam") or 0) <= 6)
    add("longo", "Nome longo (≥12 letras)", lambda c: int(c.get("nome_tam") or 0) >= 12)
    for n in range(1, 12):
        add(f"nv:{n}", f"Nome tem {n} vogais", lambda c, n=n: int(c.get("nome_nvogais") or 0) == n)
        add(f"nc:{n}", f"Nome tem {n} consoantes", lambda c, n=n: int(c.get("nome_ncons") or 0) == n)
    for ch in "abcdefghijklmnopqrstuvwxyz":
        add(f"tem:{ch}", f"Nome tem a letra {ch.upper()}", lambda c, ch=ch: ch in (c.get("nome_core") or ""))
        add(
            f"nao:{ch}",
            f"Nome não tem a letra {ch.upper()}",
            lambda c, ch=ch: bool(c.get("nome_core")) and ch not in c["nome_core"],
        )
    return out


@lru_cache(maxsize=16)
def categorias_disponiveis(dia: str | None = None) -> tuple[Categoria, ...]:
    dia_s = dia or dia_grid()
    return tuple(_montar_categorias(dia_s))


def gerar_puzzle(dia: str | None = None) -> dict[str, Any]:
    """Gera grade 3×3 determinística para o dia; cada célula com ≥ DENSIDADE_MIN clubes.

    Nunca deixa o /grid quebrar: se o gerador principal falhar, tenta o outro
    e por fim uma busca ampla garantida.
    """
    dia_s = dia or dia_grid()
    if variedade_ativa(dia_s):
        primary, secondary = _gerar_puzzle_variado, _gerar_puzzle_legado
    else:
        primary, secondary = _gerar_puzzle_legado, _gerar_puzzle_variado
    try:
        return primary(dia_s)
    except RuntimeError:
        pass
    try:
        return secondary(dia_s)
    except RuntimeError:
        pass
    return _gerar_puzzle_garantido(dia_s)


def _gerar_puzzle_legado(dia_s: str) -> dict[str, Any]:
    """Gerador v1/v2 (sem caps de variedade) — mantém puzzles antigos estáveis."""
    cats = list(categorias_disponiveis(dia_s))
    if len(cats) < GRID_SIZE * 2:
        raise RuntimeError("catálogo insuficiente para o grid")

    rng = _rng_dia(dia_s)
    by_tipo: dict[str, list[Categoria]] = {}
    for c in cats:
        by_tipo.setdefault(c.tipo, []).append(c)
        rng.shuffle(by_tipo[c.tipo])

    # Estratégia estável: um eixo "atributo/história", outro "nome (começa/termina)"
    geo = (
        list(by_tipo.get("uf") or [])
        + list(by_tipo.get("regiao") or [])
        + list(by_tipo.get("serie") or [])
        + list(by_tipo.get("titulo") or [])
        + list(by_tipo.get("premio") or [])
        + list(by_tipo.get("participacao") or [])
        + list(by_tipo.get("longevidade") or [])
        + list(by_tipo.get("paridade") or [])
        + list(by_tipo.get("goleada") or [])
    )
    nome_eixo = list(by_tipo.get("letra") or []) + list(by_tipo.get("termina") or [])
    rng.shuffle(geo)
    rng.shuffle(nome_eixo)

    templates = [
        ("geo", "letra"),
        ("letra", "geo"),
        ("mix", "letra"),
        ("letra", "mix"),
    ]
    rng.shuffle(templates)

    def montar_eixo(kind: str) -> list[list[Categoria]]:
        if kind == "letra":
            return [list(x) for x in _combinacoes(nome_eixo, GRID_SIZE, rng, limite=100)]
        if kind == "geo":
            return [list(x) for x in _combinacoes(geo, GRID_SIZE, rng, limite=120)]
        pool = list(cats)
        rng.shuffle(pool)
        return [list(x) for x in _combinacoes(pool, GRID_SIZE, rng, limite=160)]

    for left_kind, right_kind in templates:
        left_opts = montar_eixo(left_kind)
        right_opts = montar_eixo(right_kind)
        rng.shuffle(left_opts)
        rng.shuffle(right_opts)
        for rows in left_opts:
            for cols in right_opts:
                board = _tentar_board(rows, cols)
                if board:
                    return {
                        "dia": dia_s,
                        "linhas": [c.to_public() for c in board[0]],
                        "colunas": [c.to_public() for c in board[1]],
                        "densidades": board[2],
                        "tamanho": GRID_SIZE,
                    }

    raise RuntimeError(f"não foi possível gerar grid jogável para {dia_s}")


def _gerar_puzzle_garantido(dia_s: str) -> dict[str, Any]:
    """Último recurso: amostras amplas até achar grade densa (evita HTTP 500)."""
    cats = list(categorias_disponiveis(dia_s))
    if len(cats) < GRID_SIZE * 2:
        raise RuntimeError("catálogo insuficiente para o grid")
    rng = _rng_dia(dia_s)
    memo: dict[tuple[str, str], int] = {}
    n = len(cats)
    fallback: dict[str, Any] | None = None
    for _ in range(max(2500, n * 8)):
        rows = list(rng.sample(cats, GRID_SIZE))
        ids = {c.id for c in rows}
        resto = [c for c in cats if c.id not in ids]
        if len(resto) < GRID_SIZE:
            continue
        cols = list(rng.sample(resto, GRID_SIZE))
        board = _tentar_board(rows, cols, memo)
        if not board:
            continue
        r, c, dens = board
        payload = {
            "dia": dia_s,
            "linhas": [x.to_public() for x in r],
            "colunas": [x.to_public() for x in c],
            "densidades": dens,
            "tamanho": GRID_SIZE,
        }
        if _board_diverso(r, c):
            return payload
        if fallback is None:
            fallback = payload
    if fallback is not None:
        return fallback
    raise RuntimeError(f"não foi possível gerar grid jogável para {dia_s}")


def _max_tipo(tipo: str) -> int:
    return _MAX_POR_TIPO_EIXO.get(tipo, 1)


def _subgrupo_categoria(cat: Categoria) -> str:
    """Subgrupo semântico — no máximo 1 categoria do mesmo subgrupo por eixo.

    Agrupa rótulos parecidos (ex.: vários “Já…”, “Não é…”, contagens “≥N”,
    eras “Disputou/Jogou…”) mesmo quando o `tipo` técnico difere.
    """
    t = cat.tipo
    if t in ("uf", "regiao"):
        return "geo_pos"
    if t in ("nao_uf", "nao_regiao"):
        return "geo_neg"
    if t == "serie":
        return "serie"
    if t in _TIPOS_NOME:
        return "nome"
    if t == "paridade":
        return "hist_paridade"
    if t == "longevidade":
        return "hist_contagem"
    if t == "goleada":
        return "hist_ja"

    rot = (cat.rotulo or "").strip()
    if rot.startswith("Já "):
        return "hist_ja"
    if rot.startswith("Nunca "):
        return "hist_nunca"
    if rot.startswith("≥") or rot.startswith(">="):
        return "hist_contagem"
    if t == "participacao":
        return "hist_era"
    if t in ("titulo", "premio"):
        # Ex.: "Campeão da Copa e nunca do Brasileirão"
        return "hist_titulo_composto"
    return t


def _categoria_serie_c(cat: Categoria) -> bool:
    """True se a categoria fala explicitamente da Série C."""
    if cat.tipo == "serie" and str(cat.valor).upper() == "C":
        return True
    valor = str(cat.valor or "").casefold()
    if "serie_c" in valor:
        return True
    rot = fold_txt(cat.rotulo or "")
    return "serie c" in rot


def _peso_categoria(cat: Categoria) -> float:
    """Peso no sorteio: UF positiva e Série C sobem; negações e nome descem."""
    t = cat.tipo
    w = 1.0
    if t == "uf":
        # “Time rondoniano” filtra bem; preferir a “Não é rondoniano”
        w *= 4.5
    elif t == "regiao":
        w *= 2.8
    elif t == "nao_uf":
        w *= 0.22
    elif t == "nao_regiao":
        w *= 0.35
    elif t in _TIPOS_NOME:
        w *= 0.55
    elif t == "serie":
        # Divisão atual: C um pouco acima de A/B/D
        serie = str(cat.valor or "").upper()
        if serie == "C":
            w *= 3.5
        elif serie in ("A", "B"):
            w *= 1.1
        else:
            w *= 0.9

    if _categoria_serie_c(cat):
        w *= 3.8
    return w


def _amostra_ponderada(
    rng: random.Random,
    itens: list[Categoria],
    *,
    k: int,
) -> list[Categoria]:
    """Amostra sem reposição com probabilidade proporcional a `_peso_categoria`."""
    if not itens or k <= 0:
        return []
    pool = list(itens)
    pesos = [_peso_categoria(c) for c in pool]
    out: list[Categoria] = []
    n = min(k, len(pool))
    for _ in range(n):
        total = sum(pesos)
        if total <= 0:
            # fallback uniforme
            idx = rng.randrange(len(pool))
        else:
            alvo = rng.random() * total
            acc = 0.0
            idx = len(pool) - 1
            for i, p in enumerate(pesos):
                acc += p
                if alvo <= acc:
                    idx = i
                    break
        out.append(pool.pop(idx))
        pesos.pop(idx)
    return out


def _eixo_parcial_ok(cats: list[Categoria]) -> bool:
    """Regras de diversidade aplicáveis a um eixo incompleto (1..GRID_SIZE)."""
    if not cats or len(cats) > GRID_SIZE:
        return False
    cont_tipo = Counter(c.tipo for c in cats)
    for tipo, n in cont_tipo.items():
        if n > _max_tipo(tipo):
            return False
    cont_sub = Counter(_subgrupo_categoria(c) for c in cats)
    if any(n > 1 for n in cont_sub.values()):
        return False
    n_nome = sum(1 for c in cats if c.tipo in _TIPOS_NOME)
    if n_nome > 1:
        return False
    return True


def _eixo_diverso(cats: list[Categoria]) -> bool:
    """Eixo válido: 3 cats, ≥2 tipos, ≤1 por subgrupo semântico, ≤1 nome."""
    if len(cats) != GRID_SIZE:
        return False
    if not _eixo_parcial_ok(cats):
        return False
    if len({c.tipo for c in cats}) < 2:
        return False
    return True


def _board_diverso(rows: list[Categoria], cols: list[Categoria]) -> bool:
    """Board no estilo HoopsGrid: eixos diversos e poucas categorias de nome."""
    if not _eixo_diverso(rows) or not _eixo_diverso(cols):
        return False
    if all(c.tipo in _TIPOS_NOME for c in rows):
        return False
    if all(c.tipo in _TIPOS_NOME for c in cols):
        return False
    n_nome = sum(1 for c in rows + cols if c.tipo in _TIPOS_NOME)
    if n_nome > 2:
        return False
    familias = {_familia_categoria(c.tipo) for c in rows + cols}
    return len(familias) >= 2


def _sortear_tipos_livres(
    rng: random.Random, tipos_disp: list[str], k: int = GRID_SIZE
) -> list[str] | None:
    """Sorteia tipos com peso igual (não pelo tamanho do pool de cada tipo)."""
    if len(tipos_disp) < 2:
        return None
    pool = list(tipos_disp)
    rng.shuffle(pool)
    escolhidos: list[str] = []
    cont: Counter[str] = Counter()

    # Prefere tipos distintos
    for t in pool:
        if len(escolhidos) >= k:
            break
        if cont[t] >= _max_tipo(t):
            continue
        if t in escolhidos and _max_tipo(t) <= 1:
            continue
        escolhidos.append(t)
        cont[t] += 1

    while len(escolhidos) < k:
        extras = [t for t in pool if cont[t] < _max_tipo(t)]
        if not extras:
            return None
        t = rng.choice(extras)
        escolhidos.append(t)
        cont[t] += 1

    rng.shuffle(escolhidos)
    return escolhidos[:k]


def _opcoes_eixo_livre(
    rng: random.Random,
    by_tipo: dict[str, list[Categoria]],
    *,
    limite: int,
    tipos_preferidos: tuple[str, ...] | None = None,
) -> list[list[Categoria]]:
    """Monta eixos a partir de qualquer tipo denso; opcionalmente enviesa a um subconjunto."""
    if tipos_preferidos:
        tipos_base = [t for t in tipos_preferidos if by_tipo.get(t)]
    else:
        tipos_base = [t for t, lst in by_tipo.items() if lst]
    if len(tipos_base) < 2:
        return []

    out: list[list[Categoria]] = []
    visto: set[tuple[str, ...]] = set()
    for _ in range(limite * 6):
        tipos = _sortear_tipos_livres(rng, tipos_base)
        if not tipos:
            continue
        usados: set[str] = set()
        cats: list[Categoria] = []
        ok = True
        for t in tipos:
            opcoes = [c for c in by_tipo.get(t, []) if c.id not in usados]
            if not opcoes:
                ok = False
                break
            pick = _amostra_ponderada(rng, opcoes, k=1)[0]
            cats.append(pick)
            usados.add(pick.id)
        if not ok or not _eixo_diverso(cats):
            continue
        key = tuple(sorted(c.id for c in cats))
        if key in visto:
            continue
        visto.add(key)
        out.append(cats)
        if len(out) >= limite:
            break
    return out


def _densidade_celula(
    row: Categoria,
    col: Categoria,
    memo: dict[tuple[str, str], int],
) -> int | None:
    """Retorna densidade da célula ou None se incompatível."""
    if not categorias_compativeis(row, col):
        return None
    key = (row.id, col.id)
    if key not in memo:
        memo[key] = len(pool_celula(row, col))
    return memo[key]


def _candidato_encaixa_no_outro_eixo(
    cat: Categoria,
    outro: list[Categoria],
    *,
    cat_eh_linha: bool,
    memo: dict[tuple[str, str], int],
) -> bool:
    """Valida solubilidade de `cat` contra todas as categorias já fixadas no outro eixo."""
    for outra in outro:
        row, col = (cat, outra) if cat_eh_linha else (outra, cat)
        n = _densidade_celula(row, col, memo)
        if n is None or n < DENSIDADE_MIN:
            return False
    return True


def _tentar_board(
    rows: list[Categoria],
    cols: list[Categoria],
    memo: dict[tuple[str, str], int] | None = None,
) -> tuple[list[Categoria], list[Categoria], list[list[int]]] | None:
    ids_row = {c.id for c in rows}
    ids_col = {c.id for c in cols}
    if ids_row & ids_col:
        return None
    cache = memo if memo is not None else {}
    densidades: list[list[int]] = []
    for r in rows:
        linha_d: list[int] = []
        for c in cols:
            n = _densidade_celula(r, c, cache)
            if n is None or n < DENSIDADE_MIN:
                return None
            linha_d.append(n)
        densidades.append(linha_d)
    return rows, cols, densidades


def _familia_categoria(tipo: str) -> str:
    if tipo in _TIPOS_NOME:
        return "nome"
    if tipo in ("uf", "nao_uf", "regiao", "nao_regiao", "serie"):
        return "geo"
    if tipo in _TIPOS_HISTORICOS:
        return "hist"
    return tipo


def _score_variedade(
    rows: list[Categoria], cols: list[Categoria], densidades: list[list[int]]
) -> tuple[int, int, int, int]:
    """Maior = melhor: famílias distintas, UF+, Série C, pouco “Não é…”/Nome."""
    all_cats = rows + cols
    familias = {_familia_categoria(c.tipo) for c in all_cats}
    tipos_all = {c.tipo for c in all_cats}
    n_hist = sum(1 for t in tipos_all if t in _TIPOS_HISTORICOS)
    n_nome = sum(1 for c in all_cats if c.tipo in _TIPOS_NOME)
    n_outros = len(tipos_all) - n_hist
    diversidade = n_outros + min(n_hist, 2)
    tipos_eixo = len({c.tipo for c in rows}) + len({c.tipo for c in cols})
    dens_min = min(n for linha in densidades for n in linha)
    cont = Counter(c.tipo for c in all_cats)
    mono_penalty = sum(1 for n in cont.values() if n >= 3)
    nome_bonus = 2 - n_nome
    subgrupos = {_subgrupo_categoria(c) for c in all_cats}
    n_geo_pos = sum(1 for c in all_cats if c.tipo in ("uf", "regiao"))
    n_geo_neg = sum(1 for c in all_cats if c.tipo in ("nao_uf", "nao_regiao"))
    n_serie_c = sum(1 for c in all_cats if _categoria_serie_c(c))
    # Premia filtros positivos e Série C; penaliza excesso de negação
    bias = n_geo_pos * 2 + n_serie_c * 3 - n_geo_neg
    return (
        len(familias),
        diversidade - mono_penalty + nome_bonus + len(subgrupos) + bias,
        tipos_eixo,
        dens_min,
    )


def _candidatos_eixo(
    rng: random.Random,
    pool: list[Categoria],
    eixo: list[Categoria],
    outro: list[Categoria],
    usados: set[str],
    *,
    cat_eh_linha: bool,
    memo: dict[tuple[str, str], int],
    limite: int = 36,
) -> list[Categoria]:
    """Candidatos válidos, ordenados por sorteio ponderado (UF+/Série C)."""
    validos: list[Categoria] = []
    # Varre o pool embaralhado para não enviesar só pelo início da lista
    opcoes = [c for c in pool if c.id not in usados]
    rng.shuffle(opcoes)
    for c in opcoes:
        if not _eixo_parcial_ok(eixo + [c]):
            continue
        if outro and not _candidato_encaixa_no_outro_eixo(
            c, outro, cat_eh_linha=cat_eh_linha, memo=memo
        ):
            continue
        validos.append(c)
        # Coleta um pouco além do limite para o peso ter efeito
        if len(validos) >= limite * 3:
            break
    return _amostra_ponderada(rng, validos, k=limite)


def _montar_board_sequencial(
    rng: random.Random,
    pool: list[Categoria],
    memo: dict[tuple[str, str], int],
    *,
    tentativas_folha: int = 6,
) -> tuple[list[Categoria], list[Categoria], list[list[int]]] | None:
    """Monta linhas/colunas uma a uma com re-roll e retrocesso por solubilidade.

    Ordem: L0 → C0 (célula) → C1 → C2 → L1 → L2, validando cada cruzamento
    assim que ambos os eixos têm a categoria correspondente.
    """
    rows: list[Categoria] = []
    cols: list[Categoria] = []
    usados: set[str] = set()

    # Sequência de passos: ("row"|"col", índice_alvo)
    passos: list[tuple[str, int]] = [
        ("row", 0),
        ("col", 0),
        ("col", 1),
        ("col", 2),
        ("row", 1),
        ("row", 2),
    ]

    def dfs(passo_i: int) -> tuple[list[Categoria], list[Categoria], list[list[int]]] | None:
        if passo_i >= len(passos):
            return _tentar_board(rows, cols, memo)

        kind, _idx = passos[passo_i]
        if kind == "row":
            cands = _candidatos_eixo(
                rng,
                pool,
                rows,
                cols,
                usados,
                cat_eh_linha=True,
                memo=memo,
                limite=24,
            )
            eixo = rows
        else:
            cands = _candidatos_eixo(
                rng,
                pool,
                cols,
                rows,
                usados,
                cat_eh_linha=False,
                memo=memo,
                limite=24,
            )
            eixo = cols

        if not cands:
            return None

        # Limita ramificação: tenta um subconjunto aleatório já embaralhado
        for cat in cands[:tentativas_folha]:
            eixo.append(cat)
            usados.add(cat.id)
            achou = dfs(passo_i + 1)
            if achou is not None:
                return achou
            eixo.pop()
            usados.discard(cat.id)
        return None

    return dfs(0)


def _gerar_puzzle_variado(dia_s: str) -> dict[str, Any]:
    """Gerador v5: sorteio sequencial + solubilidade + ≤1 subgrupo por eixo."""
    cats = list(categorias_disponiveis(dia_s))
    if len(cats) < GRID_SIZE * 2:
        raise RuntimeError("catálogo insuficiente para o grid")

    rng = _rng_dia(dia_s)
    memo: dict[tuple[str, str], int] = {}

    melhor: dict[str, Any] | None = None
    melhor_score: tuple[int, int, int, int] | None = None
    tentativas_ok = 0
    orcamento = 28

    for _ in range(orcamento * 2):
        board = _montar_board_sequencial(rng, cats, memo)
        if not board:
            continue
        r, c, dens = board
        if not _board_diverso(r, c):
            continue
        if len({x.tipo for x in r + c}) < 4:
            continue
        score = _score_variedade(r, c, dens)
        tentativas_ok += 1
        if melhor_score is None or score > melhor_score:
            melhor_score = score
            melhor = {
                "dia": dia_s,
                "linhas": [x.to_public() for x in r],
                "colunas": [x.to_public() for x in c],
                "densidades": dens,
                "tamanho": GRID_SIZE,
            }
        # Bom o bastante: famílias ≥3 e subgrupos bem espalhados
        if score[0] >= 3 and score[1] >= 10 and tentativas_ok >= 2:
            return melhor
        if tentativas_ok >= 8 and melhor is not None:
            return melhor
        if tentativas_ok >= orcamento and melhor is not None:
            return melhor

    if melhor is not None:
        return melhor

    # Fallback: templates por tipo (ainda com filtro de subgrupo via _eixo_diverso)
    by_tipo: dict[str, list[Categoria]] = {}
    for c in cats:
        by_tipo.setdefault(c.tipo, []).append(c)
        rng.shuffle(by_tipo[c.tipo])

    templates: list[tuple[tuple[str, ...] | None, tuple[str, ...] | None]] = [
        (None, None),
        (_TIPOS_GEO, None),
        (None, _TIPOS_GEO),
        (tuple(_TIPOS_HISTORICOS), _TIPOS_GEO),
        (_TIPOS_GEO, tuple(_TIPOS_HISTORICOS)),
        (None, tuple(_TIPOS_HISTORICOS)),
        (tuple(_TIPOS_HISTORICOS), None),
        (_TIPOS_GEO + _TIPOS_NOME, None),
        (None, _TIPOS_GEO + _TIPOS_NOME),
        (tuple(_TIPOS_HISTORICOS) + _TIPOS_NOME, _TIPOS_GEO),
        (_TIPOS_GEO, tuple(_TIPOS_HISTORICOS) + _TIPOS_NOME),
    ]
    rng.shuffle(templates)

    for left_pref, right_pref in templates:
        left_opts = _opcoes_eixo_livre(
            rng, by_tipo, limite=20, tipos_preferidos=left_pref
        )
        if not left_opts and left_pref is not None:
            left_opts = _opcoes_eixo_livre(rng, by_tipo, limite=20, tipos_preferidos=None)
        right_opts = _opcoes_eixo_livre(
            rng, by_tipo, limite=20, tipos_preferidos=right_pref
        )
        if not right_opts and right_pref is not None:
            right_opts = _opcoes_eixo_livre(
                rng, by_tipo, limite=20, tipos_preferidos=None
            )
        rng.shuffle(left_opts)
        rng.shuffle(right_opts)
        for rows in left_opts:
            for cols in right_opts:
                if not _board_diverso(rows, cols):
                    continue
                board = _tentar_board(rows, cols, memo)
                if not board:
                    continue
                r, c, dens = board
                if len({x.tipo for x in r + c}) < 4:
                    continue
                score = _score_variedade(r, c, dens)
                tentativas_ok += 1
                if melhor_score is None or score > melhor_score:
                    melhor_score = score
                    melhor = {
                        "dia": dia_s,
                        "linhas": [x.to_public() for x in r],
                        "colunas": [x.to_public() for x in c],
                        "densidades": dens,
                        "tamanho": GRID_SIZE,
                    }
                if tentativas_ok >= 12 and melhor is not None:
                    return melhor

    if melhor is not None:
        return melhor
    raise RuntimeError(f"não foi possível gerar grid variado para {dia_s}")


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


def categoria_por_id(cat_id: str, dia: str | None = None) -> Categoria | None:
    for c in categorias_disponiveis(dia):
        if c.id == cat_id:
            return c
    # Fallback: categorias históricas podem ser resolvidas mesmo se o dia
    # corrente ainda estiver no pool clássico (útil em testes pontuais).
    for c in categorias_disponiveis(GRID_HISTORICO_DESDE):
        if c.id == cat_id:
            return c
    return None


def puzzle_publico(dia: str | None = None) -> dict[str, Any]:
    p = gerar_puzzle(dia)
    dia_s = p["dia"]
    h, mi = get_virada_hm()
    return {
        **p,
        "rotulo": rotulo_dia(dia_s),
        "virada_em_ms": ms_ate_proxima_virada(),
        "virada_hora": h,
        "virada_minuto": mi,
        "virada_rotulo": rotulo_hora_virada(h, mi),
        "tz": "America/Sao_Paulo",
        "regenerado": bool(_salt_dia(dia_s)),
    }


def nome_core_norm(nome_norm: str) -> str:
    """Nome sem sufixo '(UF)' — base do limiar de sugestão."""
    return _UF_SUFFIX_RE.sub("", (nome_norm or "").strip()).strip()


# Prefixos jurídicos no início (token + espaço). RB/XV são parte do nome.
_PREFIXOS_JURIDICOS = frozenset(
    {
        "fc",
        "sc",
        "ec",
        "ac",
        "aa",
        "ca",
        "ce",
        "se",
        "ad",
        "ae",
        "af",
        "ag",
        "ge",
        "cr",
        "cs",
        "cd",
        "ff",
        "oc",
        "ua",
    }
)
_PREFIXOS_IDENTIDADE = frozenset({"rb", "xv"})


def nome_sem_prefixo_juridico(nome_norm: str) -> str:
    """Remove FC/SC/EC/… do início; mantém RB, XV e nomes sem prefixo."""
    core = nome_core_norm(nome_norm)
    parts = core.split()
    if len(parts) < 2:
        return core
    head = parts[0]
    if head in _PREFIXOS_IDENTIDADE:
        return core
    if head in _PREFIXOS_JURIDICOS:
        rest = " ".join(parts[1:]).strip()
        return rest or core
    return core


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
    sig = clube.get("nome_sig") or nome_sem_prefixo_juridico(nome)
    if not (
        core.startswith(query)
        or sig.startswith(query)
        or nome.startswith(query)
        or query in core
        or query in sig
    ):
        return False
    # Limiar pelo nome completo (com FC/SC); o match pode ser pelo nome significativo.
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
    row = categoria_por_id(puzzle["linhas"][linha]["id"], dia)
    col = categoria_por_id(puzzle["colunas"][coluna]["id"], dia)
    if not row or not col:
        raise ValueError("categoria inválida")
    pool = pool_celula(row, col)
    total = len(pool)
    query = fold_txt(q or "")
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
    query = fold_txt(nome or "").strip()
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


def chute_nome_inexistente(
    *,
    linha: int,
    coluna: int,
    nome: str,
) -> dict[str, Any]:
    """Registra chute com texto fora do catálogo como erro (célula vermelha)."""
    if not (0 <= linha < GRID_SIZE and 0 <= coluna < GRID_SIZE):
        raise ValueError("célula inválida")
    rotulo = " ".join((nome or "").strip().split())
    if len(rotulo) < BUSCA_MIN_CHARS:
        raise ValueError(f"Digite pelo menos {BUSCA_MIN_CHARS} letras do nome")
    rotulo = rotulo[:80]
    return {
        "ok": False,
        "clube": {
            "id": "",
            "nome": rotulo,
            "uf": "",
            "emblema": "",
        },
        "linha": linha,
        "coluna": coluna,
        "inventado": True,
    }


def clube_ja_usado_no_grid(
    celulas: list[list[dict[str, Any] | None]],
    clube_id: str,
) -> bool:
    """True se o clube já aparece em alguma célula (acerto ou erro).

    Estilo HoopsGrid: cada time só pode ser usado uma vez no tabuleiro.
    """
    cid = str(clube_id or "").strip()
    if not cid:
        return False
    for r in range(GRID_SIZE):
        for c in range(GRID_SIZE):
            cell = celulas[r][c] if r < len(celulas) and c < len(celulas[r]) else None
            if not cell:
                continue
            clube = cell.get("clube") if isinstance(cell, dict) else None
            if isinstance(clube, dict) and str(clube.get("id") or "").strip() == cid:
                return True
    return False


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
    row = categoria_por_id(puzzle["linhas"][linha]["id"], dia)
    col = categoria_por_id(puzzle["colunas"][coluna]["id"], dia)
    if not row or not col:
        raise ValueError("categoria inválida")
    clube = clubes_por_id().get(clube_id)
    if not clube:
        raise ValueError("clube inválido")
    ok = clube_bate_categoria(clube, row) and clube_bate_categoria(clube, col)
    rep = int(clube.get("rep") or 0)
    return {
        "ok": ok,
        "clube": {
            "id": clube["id"],
            "nome": clube["nome"],
            "uf": clube["uf"],
            "emblema": clube["emblema"],
            "rep": rep,
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
