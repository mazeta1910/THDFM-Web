"""Importação do histórico WhatsApp para o Xonhômetro."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "xonhometro" / "eventos_import.json"

_TIPOS = frozenset({"saida", "volta", "banimento"})


def caminho_import_padrao() -> Path:
    return _DATA_PATH


def meta_eventos_import(path: Path | None = None) -> dict[str, Any]:
    """Só metadados do JSON (sem montar a lista de eventos).

    Usado no GET do admin — evita parsear ~1,5k itens só para mostrar
    a quantidade no card de importação.
    """
    arquivo = path or _DATA_PATH
    if not arquivo.is_file():
        raise FileNotFoundError(f"Arquivo de importação não encontrado: {arquivo}")
    raw = json.loads(arquivo.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("JSON inválido: esperado objeto.")
    eventos_raw = raw.get("eventos") or []
    qtd = len(eventos_raw) if isinstance(eventos_raw, list) else 0
    totais = raw.get("totais") if isinstance(raw.get("totais"), dict) else {}
    return {
        "gerado_em": raw.get("gerado_em"),
        "fonte": raw.get("fonte"),
        "versao": raw.get("versao"),
        "totais": totais or {},
        "arquivo": str(arquivo),
        "quantidade": qtd,
    }


def carregar_eventos_import(
    path: Path | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Lê o JSON de importação. Retorna (eventos, meta)."""
    arquivo = path or _DATA_PATH
    if not arquivo.is_file():
        raise FileNotFoundError(f"Arquivo de importação não encontrado: {arquivo}")
    raw = json.loads(arquivo.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or "eventos" not in raw:
        raise ValueError("JSON inválido: esperado objeto com chave 'eventos'.")
    eventos_raw = raw.get("eventos") or []
    if not isinstance(eventos_raw, list):
        raise ValueError("JSON inválido: 'eventos' deve ser uma lista.")

    eventos: list[dict[str, Any]] = []
    for item in eventos_raw:
        if not isinstance(item, dict):
            continue
        tipo = str(item.get("tipo") or "").strip().lower()
        data = str(item.get("data") or "").strip()[:10]
        if tipo not in _TIPOS or len(data) != 10:
            continue
        hora = str(item.get("hora") or "").strip() or None
        if hora and len(hora) >= 5:
            hora = hora[:5]
        else:
            hora = None
        motivo = str(item.get("motivo") or "").strip() or None
        if motivo and len(motivo) > 500:
            motivo = motivo[:500]
        origem = str(item.get("origem") or "").strip() or None
        eventos.append(
            {
                "tipo": tipo,
                "data": data,
                "hora": hora,
                "motivo": motivo,
                "origem": origem,
            }
        )

    meta = {
        "gerado_em": raw.get("gerado_em"),
        "fonte": raw.get("fonte"),
        "versao": raw.get("versao"),
        "totais": raw.get("totais") or {},
        "arquivo": str(arquivo),
        "quantidade": len(eventos),
    }
    return eventos, meta
