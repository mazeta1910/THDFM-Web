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
                    pj_volta = palpites["jogos"].get(volta["id"])
                    pen_palpite = palpites["penaltis"].get(c["id"], {}).get(
                        "penaltis_clube_id"
                    )
                    if pj_volta:
                        # Agregado do palpite = oficial da Ida + Volta do usuário.
                        # Se empatar, usa pênaltis; senão o líder é o implícito.
                        palpite_cls = quem_classifica_agregado(
                            ida["gols_mandante"],
                            ida["gols_visitante"],
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
    from src.db import append_rodada_historico, get_meta, save_snapshot

    linhas = calcular_classificacao()
    fase = get_meta("fase_atual", "oitavas") or "oitavas"
    hist = append_rodada_historico(
        linhas=serializar_linhas_historico(linhas),
        fase=fase,
        janela=janela_para_nova_rodada(fase),
    )
    save_snapshot(snapshot_atual(linhas))
    return hist


_FASE_LABEL = {
    "oitavas": "Oitavas",
    "quartas": "Quartas",
    "semis": "Semis",
    "final": "Final",
}
_FASE_LABEL_CURTA = {
    "oitavas": "Oit",
    "quartas": "Qua",
    "semis": "Sem",
    "final": "Fin",
}
_JANELA_LABEL = {
    "ida": "Ida",
    "volta": "Volta",
}


def _linha_do_participante(
    linhas: list[dict],
    *,
    participante_id: int | None,
    nome: str | None,
) -> dict | None:
    if participante_id is not None:
        for row in linhas:
            rid = row.get("participante_id")
            if rid is not None and int(rid) == int(participante_id):
                return row
    if nome:
        nome_cf = nome.casefold()
        for row in linhas:
            if (row.get("participante") or "").casefold() == nome_cf:
                return row
    return None


def _entrada_resumo_rodada(
    *,
    rotulo: str,
    fase: str,
    janela: str,
    linha: dict | None,
    ao_vivo: bool = False,
    numero: int | None = None,
    jogos: list[dict] | None = None,
) -> dict:
    if ao_vivo:
        rotulo_curto = "Ao vivo"
    elif numero is not None:
        rotulo_curto = f"R{numero}"
    else:
        rotulo_curto = rotulo
    return {
        "rotulo": rotulo,
        "rotulo_curto": rotulo_curto,
        "fase": fase or "",
        "fase_label": _FASE_LABEL.get(fase or "", fase or ""),
        "fase_label_curta": _FASE_LABEL_CURTA.get(fase or "", _FASE_LABEL.get(fase or "", fase or "")),
        "janela": janela or "",
        "janela_label": _JANELA_LABEL.get(janela or "", janela or ""),
        "rod": int(linha.get("rod") or 0) if linha else 0,
        "soma": int(linha.get("soma") or 0) if linha else 0,
        "posicao": int(linha["posicao"]) if linha and linha.get("posicao") is not None else None,
        "movimento": linha.get("movimento") if linha else None,
        "ao_vivo": ao_vivo,
        "jogos": jogos or [],
    }


def _janela_inferida_na_fase(fase: str, indice_na_fase: int, janela_gravada: str) -> str:
    """1ª rodada da fase → Ida; 2ª → Volta; demais mantêm o gravado."""
    if indice_na_fase <= 0:
        return "ida"
    if indice_na_fase == 1:
        return "volta"
    return janela_gravada if janela_gravada in ("ida", "volta") else "volta"


def _rodada_historico_vazia(rod: dict) -> bool:
    """True se ninguém pontuou na rodada (fechamento fantasma)."""
    linhas = rod.get("linhas") or []
    if not linhas:
        return True
    return all(int(r.get("rod") or 0) == 0 for r in linhas)


def _jogos_detalhe_participante(
    participante_id: int,
    *,
    fase: str,
    perna: str,
) -> list[dict]:
    """Pontos jogo a jogo do participante na fase/perna (resultados oficiais)."""
    from src.db import list_confrontos_completos, palpites_do_participante
    from src.seed_data import emblema_url, nome_clube_curto

    if perna not in ("ida", "volta") or not fase:
        return []
    palpites = palpites_do_participante(participante_id)
    out: list[dict] = []
    for c in list_confrontos_completos(fase):
        jogo = _jogo_por_perna(c, perna)
        if not jogo:
            continue
        if jogo.get("gols_mandante") is None or jogo.get("gols_visitante") is None:
            continue
        real_m = int(jogo["gols_mandante"])
        real_v = int(jogo["gols_visitante"])
        # Na volta o mandante é o clube B.
        if perna == "volta":
            casa_nome = c.get("clube_b") or "?"
            fora_nome = c.get("clube_a") or "?"
        else:
            casa_nome = c.get("clube_a") or "?"
            fora_nome = c.get("clube_b") or "?"
        pj = palpites["jogos"].get(jogo["id"])
        base = {
            "casa": casa_nome,
            "fora": fora_nome,
            "casa_curto": nome_clube_curto(casa_nome),
            "fora_curto": nome_clube_curto(fora_nome),
            "casa_emblema": emblema_url(casa_nome),
            "fora_emblema": emblema_url(fora_nome),
            "real_m": real_m,
            "real_v": real_v,
        }
        if not pj:
            out.append(
                {
                    **base,
                    "palpite_m": None,
                    "palpite_v": None,
                    "pts": 0,
                    "placar": 0,
                    "vencedor": 0,
                    "gols_casa": 0,
                    "gols_fora": 0,
                    "sem_palpite": True,
                }
            )
            continue
        det = pontos_detalhados(
            int(pj["gols_mandante"]),
            int(pj["gols_visitante"]),
            real_m,
            real_v,
            fase=fase,
            clube_casa_id=jogo.get("mandante_clube_id") or "a",
            palpite_penaltis=None,
            real_penaltis=None,
            permite_empate=True,
        )
        out.append(
            {
                **base,
                "palpite_m": int(pj["gols_mandante"]),
                "palpite_v": int(pj["gols_visitante"]),
                "pts": int(det.total),
                "placar": int(det.placar),
                "vencedor": int(det.vencedor),
                "gols_casa": int(det.gols_casa),
                "gols_fora": int(det.gols_fora),
                "sem_palpite": False,
            }
        )
    return out


def janela_para_nova_rodada(fase: str | None = None) -> str:
    """Janela gravada ao confirmar: 1ª da fase = ida, 2ª = volta.

    Conta só rodadas com pontuação (ignora fechamentos fantasma).
    """
    from src.db import get_janela, get_meta, get_rodada_historico, list_rodadas_historico

    fase_ref = fase or get_meta("fase_atual", "oitavas") or "oitavas"
    n = 0
    for h in list_rodadas_historico():
        if (h.get("fase") or "") != fase_ref:
            continue
        full = get_rodada_historico(int(h["id"]))
        if full and not _rodada_historico_vazia(full):
            n += 1
    if n <= 0:
        return "ida"
    if n == 1:
        return "volta"
    j = get_janela()
    return j if j in ("ida", "volta") else "volta"


def resumo_pontuacao_por_participante(
    linhas_ao_vivo: list[dict] | None = None,
) -> dict[int, list[dict]]:
    """Histórico de pontuação por rodada confirmada + situação ao vivo.

    Devolve ``{participante_id: [entrada, ...]}`` em ordem cronológica.
    Cada entrada traz rótulo, fase/perna (Ida/Volta inferida), pts, soma,
    posição e lista ``jogos`` (detalhe jogo a jogo). Rodadas confirmadas
    sem pontuação de ninguém são omitidas.
    """
    from src.db import get_janela, get_meta, get_rodada_historico, list_rodadas_historico

    ao_vivo = linhas_ao_vivo if linhas_ao_vivo is not None else calcular_classificacao()
    historico_meta = list_rodadas_historico()
    rodadas: list[dict] = []
    for meta in historico_meta:
        full = get_rodada_historico(int(meta["id"]))
        if full and not _rodada_historico_vazia(full):
            rodadas.append(full)

    # Índice da rodada dentro da fase (para Ida/Volta corretos).
    indice_na_fase: dict[int, int] = {}
    contagem_fase: dict[str, int] = {}
    for rod in rodadas:
        f = rod.get("fase") or ""
        indice_na_fase[int(rod["id"])] = contagem_fase.get(f, 0)
        contagem_fase[f] = contagem_fase.get(f, 0) + 1

    # Uma entrada por (fase, Ida/Volta): evita R3 fantasma duplicando Oit·Volta.
    rodadas_unicas: list[tuple[dict, str, str]] = []
    vistos: set[tuple[str, str]] = set()
    for rod in rodadas:
        fase_r = rod.get("fase") or ""
        idx = indice_na_fase.get(int(rod["id"]), 0)
        janela_r = _janela_inferida_na_fase(fase_r, idx, rod.get("janela") or "")
        key = (fase_r, janela_r)
        if key in vistos:
            continue
        vistos.add(key)
        rodadas_unicas.append((rod, fase_r, janela_r))

    fase_atual = get_meta("fase_atual", "oitavas") or "oitavas"
    janela_atual = get_janela()
    if janela_atual not in ("ida", "volta"):
        janela_atual = "ida"

    out: dict[int, list[dict]] = {}

    for row in ao_vivo:
        pid = row.get("participante_id")
        if pid is None:
            continue
        pid = int(pid)
        nome = row.get("participante")
        entradas: list[dict] = []
        for rod, fase_r, janela_r in rodadas_unicas:
            linha = _linha_do_participante(
                rod.get("linhas") or [],
                participante_id=pid,
                nome=nome,
            )
            entradas.append(
                _entrada_resumo_rodada(
                    rotulo=rod.get("rotulo") or f"Rodada {rod.get('numero')}",
                    fase=fase_r,
                    janela=janela_r,
                    linha=linha,
                    ao_vivo=False,
                    numero=rod.get("numero"),
                    jogos=_jogos_detalhe_participante(
                        pid, fase=fase_r, perna=janela_r
                    ),
                )
            )
        entradas.append(
            _entrada_resumo_rodada(
                rotulo="Ao vivo",
                fase=fase_atual,
                janela=janela_atual,
                linha=row,
                ao_vivo=True,
                jogos=_jogos_detalhe_participante(
                    pid, fase=fase_atual, perna=janela_atual
                ),
            )
        )
        out[pid] = entradas
    return out


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
