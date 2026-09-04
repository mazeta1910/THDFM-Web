"""Ciclo de vida das partidas do Grid (Raiz / Xonha) — lógica de serviço."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from src import db
from src.grid_score import pontos_partida

TZ_SP = ZoneInfo("America/Sao_Paulo")


def agora_iso() -> str:
    return datetime.now(TZ_SP).replace(microsecond=0).isoformat()


def tempo_decorrido_s(iniciado_em: str | None, *, ate: str | None = None) -> int | None:
    if not iniciado_em:
        return None
    try:
        ini = datetime.fromisoformat(str(iniciado_em))
    except ValueError:
        return None
    if ini.tzinfo is None:
        ini = ini.replace(tzinfo=TZ_SP)
    if ate:
        try:
            fim = datetime.fromisoformat(str(ate))
        except ValueError:
            fim = datetime.now(TZ_SP)
    else:
        fim = datetime.now(TZ_SP)
    if fim.tzinfo is None:
        fim = fim.replace(tzinfo=TZ_SP)
    return max(0, int((fim - ini).total_seconds()))


def _recalcular_pontos(partida: dict[str, Any]) -> int:
    return pontos_partida(
        partida.get("celulas"),
        finalizado=bool(partida.get("finalizado")),
        interrompido=bool(partida.get("interrompido")),
        tempo_segundos=partida.get("tempo_segundos"),
        dicas=partida.get("dicas") or [],
    )


def iniciar_raiz(participante_id: int, dia: str) -> dict[str, Any]:
    """Idempotente: devolve a partida Raiz do dia ou cria uma nova."""
    existing = db.get_grid_partida_raiz(participante_id, dia)
    if existing:
        return existing
    now = agora_iso()
    return db.criar_grid_partida(
        participante_id,
        dia,
        modo="raiz",
        puzzle_salt="",
        iniciado_em=now,
    )


def interromper_partida(partida_id: int, *, participante_id: int) -> dict[str, Any]:
    part = db.get_grid_partida(partida_id)
    if not part or int(part["participante_id"]) != int(participante_id):
        raise LookupError("partida não encontrada")
    if part["modo"] != "raiz":
        raise ValueError("só o modo Raiz interrompe ao sair")
    if part.get("finalizado") or part.get("interrompido"):
        return part
    now = agora_iso()
    tempo = tempo_decorrido_s(part.get("iniciado_em"), ate=now)
    part = db.atualizar_grid_partida(
        partida_id,
        interrompido=True,
        encerrado_em=now,
        tempo_segundos=tempo,
    )
    pts = _recalcular_pontos(part)
    part = db.atualizar_grid_partida(partida_id, pontos=pts)
    # Espelha no progresso legado (ranking antigo) até a Fase 6.
    db.salvar_grid_progresso(
        participante_id,
        part["dia"],
        part.get("celulas") or [],
        finalizado=False,
    )
    return part


def aplicar_chute_partida(
    partida_id: int,
    *,
    participante_id: int,
    linha: int,
    coluna: int,
    resultado: dict[str, Any],
) -> dict[str, Any]:
    """Grava chute numa partida; levanta ValueError/LookupError/PermissionError."""
    from src.grid_game import celulas_completas, parse_celulas_progresso

    part = db.get_grid_partida(partida_id)
    if not part or int(part["participante_id"]) != int(participante_id):
        raise LookupError("partida não encontrada")
    if part.get("interrompido"):
        raise PermissionError("tentativa encerrada — células vazias bloqueadas")
    if part.get("finalizado"):
        raise PermissionError("partida já finalizada")

    celulas = parse_celulas_progresso(part.get("celulas"))
    if celulas[linha][coluna] is not None:
        raise ValueError("Célula já jogada")

    celulas[linha][coluna] = {
        "ok": resultado["ok"],
        "clube": resultado["clube"],
    }
    finalizado = celulas_completas(celulas)
    now = agora_iso()
    encerrado = now if finalizado else None
    tempo = tempo_decorrido_s(part.get("iniciado_em"), ate=now) if finalizado else None
    part = db.atualizar_grid_partida(
        partida_id,
        celulas=celulas,
        finalizado=finalizado,
        encerrado_em=encerrado,
        tempo_segundos=tempo if finalizado else part.get("tempo_segundos"),
    )
    pts = _recalcular_pontos(part)
    part = db.atualizar_grid_partida(partida_id, pontos=pts)
    if part["modo"] == "raiz":
        db.salvar_grid_progresso(
            participante_id,
            part["dia"],
            celulas,
            finalizado=finalizado,
        )
    return part
