"""Pontuação do THDFM Grid (Raiz / Xonha) — funções puras.

Score de partida = acertos + bônus completo + tempo + raridade − dicas.
Score de ranking = soma das partidas do modo + bônus de streak.

Raridade = média(pontos_rep das células corretas) × (acertos / 9) × fator.
Assim times raros pesam no score, mas um déficit grande de acertos
(ex.: 3 vs 6) não é revertido só por Rep; um déficit pequeno
(6–7 vs 8 “safe”) pode ser.

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

# média(rep) × (ok/GRID) × fator — calibração: 6–7 raros podem passar 8 safe;
# 3 raros não passam 6 safe.
RARIDADE_FATOR = 0.045
GRID_CELULAS = 9


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


def _reps_corretas(celulas: Any) -> list[int]:
    """pontos_rep_desempate de cada célula correta."""
    from src.clubes_catalogo import pontos_rep_desempate

    out: list[int] = []
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
        out.append(pontos_rep_desempate(rep))
    return out


def pontos_rep_celulas(celulas: Any) -> int:
    """Soma bruta de pontos_rep (desempate / métricas)."""
    return int(sum(_reps_corretas(celulas)))


def media_raridade(celulas: Any) -> float:
    """Média dos pontos_rep das células corretas (0 se nenhuma)."""
    reps = _reps_corretas(celulas)
    if not reps:
        return 0.0
    return float(sum(reps)) / len(reps)


def bonus_raridade(celulas: Any) -> int:
    """Média de raridade × índice de acertos × fator.

    ``indice`` = acertos / 9. Quanto mais casas certas *e* mais raros os
    times, maior o bônus — sem deixar um board quase vazio superar um
    board bem preenchido.
    """
    reps = _reps_corretas(celulas)
    ok = len(reps)
    if ok <= 0:
        return 0
    media = float(sum(reps)) / ok
    indice = ok / float(GRID_CELULAS)
    return int(round(media * indice * RARIDADE_FATOR))


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
    pts += bonus_raridade(celulas)
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
