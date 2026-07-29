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
                        # Seu agregado: se empatou usa pênaltis; senão o líder do agregado
                        # é o "time dos pênaltis" implícito (como na Copa de um jogo).
                        palpite_cls = quem_classifica_agregado(
                            pj_ida["gols_mandante"],
                            pj_ida["gols_visitante"],
                            pj_volta["gols_mandante"],
                            pj_volta["gols_visitante"],
                            penaltis_clube_id=pen_palpite,
                        )
                        if palpite_cls == real_cls:
                            pesos = pesos_para_fase(fase)
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
                "participante_id": p["id"],
                "participante": p["nome"],
                "avatar_path": p.get("avatar_path"),
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
    total = len(linhas)
    posicoes_ant = snapshot.get("posicoes") or {}
    for i, row in enumerate(linhas, start=1):
        row["posicao"] = i
        row["zona"] = _zona_classificacao(i, total)
        prev = posicoes_ant.get(row["participante"])
        if prev is None:
            row["movimento"] = None
        else:
            row["movimento"] = prev - i
    return linhas


def faixa_zonas(total: int) -> int:
    """Tamanho da faixa top/risco: regra de 3 com Brasileirão (4 em 20)."""
    if total <= 0:
        return 0
    faixa = max(1, round(total * 4 / 20))
    if faixa * 2 >= total and total >= 3:
        faixa = max(1, total // 5) or 1
    return faixa


def _zona_classificacao(posicao: int, total: int) -> str:
    """Zonas hipotéticas por regra de 3 com o Brasileirão (20 clubes).

    No exemplo: top 4/20 (20%) e rebaixamento 4/20 (20%).
    O 1º é sempre o campeão (amarelo); o restante da faixa do topo fica verde.
    """
    if total <= 0:
        return ""
    faixa = faixa_zonas(total)
    if posicao == 1:
        return "campeao"
    if posicao <= faixa:
        return "podio"
    if posicao > total - faixa:
        return "risco"
    return "meio"


def snapshot_atual(linhas: list[dict] | None = None) -> dict:
    rows = linhas if linhas is not None else calcular_classificacao()
    return {
        "somas": {r["participante"]: r["soma"] for r in rows},
        "posicoes": {r["participante"]: r["posicao"] for r in rows},
    }


_HIST_KEYS = (
    "participante_id",
    "participante",
    "avatar_path",
    "placar",
    "vencedor",
    "gols_casa",
    "gols_fora",
    "fidelidade",
    "soma",
    "rod",
    "posicao",
    "zona",
    "movimento",
)


def serializar_linhas_historico(linhas: list[dict]) -> list[dict]:
    return [{k: r.get(k) for k in _HIST_KEYS} for r in linhas]


def confirmar_rodada() -> dict:
    """Arquiva a tabela atual e atualiza o baseline da próxima rodada."""
    from src.db import append_rodada_historico, get_janela, get_meta, save_snapshot

    linhas = calcular_classificacao()
    hist = append_rodada_historico(
        linhas=serializar_linhas_historico(linhas),
        fase=get_meta("fase_atual", "oitavas") or "oitavas",
        janela=get_janela(),
    )
    save_snapshot(snapshot_atual(linhas))
    return hist


def desfazer_ultima_rodada() -> dict:
    """Remove a última rodada confirmada e restaura o baseline anterior."""
    from src.db import (
        clear_snapshot,
        delete_rodada_historico,
        get_ultima_rodada_historico,
        list_rodadas_historico,
        save_snapshot,
    )

    ultima = get_ultima_rodada_historico()
    if not ultima:
        raise ValueError("Nenhuma rodada confirmada para desfazer")

    if not delete_rodada_historico(int(ultima["id"])):
        raise ValueError("Não foi possível remover a rodada")

    restantes = list_rodadas_historico()
    if restantes:
        anterior = get_ultima_rodada_historico()
        if anterior and anterior.get("linhas"):
            save_snapshot(snapshot_atual(anterior["linhas"]))
        else:
            clear_snapshot()
    else:
        clear_snapshot()

    return ultima
