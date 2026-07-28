from __future__ import annotations

from src.db import (
    get_meta,
    list_confrontos_completos,
    list_participantes,
    load_snapshot,
    palpites_do_participante,
)
from src.fidelidade import FidelidadeDetalhe, calcular_fidelidade
from src.models import PontosParticipante
from src.scoring import (
    pontos_detalhados,
    quem_classifica_agregado,
    pesos_para_fase,
)


def _clube_nome(confronto: dict, clube_id: str) -> str:
    return confronto["clube_a"] if clube_id == "a" else confronto["clube_b"]


def _jogo_por_perna(confronto: dict, perna: str) -> dict | None:
    for j in confronto["jogos"]:
        if j["perna"] == perna:
            return j
    return None


def _acertou_vencedor_jogo(
    palpite_m: int,
    palpite_v: int,
    real_m: int,
    real_v: int,
    *,
    mandante_clube_id: str,
    palpite_pen: str | None,
    real_pen: str | None,
    permite_empate: bool,
) -> bool:
    from src.scoring import _acertou_vencedor

    return _acertou_vencedor(
        palpite_m,
        palpite_v,
        real_m,
        real_v,
        clube_casa_id=mandante_clube_id,
        palpite_penaltis=palpite_pen,
        real_penaltis=real_pen,
        permite_empate=permite_empate,
    )


def calcular_classificacao() -> list[dict]:
    fase = get_meta("fase_atual", "oitavas") or "oitavas"
    confrontos = list_confrontos_completos()
    participantes = [p for p in list_participantes() if p.get("status") == "liberado"]
    snapshot = load_snapshot() or {}
    baseline = snapshot.get("somas", {})

    linhas: list[dict] = []
    for p in participantes:
        pts = PontosParticipante(participante=p["nome"])
        palpites = palpites_do_participante(p["id"])
        prev_casa = prev_fora = real_casa = real_fora = 0
        acertos_venc = jogos_realizados = 0
        detalhe_fid: FidelidadeDetalhe | None = None

        for c in confrontos:
            ida = _jogo_por_perna(c, "ida")
            volta = _jogo_por_perna(c, "volta")
            if not ida or not volta:
                continue

            # Pontuar cada perna realizada (90 min — empate permitido)
            for jogo in (ida, volta):
                if jogo["gols_mandante"] is None or jogo["gols_visitante"] is None:
                    continue
                jogos_realizados += 1
                real_casa += jogo["gols_mandante"]
                real_fora += jogo["gols_visitante"]

                pj = palpites["jogos"].get(jogo["id"])
                if not pj:
                    continue
                prev_casa += pj["gols_mandante"]
                prev_fora += pj["gols_visitante"]

                pen_p = None
                pen_r = None
                # pênaltis só entram no desfecho agregado, não no 90 min da perna
                det = pontos_detalhados(
                    pj["gols_mandante"],
                    pj["gols_visitante"],
                    jogo["gols_mandante"],
                    jogo["gols_visitante"],
                    fase=fase,
                    clube_casa_id=jogo["mandante_clube_id"],
                    palpite_penaltis=None,
                    real_penaltis=None,
                    permite_empate=True,
                )
                pts.adicionar(det)
                if _acertou_vencedor_jogo(
                    pj["gols_mandante"],
                    pj["gols_visitante"],
                    jogo["gols_mandante"],
                    jogo["gols_visitante"],
                    mandante_clube_id=jogo["mandante_clube_id"],
                    palpite_pen=None,
                    real_pen=None,
                    permite_empate=True,
                ):
                    acertos_venc += 1

            # Desfecho agregado com pênaltis (estilo WC): 1x vencedor se aplicável
            if (
                ida["gols_mandante"] is not None
                and ida["gols_visitante"] is not None
                and volta["gols_mandante"] is not None
                and volta["gols_visitante"] is not None
            ):
                real_cls = quem_classifica_agregado(
                    ida["gols_mandante"],
                    ida["gols_visitante"],
                    volta["gols_mandante"],
                    volta["gols_visitante"],
                    penaltis_clube_id=volta.get("penaltis_clube_id"),
                )
                # só pontos extras de "quem passou" quando foi a pênaltis
                ida_a, ida_b = ida["gols_mandante"], ida["gols_visitante"]
                agg_empate = (ida_a + volta["gols_visitante"]) == (
                    ida_b + volta["gols_mandante"]
                )
                if agg_empate and real_cls in ("a", "b"):
                    pj_ida = palpites["jogos"].get(ida["id"])
                    pj_volta = palpites["jogos"].get(volta["id"])
                    pen_palpite = palpites["penaltis"].get(c["id"], {}).get(
                        "penaltis_clube_id"
                    )
                    if pj_ida and pj_volta:
                        palpite_cls = quem_classifica_agregado(
                            pj_ida["gols_mandante"],
                            pj_ida["gols_visitante"],
                            pj_volta["gols_mandante"],
                            pj_volta["gols_visitante"],
                            penaltis_clube_id=pen_palpite,
                        )
                        if palpite_cls == real_cls:
                            pesos = pesos_para_fase(fase)
                            # evita pontuar vencedor duas vezes se já veio do placar de perna
                            # aqui é o desfecho do confronto via pênaltis
                            pts.vencedor += pesos.vencedor

        if jogos_realizados:
            detalhe_fid = calcular_fidelidade(
                previsto_casa=prev_casa,
                real_casa=real_casa,
                previsto_fora=prev_fora,
                real_fora=real_fora,
                acertos_vencedor=acertos_venc,
                jogos=jogos_realizados,
                fase=fase,
            )
            pts.fidelidade = detalhe_fid.bonus
            pts.indice_fidelidade = detalhe_fid.indice

        soma_base = baseline.get(p["nome"], 0)
        rod = pts.soma - soma_base
        linhas.append(
            {
                "participante": p["nome"],
                "placar": pts.placar,
                "vencedor": pts.vencedor,
                "gols_casa": pts.gols_casa,
                "gols_fora": pts.gols_fora,
                "gols": pts.gols_casa + pts.gols_fora,
                "fidelidade": pts.fidelidade,
                "indice_fidelidade": pts.indice_fidelidade,
                "fidelidade_detalhe": detalhe_fid,
                "soma": pts.soma,
                "rod": rod,
            }
        )

    linhas.sort(
        key=lambda r: (-r["soma"], -r["indice_fidelidade"], r["participante"].lower())
    )
    for i, row in enumerate(linhas, start=1):
        row["posicao"] = i
    return linhas


def snapshot_atual() -> dict:
    linhas = calcular_classificacao()
    return {
        "somas": {r["participante"]: r["soma"] for r in linhas},
    }
