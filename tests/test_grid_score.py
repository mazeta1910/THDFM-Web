"""Testes unitários da pontuação / dicas do Grid (Fase 1)."""

from __future__ import annotations

from src.clubes_catalogo import pontos_rep_desempate
from src.grid_score import (
    CUSTO_CONTAGEM,
    GRID_CELULAS,
    MATRIZ_BASE,
    P_ACERTO,
    P_COMPLETO,
    P_STREAK_DIA,
    RARIDADE_FATOR,
    TEMPO_TETO_S,
    bonus_raridade,
    bonus_tempo,
    contar_acertos,
    custo_dica_contagem,
    custo_dica_matriz,
    custo_dicas,
    media_raridade,
    pontos_partida,
    score_ranking,
)


def _cell(ok: bool, *, rep: int = 500, nome: str = "Clube") -> dict:
    return {"ok": ok, "clube": {"id": "1", "nome": nome, "rep": rep}}


def _board(reps: list[int | None]) -> list[list[dict | None]]:
    """Monta 3×3: int=acerto com aquele rep; None=vazio."""
    assert len(reps) == 9
    out: list[list[dict | None]] = []
    for i in range(3):
        row: list[dict | None] = []
        for j in range(3):
            r = reps[i * 3 + j]
            row.append(None if r is None else _cell(True, rep=int(r)))
        out.append(row)
    return out


def test_custo_contagem_fixo():
    assert custo_dica_contagem() == CUSTO_CONTAGEM == 10


def test_custo_matriz_linear_ilimitado():
    assert custo_dica_matriz(0) == 80
    assert custo_dica_matriz(1) == 160
    assert custo_dica_matriz(2) == 240
    assert custo_dica_matriz(3) == 320
    assert custo_dica_matriz(9) == 800
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


def test_bonus_raridade_media_vezes_indice():
    celulas = _board([200, 200, 200, None, None, None, None, None, None])
    media = media_raridade(celulas)
    assert media == float(pontos_rep_desempate(200))
    expected = int(round(media * (3 / GRID_CELULAS) * RARIDADE_FATOR))
    assert bonus_raridade(celulas) == expected
    assert expected > 0


def test_pontos_partida_acertos_e_completo():
    celulas = [[_cell(True, rep=500) for _ in range(3)] for _ in range(3)]
    pts = pontos_partida(celulas, finalizado=True, tempo_segundos=TEMPO_TETO_S)
    assert pts == 9 * P_ACERTO + P_COMPLETO + bonus_raridade(celulas)


def test_pontos_partida_interrompido_sem_bonus_completo_nem_tempo():
    celulas = [[_cell(True, rep=500), None, None], [None, None, None], [None, None, None]]
    pts = pontos_partida(
        celulas,
        finalizado=False,
        interrompido=True,
        tempo_segundos=30,
    )
    assert pts == P_ACERTO + bonus_raridade(celulas)


def test_pontos_partida_desconta_dicas_piso_zero():
    celulas = [[_cell(True, rep=7750), None, None], [None, None, None], [None, None, None]]
    dicas = [{"tipo": "matriz", "custo": custo_dica_matriz(0)}]
    pts = pontos_partida(celulas, dicas=dicas)
    assert pts == max(0, P_ACERTO + bonus_raridade(celulas) - 80)

    dicas_caras = [{"custo": 10_000}]
    assert pontos_partida([[_cell(True, rep=7750)]], dicas=dicas_caras) == 0


def test_raridade_7_ou_6_raros_podem_passar_8_safe():
    """6–7/9 com times obscuros podem superar 8/9 ‘safe’."""
    raro7 = _board([200] * 7 + [None, None])
    raro6 = _board([200] * 6 + [None, None, None])
    safe8 = _board([7750] * 8 + [None])
    kwargs = dict(finalizado=True, tempo_segundos=TEMPO_TETO_S)
    assert pontos_partida(raro7, **kwargs) > pontos_partida(safe8, **kwargs)
    assert pontos_partida(raro6, **kwargs) > pontos_partida(safe8, **kwargs)


def test_raridade_nao_faz_3_passar_6():
    """Déficit grande de acertos não é revertido só por Rep."""
    obscure3 = _board([200, 200, 200, None, None, None, None, None, None])
    famosos6 = _board([7750] * 6 + [None, None, None])
    kwargs = dict(finalizado=True, tempo_segundos=TEMPO_TETO_S)
    assert pontos_partida(famosos6, **kwargs) > pontos_partida(obscure3, **kwargs)


def test_score_ranking_soma_e_streak():
    assert score_ranking([100, 200], streak=3) == 300 + 3 * P_STREAK_DIA
    assert score_ranking([], streak=0) == 0
    assert score_ranking([-5, 10], streak=-1) == 10  # negativos ignorados na soma via max
