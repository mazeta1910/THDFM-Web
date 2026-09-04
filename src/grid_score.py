"""Pontuação do THDFM Grid (Raiz / Xonha) — funções puras.

Score de partida = acertos + bônus completo + tempo + raridade (Rep)
               − custos de dicas.
Score de ranking = soma das partidas do modo + bônus de streak.

No Contínuo, só a primeira partida de cada dia entra no ranking;
as demais (2ª/3ª) são só diversão (pontos locais, sem ranking).
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

# --- constantes (ajustáveis sem mudar a API) ---
P_ACERTO = 100
P_COMPLETO = 250
P_TEMPO_POR_S = 1
TEMPO_TETO_S = 600  # bônus zera a partir de 10 min
P_STREAK_DIA = 50

CUSTO_CONTAGEM = 10
MATRIZ_BASE = 80  # 1ª matriz: 80; 2ª: 160; 3ª: 320; …


def custo_dica_contagem() -> int:
    return CUSTO_CONTAGEM


def custo_dica_matriz(usos_anteriores: int) -> int:
    """Custo da próxima matriz na partida (exponencial).

    ``usos_anteriores`` = quantas matrizes já foram abertas (0 → primeira).
    """
    n = max(0, int(usos_anteriores))
    return int(MATRIZ_BASE * (2**n))


def bonus_tempo(tempo_segundos: int | None, *, finalizado: bool) -> int:
    if not finalizado or tempo_segundos is None:
        return 0
    t = max(0, int(tempo_segundos))
    return max(0, TEMPO_TETO_S - t) * P_TEMPO_POR_S


def _celulas_iter(celulas: Any) -> Iterable[Mapping[str, Any]]:
    if not isinstance(celulas, list):
        return
    for row in celulas:
        if not isinstance(row, list):
            continue
        for cell in row:
            if isinstance(cell, dict):
                yield cell


def contar_acertos(celulas: Any) -> tuple[int, int]:
    """Devolve (ok, preenchidas)."""
    ok = 0
    filled = 0
    for cell in _celulas_iter(celulas):
        if not cell.get("clube"):
            continue
        filled += 1
        if cell.get("ok"):
            ok += 1
    return ok, filled


def pontos_rep_celulas(celulas: Any) -> int:
    """Soma pontos_rep_desempate das células corretas."""
    from src.clubes_catalogo import pontos_rep_desempate

    total = 0
    for cell in _celulas_iter(celulas):
        if not cell.get("ok") or not cell.get("clube"):
            continue
        clube = cell.get("clube")
        rep = 0
        if isinstance(clube, dict) and clube.get("rep") is not None:
            try:
                rep = max(0, int(clube.get("rep") or 0))
            except (TypeError, ValueError):
                rep = 0
        total += pontos_rep_desempate(rep)
    return total


def custo_dicas(dicas: Sequence[Mapping[str, Any]] | None) -> int:
    """Soma custos já gravados em dicas_json (campo ``custo``)."""
    if not dicas:
        return 0
    total = 0
    for d in dicas:
        if not isinstance(d, Mapping):
            continue
        try:
            total += max(0, int(d.get("custo") or 0))
        except (TypeError, ValueError):
            continue
    return total


def pontos_partida(
    celulas: Any,
    *,
    finalizado: bool = False,
    interrompido: bool = False,
    tempo_segundos: int | None = None,
    dicas: Sequence[Mapping[str, Any]] | None = None,
) -> int:
    """Pontuação de uma partida (número único, ≥ 0)."""
    ok, _filled = contar_acertos(celulas)
    pts = ok * P_ACERTO
    if finalizado and not interrompido:
        pts += P_COMPLETO
        pts += bonus_tempo(tempo_segundos, finalizado=True)
    pts += pontos_rep_celulas(celulas)
    pts -= custo_dicas(dicas)
    return max(0, int(pts))


def score_ranking(
    pontos_partidas: Iterable[int],
    *,
    streak: int = 0,
) -> int:
    """Score agregado do modo: soma das partidas + bônus de streak."""
    base = sum(max(0, int(p)) for p in pontos_partidas)
    return base + P_STREAK_DIA * max(0, int(streak))
