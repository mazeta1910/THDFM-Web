from __future__ import annotations

from dataclasses import dataclass

from src.models import TETO_FIDELIDADE


@dataclass
class FidelidadeDetalhe:
    f_gols_casa: float
    f_gols_fora: float
    f_vencedor: float
    indice: float
    teto: int
    bonus: int
    previsto_casa: int
    real_casa: int
    previsto_fora: int
    real_fora: int
    acertos_vencedor: int
    jogos: int


def fidelidade_eixo(previsto: int, real: int) -> float:
    return max(0.0, 1.0 - abs(previsto - real) / max(real, 1))


def calcular_fidelidade(
    *,
    previsto_casa: int,
    real_casa: int,
    previsto_fora: int,
    real_fora: int,
    acertos_vencedor: int,
    jogos: int,
    fase: str,
) -> FidelidadeDetalhe:
    f1 = fidelidade_eixo(previsto_casa, real_casa)
    f2 = fidelidade_eixo(previsto_fora, real_fora)
    f3 = fidelidade_eixo(acertos_vencedor, jogos) if jogos else 0.0
    indice = (f1 + f2 + f3) / 3.0 if jogos else 0.0
    teto = TETO_FIDELIDADE.get(fase, 5)
    bonus = int(round(indice * teto))
    return FidelidadeDetalhe(
        f_gols_casa=f1,
        f_gols_fora=f2,
        f_vencedor=f3,
        indice=indice,
        teto=teto,
        bonus=bonus,
        previsto_casa=previsto_casa,
        real_casa=real_casa,
        previsto_fora=previsto_fora,
        real_fora=real_fora,
        acertos_vencedor=acertos_vencedor,
        jogos=jogos,
    )
