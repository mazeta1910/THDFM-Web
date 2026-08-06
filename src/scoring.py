from __future__ import annotations

from src.models import PESOS_POR_FASE, PesosJogo, PontosJogo


def pesos_para_fase(fase: str) -> PesosJogo:
    return PESOS_POR_FASE.get(fase, PESOS_POR_FASE["oitavas"])


def vencedor_lado(gols_casa: int, gols_fora: int) -> str:
    if gols_casa > gols_fora:
        return "casa"
    if gols_casa < gols_fora:
        return "fora"
    return "empate"


def lado_por_clube(
    gols_casa: int,
    gols_fora: int,
    *,
    clube_casa_id: str,
    penaltis_clube_id: str | None,
    permite_empate: bool,
) -> str | None:
    """Quem 'passou' neste jogo: id do clube ('a'/'b'), 'empate', ou None."""
    if gols_casa > gols_fora:
        return clube_casa_id
    if gols_casa < gols_fora:
        return "b" if clube_casa_id == "a" else "a"
    
    # A CORREÇÃO ESTÁ AQUI: Pênaltis avaliados ANTES do empate
    if penaltis_clube_id in ("a", "b"):
        return penaltis_clube_id
        
    if permite_empate:
        return "empate"
        
    return None


def classificar_palpite(
    palpite_casa: int,
    palpite_fora: int,
    real_casa: int,
    real_fora: int,
    *,
    clube_casa_id: str,
    palpite_penaltis: str | None = None,
    real_penaltis: str | None = None,
    permite_empate: bool = True,
) -> tuple[str, bool]:
    if palpite_casa == real_casa and palpite_fora == real_fora:
        acertou_vencedor = True
        if not permite_empate and real_casa == real_fora:
            acertou_vencedor = _acertou_vencedor(
                palpite_casa,
                palpite_fora,
                real_casa,
                real_fora,
                clube_casa_id=clube_casa_id,
                palpite_penaltis=palpite_penaltis,
                real_penaltis=real_penaltis,
                permite_empate=permite_empate,
            )
        return "Placar", acertou_vencedor

    acertou_vencedor = _acertou_vencedor(
        palpite_casa,
        palpite_fora,
        real_casa,
        real_fora,
        clube_casa_id=clube_casa_id,
        palpite_penaltis=palpite_penaltis,
        real_penaltis=real_penaltis,
        permite_empate=permite_empate,
    )
    if palpite_casa == real_casa:
        return "Gols Casa", acertou_vencedor
    if palpite_fora == real_fora:
        return "Gols fora", acertou_vencedor
    return "Nada", acertou_vencedor


def _acertou_vencedor(
    palpite_casa: int,
    palpite_fora: int,
    real_casa: int,
    real_fora: int,
    *,
    clube_casa_id: str,
    palpite_penaltis: str | None,
    real_penaltis: str | None,
    permite_empate: bool,
) -> bool:
    lado_p = lado_por_clube(
        palpite_casa,
        palpite_fora,
        clube_casa_id=clube_casa_id,
        penaltis_clube_id=palpite_penaltis,
        permite_empate=permite_empate,
    )
    lado_r = lado_por_clube(
        real_casa,
        real_fora,
        clube_casa_id=clube_casa_id,
        penaltis_clube_id=real_penaltis,
        permite_empate=permite_empate,
    )
    return lado_p is not None and lado_p == lado_r


def pontos_detalhados(
    palpite_casa: int,
    palpite_fora: int,
    real_casa: int,
    real_fora: int,
    *,
    fase: str,
    clube_casa_id: str = "a",
    palpite_penaltis: str | None = None,
    real_penaltis: str | None = None,
    permite_empate: bool = True,
) -> PontosJogo:
    categoria, acertou_vencedor = classificar_palpite(
        palpite_casa,
        palpite_fora,
        real_casa,
        real_fora,
        clube_casa_id=clube_casa_id,
        palpite_penaltis=palpite_penaltis,
        real_penaltis=real_penaltis,
        permite_empate=permite_empate,
    )
    pesos = pesos_para_fase(fase)

    if categoria == "Placar":
        if acertou_vencedor:
            return PontosJogo(placar=pesos.placar, vencedor=pesos.vencedor)
        return PontosJogo(placar=pesos.placar)

    pts = PontosJogo()
    if acertou_vencedor:
        pts.vencedor = pesos.vencedor
    if categoria == "Gols Casa":
        pts.gols_casa = pesos.gols
    elif categoria == "Gols fora":
        pts.gols_fora = pesos.gols
    return pts


def agregado_empatado(
    ida_a: int,
    ida_b: int,
    volta_mandante: int,
    volta_visitante: int,
    *,
    volta_casa_e_clube_b: bool = True,
) -> bool:
    """Na volta o mandante é o clube b (segundo da chave)."""
    if volta_casa_e_clube_b:
        # ida: a mandante; volta: b mandante
        total_a = ida_a + volta_visitante
        total_b = ida_b + volta_mandante
    else:
        total_a = ida_a + volta_mandante
        total_b = ida_b + volta_visitante
    return total_a == total_b


def quem_classifica_agregado(
    ida_a: int,
    ida_b: int,
    volta_mandante: int,
    volta_visitante: int,
    *,
    penaltis_clube_id: str | None = None,
    volta_casa_e_clube_b: bool = True,
) -> str | None:
    if volta_casa_e_clube_b:
        total_a = ida_a + volta_visitante
        total_b = ida_b + volta_mandante
    else:
        total_a = ida_a + volta_mandante
        total_b = ida_b + volta_visitante
    if total_a > total_b:
        return "a"
    if total_b > total_a:
        return "b"
    if penaltis_clube_id in ("a", "b"):
        return penaltis_clube_id
    return None