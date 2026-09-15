"""Acervo — fatos de futebol do site (fonte neutra; Grid é um consumidor).

MVP: clubes, competições e edições (campeão/vice; tabela completa depois).
"""

from __future__ import annotations

import re
import unicodedata

UFS_BR = frozenset(
    {
        "AC",
        "AL",
        "AP",
        "AM",
        "BA",
        "CE",
        "DF",
        "ES",
        "GO",
        "MA",
        "MT",
        "MS",
        "MG",
        "PA",
        "PB",
        "PR",
        "PE",
        "PI",
        "RJ",
        "RN",
        "RS",
        "RO",
        "RR",
        "SC",
        "SP",
        "SE",
        "TO",
    }
)

AMBITOS = frozenset({"nacional", "estadual", "internacional", "outro"})
COBERTURAS = frozenset({"vazia", "campeao_apenas", "parcial", "completa"})

# Tipos de fase de uma edição. Uma edição é uma sequência ordenada de fases.
FASE_TIPOS = frozenset({"pontos_corridos", "grupos", "mata_mata"})

# Formato de um confronto de mata-mata.
CONFRONTO_FORMATOS = frozenset({"jogo_unico", "ida_volta"})

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(texto: str) -> str:
    """Gera slug ASCII a partir do nome (ex.: 'Série A' → 'serie-a')."""
    s = unicodedata.normalize("NFKD", (texto or "").strip())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.casefold()
    s = _SLUG_RE.sub("-", s).strip("-")
    return s[:80]


def normalizar_nome(nome: str) -> str:
    n = " ".join((nome or "").strip().split())
    if not n:
        raise ValueError("Nome obrigatório.")
    if len(n) > 120:
        raise ValueError("Nome muito longo (máx. 120).")
    return n


def normalizar_uf(uf: str | None, *, obrigatorio: bool = False) -> str:
    u = (uf or "").strip().upper()
    if not u:
        if obrigatorio:
            raise ValueError("UF obrigatória.")
        return ""
    if u not in UFS_BR:
        raise ValueError(f"UF inválida: {u}")
    return u


def normalizar_ambito(ambito: str | None) -> str:
    a = (ambito or "nacional").strip().lower()
    if a not in AMBITOS:
        raise ValueError("Âmbito inválido.")
    return a


def normalizar_cobertura(cobertura: str | None) -> str:
    c = (cobertura or "vazia").strip().lower()
    if c not in COBERTURAS:
        raise ValueError("Cobertura inválida.")
    return c


def normalizar_ano(ano: int | str) -> int:
    try:
        a = int(ano)
    except (TypeError, ValueError) as exc:
        raise ValueError("Ano inválido.") from exc
    if a < 1860 or a > 2100:
        raise ValueError("Ano fora do intervalo (1860–2100).")
    return a


def normalizar_fm_unique_id(raw: str | None) -> str | None:
    s = (raw or "").strip()
    if not s:
        return None
    if len(s) > 32:
        raise ValueError("Unique ID FM muito longo.")
    return s


def normalizar_notas(notas: str | None) -> str:
    n = (notas or "").strip()
    if len(n) > 2000:
        raise ValueError("Notas muito longas (máx. 2000).")
    return n


def normalizar_texto_curto(
    valor: str | None, *, campo: str = "Campo", maxlen: int = 120
) -> str:
    """Colapsa espaços e limita o tamanho de um texto curto opcional."""
    v = " ".join((valor or "").strip().split())
    if len(v) > maxlen:
        raise ValueError(f"{campo} muito longo (máx. {maxlen}).")
    return v


# --- Pontuação de tabelas (pontos corridos) ------------------------------
# Critério padrão do futebol de pontos corridos.
PONTOS_VITORIA = 3
PONTOS_EMPATE = 1
PONTOS_DERROTA = 0


def calcular_derivados(
    v: int | None,
    e: int | None,
    d: int | None,
    gp: int | None,
    gc: int | None,
) -> tuple[int | None, int | None, int | None]:
    """Deriva (jogos, saldo de gols, pontos) a partir das estatísticas base.

    - J  = V + E + D
    - SG = GP - GC
    - Pts = 3·V + 1·E + 0·D
    Retorna ``None`` para cada métrica cujas entradas necessárias faltem.
    """
    tem_resultado = any(x is not None for x in (v, e, d))
    j = (v or 0) + (e or 0) + (d or 0) if tem_resultado else None
    pts = (
        PONTOS_VITORIA * (v or 0)
        + PONTOS_EMPATE * (e or 0)
        + PONTOS_DERROTA * (d or 0)
        if tem_resultado
        else None
    )
    sg = (gp - gc) if (gp is not None and gc is not None) else None
    return j, sg, pts


def normalizar_url(url: str | None) -> str:
    u = (url or "").strip()
    if len(u) > 500:
        raise ValueError("URL muito longa (máx. 500).")
    if u and not (u.startswith("http://") or u.startswith("https://")):
        raise ValueError("URL deve começar com http:// ou https://")
    return u


def rotulo_ambito(ambito: str) -> str:
    return {
        "nacional": "Nacional",
        "estadual": "Estadual",
        "internacional": "Internacional",
        "outro": "Outro",
    }.get(ambito, ambito)


def rotulo_cobertura(cobertura: str) -> str:
    return {
        "vazia": "Vazia",
        "campeao_apenas": "Só campeão",
        "parcial": "Parcial",
        "completa": "Completa",
    }.get(cobertura, cobertura)


def normalizar_fase_tipo(tipo: str | None) -> str:
    t = (tipo or "pontos_corridos").strip().lower()
    if t not in FASE_TIPOS:
        raise ValueError("Tipo de fase inválido.")
    return t


def normalizar_confronto_formato(formato: str | None) -> str:
    f = (formato or "jogo_unico").strip().lower()
    if f not in CONFRONTO_FORMATOS:
        raise ValueError("Formato de confronto inválido.")
    return f


def resolver_confronto(
    *,
    clube_a_id: int,
    clube_b_id: int,
    formato: str,
    gols_a_ida: int | None,
    gols_b_ida: int | None,
    gols_a_volta: int | None = None,
    gols_b_volta: int | None = None,
    gol_fora_de_casa: bool = False,
    tem_penaltis: bool = False,
    penaltis_a: int | None = None,
    penaltis_b: int | None = None,
) -> tuple[int | None, str | None]:
    """Deriva o vencedor de um confronto de mata-mata.

    Convenção de mando: no ida/volta, o clube A é mandante no jogo de ida e o
    clube B é mandante na volta. Logo, os gols "fora" de A são os da volta
    (``gols_a_volta``) e os de B são os da ida (``gols_b_ida``).

    Retorna ``(vencedor_clube_id, criterio)`` com ``criterio`` em
    ``{"agregado", "gol_fora", "penaltis"}`` — ou ``(None, None)`` quando não há
    dados suficientes para decidir.
    """
    fmt = normalizar_confronto_formato(formato)

    def _penaltis() -> tuple[int | None, str | None]:
        if tem_penaltis and penaltis_a is not None and penaltis_b is not None:
            if penaltis_a > penaltis_b:
                return clube_a_id, "penaltis"
            if penaltis_b > penaltis_a:
                return clube_b_id, "penaltis"
        return None, None

    if fmt == "jogo_unico":
        if gols_a_ida is None or gols_b_ida is None:
            return None, None
        if gols_a_ida > gols_b_ida:
            return clube_a_id, "agregado"
        if gols_b_ida > gols_a_ida:
            return clube_b_id, "agregado"
        return _penaltis()

    # ida_volta
    if None in (gols_a_ida, gols_b_ida, gols_a_volta, gols_b_volta):
        return None, None
    total_a = gols_a_ida + gols_a_volta  # type: ignore[operator]
    total_b = gols_b_ida + gols_b_volta  # type: ignore[operator]
    if total_a > total_b:
        return clube_a_id, "agregado"
    if total_b > total_a:
        return clube_b_id, "agregado"
    if gol_fora_de_casa:
        fora_a = gols_a_volta  # A jogou fora na volta
        fora_b = gols_b_ida  # B jogou fora na ida
        if fora_a > fora_b:  # type: ignore[operator]
            return clube_a_id, "gol_fora"
        if fora_b > fora_a:  # type: ignore[operator]
            return clube_b_id, "gol_fora"
    return _penaltis()


def rotulo_fase_tipo(tipo: str) -> str:
    return {
        "pontos_corridos": "Pontos corridos",
        "grupos": "Fase de grupos",
        "mata_mata": "Mata-mata",
    }.get(tipo, tipo)
