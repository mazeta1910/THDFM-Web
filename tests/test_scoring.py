from src.fidelidade import calcular_fidelidade
from src.scoring import (
    agregado_empatado,
    pontos_detalhados,
    quem_classifica_agregado,
)


def test_placar_exato_oitavas():
    pts = pontos_detalhados(2, 1, 2, 1, fase="oitavas", permite_empate=True)
    assert pts.placar == 10
    assert pts.vencedor == 7
    assert pts.total == 17


def test_so_vencedor():
    pts = pontos_detalhados(3, 0, 2, 1, fase="oitavas", permite_empate=True)
    assert pts.placar == 0
    assert pts.vencedor == 7


def test_gols_casa():
    pts = pontos_detalhados(1, 0, 1, 2, fase="oitavas", permite_empate=True)
    assert pts.gols_casa == 5
    assert pts.vencedor == 0


def test_agregado_e_penaltis():
    assert agregado_empatado(1, 0, 1, 0) is True  # 1-0 ida, 1-0 volta -> 1-1
    assert quem_classifica_agregado(1, 0, 1, 0, penaltis_clube_id="a") == "a"
    assert quem_classifica_agregado(2, 0, 0, 0) == "a"


def test_fidelidade_teto():
    d = calcular_fidelidade(
        previsto_casa=12,
        real_casa=12,
        previsto_fora=9,
        real_fora=9,
        acertos_vencedor=8,
        jogos=8,
        fase="oitavas",
    )
    assert d.indice == 1.0
    assert d.bonus == 5
