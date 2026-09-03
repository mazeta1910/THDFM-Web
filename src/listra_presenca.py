"""Presença leve na página da Listra (evita dois editores colidirem)."""

from __future__ import annotations

import threading
import time
from typing import Any

_TTL_SEC = 45.0
_lock = threading.Lock()
# chave -> {nome, visto_em}
_sessoes: dict[str, dict[str, Any]] = {}


def _expirar(agora: float) -> None:
    mortos = [
        chave
        for chave, info in _sessoes.items()
        if agora - float(info.get("visto_em") or 0) > _TTL_SEC
    ]
    for chave in mortos:
        _sessoes.pop(chave, None)


def ping(chave: str, nome: str) -> list[dict[str, str]]:
    """Registra presença e devolve os outros ainda online."""
    chave_ok = (chave or "").strip()
    nome_ok = (nome or "").strip() or "Alguém"
    if not chave_ok:
        return []
    agora = time.time()
    with _lock:
        _expirar(agora)
        _sessoes[chave_ok] = {"nome": nome_ok, "visto_em": agora}
        outros = [
            {"chave": k, "nome": str(v.get("nome") or "Alguém")}
            for k, v in _sessoes.items()
            if k != chave_ok
        ]
    outros.sort(key=lambda x: x["nome"].casefold())
    return outros


def limpar() -> None:
    """Utilitário de teste."""
    with _lock:
        _sessoes.clear()
