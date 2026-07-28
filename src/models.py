from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PesosJogo:
    placar: int
    vencedor: int
    gols: int


PESOS_POR_FASE: dict[str, PesosJogo] = {
    "oitavas": PesosJogo(placar=10, vencedor=7, gols=5),
    "quartas": PesosJogo(placar=14, vencedor=10, gols=7),
    "semis": PesosJogo(placar=18, vencedor=13, gols=9),
    "final": PesosJogo(placar=24, vencedor=17, gols=12),
}

TETO_FIDELIDADE: dict[str, int] = {
    "oitavas": 5,
    "quartas": 7,
    "semis": 9,
    "final": 12,
}


@dataclass
class PontosJogo:
    placar: int = 0
    vencedor: int = 0
    gols_casa: int = 0
    gols_fora: int = 0

    @property
    def total(self) -> int:
        return self.placar + self.vencedor + self.gols_casa + self.gols_fora


@dataclass
class PontosParticipante:
    participante: str
    placar: int = 0
    vencedor: int = 0
    gols_casa: int = 0
    gols_fora: int = 0
    fidelidade: int = 0
    indice_fidelidade: float = 0.0

    @property
    def soma_jogos(self) -> int:
        return self.placar + self.vencedor + self.gols_casa + self.gols_fora

    @property
    def soma(self) -> int:
        return self.soma_jogos + self.fidelidade

    def adicionar(self, pontos: PontosJogo) -> None:
        self.placar += pontos.placar
        self.vencedor += pontos.vencedor
        self.gols_casa += pontos.gols_casa
        self.gols_fora += pontos.gols_fora
