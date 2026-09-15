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
