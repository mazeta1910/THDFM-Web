"""Placeholders de demonstração — limpeza (não cria mais demos automaticamente)."""

from __future__ import annotations

from src import db

DEMO_PREFIX = "Demo · "


def limpar_demo() -> int:
    """Remove participantes demo e a flag de seed. Retorna quantos apagou."""
    apagados = 0
    for p in list(db.list_participantes()):
        if (p.get("nome") or "").startswith(DEMO_PREFIX):
            db.apagar_participante(p["id"])
            apagados += 1
    if db.get_meta("demo_seeded"):
        db.set_meta("demo_seeded", "0")
    return apagados
