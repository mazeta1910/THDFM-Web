"""Testes unitários da pontuação / dicas do Grid (Fase 1)."""

from __future__ import annotations

from src.clubes_catalogo import pontos_rep_desempate
from src.grid_score import (
    CUSTO_CONTAGEM,
    MATRIZ_BASE,
    P_ACERTO,
    P_COMPLETO,
    P_STREAK_DIA,
    TEMPO_TETO_S,
    bonus_tempo,
    contar_acertos,
    custo_dica_contagem,
    custo_dica_matriz,
    custo_dicas,
    pontos_partida,
    score_ranking,
)


def _cell(ok: bool, *, rep: int = 500, nome: str = "Clube") -> dict:
    return {"ok": ok, "clube": {"id": "1", "nome": nome, "rep": rep}}


def test_custo_contagem_fixo():
    assert custo_dica_contagem() == CUSTO_CONTAGEM == 10


def test_custo_matriz_exponencial():
    assert custo_dica_matriz(0) == 80
    assert custo_dica_matriz(1) == 160
    assert custo_dica_matriz(2) == 320
    assert custo_dica_matriz(3) == 640
    assert custo_dica_matriz(-1) == MATRIZ_BASE  # trata negativo como 0


def test_bonus_tempo_so_finalizado():
    assert bonus_tempo(100, finalizado=False) == 0
    assert bonus_tempo(None, finalizado=True) == 0
    assert bonus_tempo(0, finalizado=True) == TEMPO_TETO_S
    assert bonus_tempo(100, finalizado=True) == TEMPO_TETO_S - 100
    assert bonus_tempo(TEMPO_TETO_S, finalizado=True) == 0
    assert bonus_tempo(TEMPO_TETO_S + 50, finalizado=True) == 0


def test_contar_acertos():
    celulas = [
        [_cell(True), _cell(False), None],
        [None, {"clube": None}, _cell(True)],
        [None, None, None],
    ]
    ok, filled = contar_acertos(celulas)
    assert ok == 2
    assert filled == 3


def test_pontos_partida_acertos_e_completo():
    celulas = [[_cell(True) for _ in range(3)] for _ in range(3)]
    # 9 acertos + completo (sem tempo/rep extras além do rep de cada célula)
    base_rep = 9 * pontos_rep_desempate(500)
    pts = pontos_partida(celulas, finalizado=True, tempo_segundos=TEMPO_TETO_S)
    assert pts == 9 * P_ACERTO + P_COMPLETO + 0 + base_rep


def test_pontos_partida_interrompido_sem_bonus_completo_nem_tempo():
    celulas = [[_cell(True), None, None], [None, None, None], [None, None, None]]
    pts = pontos_partida(
        celulas,
        finalizado=False,
        interrompido=True,
        tempo_segundos=30,
    )
    assert pts == P_ACERTO + pontos_rep_desempate(500)


def test_pontos_partida_desconta_dicas_piso_zero():
    celulas = [[_cell(True, rep=7750), None, None], [None, None, None], [None, None, None]]
    dicas = [{"tipo": "matriz", "custo": custo_dica_matriz(0)}]
    pts = pontos_partida(celulas, dicas=dicas)
    # acerto + rep mínima (~1) − 80 → pode ir a 21 ou similar, não negativo
    assert pts == max(0, P_ACERTO + pontos_rep_desempate(7750) - 80)

    dicas_caras = [{"custo": 10_000}]
    assert pontos_partida([[_cell(True, rep=7750)]], dicas=dicas_caras) == 0


def test_score_ranking_soma_e_streak():
    assert score_ranking([100, 200], streak=3) == 300 + 3 * P_STREAK_DIA
    assert score_ranking([], streak=0) == 0
    assert score_ranking([-5, 10], streak=-1) == 10  # negativos ignorados na soma via max
