"""Estilo de palpites — perfis individuais, consenso e Hall de nicks."""

from __future__ import annotations

from collections import Counter, defaultdict
from itertools import combinations
from typing import Any

from src.db import list_confrontos_completos, list_participantes, palpites_do_participante

# Nick id → (rótulo, explicação)
EXPLICACOES_NICK: dict[str, tuple[str, str]] = {
    "boquinha": (
        "Boquinha de Cemitério",
        "Seguiu o consenso do bolão e errou — enterrou o grupo com a manada.",
    ),
    "maria": (
        "Maria Vai Com as Outras",
        "Seguiu o consenso do bolão e acertou.",
    ),
    "cacador_zica": (
        "Caçador de Zica",
        "Acertou o underdog quando a maioria ia no favorito do grupo.",
    ),
    "proxeneta": (
        "O Proxeneta",
        "Mais lucrou quando a maioria errou — acertos contrarian (contra o consenso).",
    ),
    "joselito": (
        "Joselito",
        "Aposta seguro: favorito do grupo e placares baixos. Não sabe brincar.",
    ),
    "burro": (
        "Burro",
        "Foi contra o consenso e errou.",
    ),
    "inimigo_jogo_bonito": (
        "Inimigo do jogo bonito",
        "Quem mais palpitou empate.",
    ),
    "casalzinho": (
        "Casalzinho",
        "Dupla com mais palpites idênticos.",
    ),
    "triangulo": (
        "Triângulo Amoroso",
        "Trio com mais placares idênticos.",
    ),
    "quarteto": (
        "Quarteto Fantástico",
        "Quarteto com mais palpites iguais.",
    ),
    "arqui_inimigos": (
        "Arqui-inimigos",
        "Duplas com menos palpites similares (pode haver mais de uma).",
    ),
    "donelli": (
        "Acha que todo goleiro é o Matheus Donelli",
        "Maior média de gols nos palpites — acha que todo goleiro toma goleada.",
    ),
    "placar_visto": (
        "Placar mais visto",
        "Placar mais repetido entre todos os palpites do bolão.",
    ),
}


def _lado(gm: int, gv: int) -> str:
    if gm > gv:
        return "casa"
    if gm < gv:
        return "fora"
    return "empate"


def _pct(n: int, total: int) -> float | None:
    if total <= 0:
        return None
    return round(100.0 * n / total, 1)


def _carregar_universo(fase: str | None = None) -> dict[str, Any]:
    """Carrega liberados, jogos da fase e palpites indexados."""
    confrontos = list_confrontos_completos(fase)
    liberados = [p for p in list_participantes() if p.get("status") == "liberado"]
    liberados.sort(key=lambda p: ((p.get("nome") or "").casefold(), p["id"]))

    jogos: list[dict[str, Any]] = []
    for c in confrontos:
        for j in c.get("jogos") or []:
            item = dict(j)
            item["confronto_id"] = c["id"]
            item["clube_a"] = c["clube_a"]
            item["clube_b"] = c["clube_b"]
            item["fase"] = c["fase"]
            jogos.append(item)

    cache = {p["id"]: palpites_do_participante(p["id"]) for p in liberados}
    return {"liberados": liberados, "jogos": jogos, "cache": cache}


def consenso_por_jogo(universo: dict[str, Any] | None = None) -> dict[int, dict[str, Any]]:
    """Por jogo_id: lado majoritário, contagens e se há empate de consenso."""
    u = universo or _carregar_universo()
    out: dict[int, dict[str, Any]] = {}
    for jogo in u["jogos"]:
        jid = int(jogo["id"])
        counts: Counter[str] = Counter()
        for p in u["liberados"]:
            pj = u["cache"][p["id"]]["jogos"].get(jid)
            if not pj:
                continue
            counts[_lado(int(pj["gols_mandante"]), int(pj["gols_visitante"]))] += 1
        total = sum(counts.values())
        if total <= 0:
            continue
        melhor = counts.most_common()
        top_n = melhor[0][1]
        tops = [lado for lado, n in melhor if n == top_n]
        out[jid] = {
            "total": total,
            "counts": dict(counts),
            "lado": tops[0] if len(tops) == 1 else None,  # None = empate de consenso
            "pct": _pct(top_n, total) if len(tops) == 1 else None,
            "empate_consenso": len(tops) != 1,
        }
    return out


def _perfil_de(
    part: dict[str, Any],
    *,
    jogos: list[dict[str, Any]],
    cache_palp: dict[str, Any],
    consenso: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    pid = part["id"]
    n_casa = n_empate = n_fora = 0
    gols_totais = 0
    gols_casa_sum = 0
    gols_fora_sum = 0
    goleadas = 0
    baixos = 0
    placares: Counter[str] = Counter()
    seguiu = errou_seguiu = acertou_seguiu = 0
    contra = errou_contra = acertou_contra = 0
    zebra_ok = 0
    acertos_venc = acertos_placar = 0
    n_com_resultado = 0
    # assinatura de placar por jogo para similaridade: {jogo_id: "gm-gv"}
    assinatura: dict[int, str] = {}

    for jogo in jogos:
        jid = int(jogo["id"])
        pj = cache_palp["jogos"].get(jid)
        if not pj:
            continue
        gm = int(pj["gols_mandante"])
        gv = int(pj["gols_visitante"])
        lado = _lado(gm, gv)
        if lado == "casa":
            n_casa += 1
        elif lado == "fora":
            n_fora += 1
        else:
            n_empate += 1
        gols_totais += gm + gv
        gols_casa_sum += gm
        gols_fora_sum += gv
        if abs(gm - gv) >= 3:
            goleadas += 1
        if (gm, gv) in ((0, 0), (1, 0), (0, 1)):
            baixos += 1
        key = f"{gm}×{gv}"
        placares[key] += 1
        assinatura[jid] = f"{gm}-{gv}"

        cons = consenso.get(jid)
        tem_res = (
            jogo.get("gols_mandante") is not None
            and jogo.get("gols_visitante") is not None
        )
        if not tem_res or not cons or cons.get("empate_consenso") or not cons.get("lado"):
            continue

        n_com_resultado += 1
        real_m = int(jogo["gols_mandante"])
        real_v = int(jogo["gols_visitante"])
        real_lado = _lado(real_m, real_v)
        cons_lado = cons["lado"]
        seguiu_consenso = lado == cons_lado
        acertou_lado = lado == real_lado
        if gm == real_m and gv == real_v:
            acertos_placar += 1
        if acertou_lado:
            acertos_venc += 1

        if seguiu_consenso:
            seguiu += 1
            if acertou_lado:
                acertou_seguiu += 1
            else:
                errou_seguiu += 1
        else:
            contra += 1
            if acertou_lado:
                acertou_contra += 1
                # underdog certo: foi contra consenso e o consenso era o outro lado (não empate)
                if cons_lado != "empate" and lado != "empate":
                    zebra_ok += 1
            else:
                errou_contra += 1

    n = n_casa + n_empate + n_fora
    assinatura_placar = None
    if placares:
        best, best_n = max(placares.items(), key=lambda kv: (kv[1], kv[0]))
        assinatura_placar = {"placar": best, "n": best_n}

    media_gols = round(gols_totais / n, 2) if n else None
    # Joselito score: alto % no consenso + baixa média de gols
    n_no_consenso = 0
    n_avaliados_consenso = 0
    for jid, sig in assinatura.items():
        cons = consenso.get(jid)
        if not cons or cons.get("empate_consenso") or not cons.get("lado"):
            continue
        n_avaliados_consenso += 1
        gm_s, gv_s = sig.split("-")
        if _lado(int(gm_s), int(gv_s)) == cons["lado"]:
            n_no_consenso += 1
    pct_favorito = _pct(n_no_consenso, n_avaliados_consenso)

    return {
        "participante_id": pid,
        "nome": part.get("nome") or "",
        "avatar_path": part.get("avatar_path"),
        "n": n,
        "n_jogos_fase": len(jogos),
        "n_casa": n_casa,
        "n_empate": n_empate,
        "n_fora": n_fora,
        "pct_casa": _pct(n_casa, n),
        "pct_empate": _pct(n_empate, n),
        "pct_fora": _pct(n_fora, n),
        "media_gols": media_gols,
        "media_placar": (
            f"{round(gols_casa_sum / n, 1)}×{round(gols_fora_sum / n, 1)}" if n else None
        ),
        "goleadas": goleadas,
        "placares_baixos": baixos,
        "placar_assinatura": assinatura_placar,
        "pct_favorito": pct_favorito,
        "seguiu": seguiu,
        "boquinhas": errou_seguiu,  # consenso + errou
        "maria": acertou_seguiu,  # consenso + acertou
        "burro": errou_contra,  # contra + errou
        "proxeneta": acertou_contra,  # contra + acertou
        "zebra_ok": zebra_ok,
        "acertos_vencedor": acertos_venc,
        "acertos_placar": acertos_placar,
        "n_com_resultado": n_com_resultado,
        "assinatura": assinatura,
        "badges": [],  # preenchido depois pelo Hall
    }


def _overlap(a: dict[int, str], b: dict[int, str]) -> tuple[int, int]:
    """Retorna (iguais, jogos_em_comum)."""
    comuns = set(a) & set(b)
    if not comuns:
        return 0, 0
    iguais = sum(1 for jid in comuns if a[jid] == b[jid])
    return iguais, len(comuns)


def _melhor_grupo(
    perfis: list[dict[str, Any]],
    tamanho: int,
    *,
    maximizar: bool,
) -> list[dict[str, Any]]:
    """Encontra grupo(s) de `tamanho` com mais (ou menos) overlap médio de placares."""
    if len(perfis) < tamanho:
        return []
    candidatos: list[tuple[float, int, tuple[dict[str, Any], ...]]] = []
    for combo in combinations(perfis, tamanho):
        pares = list(combinations(combo, 2))
        scores = []
        for x, y in pares:
            iguais, comuns = _overlap(x["assinatura"], y["assinatura"])
            if comuns <= 0:
                scores = []
                break
            scores.append(iguais)
        if not scores:
            continue
        score = sum(scores) / len(scores)
        chave = sum(scores)
        candidatos.append((score, chave, combo))

    if not candidatos:
        return []

    if maximizar:
        best_score = max(c[0] for c in candidatos)
        melhores = [c for c in candidatos if c[0] == best_score]
        # desempate: mais iguais absolutos
        best_chave = max(c[1] for c in melhores)
        melhores = [c for c in melhores if c[1] == best_chave]
        # um grupo só (primeiro por nome)
        melhores.sort(key=lambda c: tuple(p["nome"].casefold() for p in c[2]))
        combo = melhores[0][2]
        return [
            {
                "nomes": [p["nome"] for p in combo],
                "ids": [p["participante_id"] for p in combo],
                "valor": round(melhores[0][0], 1),
                "valor_label": f"{int(round(melhores[0][0]))} palpites iguais",
            }
        ]

    # minimizar: empates no mínimo; no máx. 5.
    best_score = min(c[0] for c in candidatos)
    melhores = [c for c in candidatos if c[0] == best_score]
    melhores.sort(key=lambda c: tuple(p["nome"].casefold() for p in c[2]))
    out = []
    for score, _chave, combo in melhores[:5]:
        out.append(
            {
                "nomes": [p["nome"] for p in combo],
                "ids": [p["participante_id"] for p in combo],
                "valor": round(score, 1),
                "valor_label": f"{int(round(score))} palpites iguais",
            }
        )
    return out


def trofeus_hall(fase: str | None = None) -> dict[str, Any]:
    """Monta Hall + mapa de perfis para a ficha."""
    u = _carregar_universo(fase)
    consenso = consenso_por_jogo(u)
    perfis = [
        _perfil_de(p, jogos=u["jogos"], cache_palp=u["cache"][p["id"]], consenso=consenso)
        for p in u["liberados"]
    ]
    com_palpite = [p for p in perfis if p["n"] > 0]

    def _top(
        key: str,
        *,
        minimo: int = 1,
        reverse: bool = True,
        label_fn=None,
    ) -> dict[str, Any] | None:
        elegiveis = [p for p in com_palpite if int(p.get(key) or 0) >= minimo or not reverse]
        if key in ("media_gols", "pct_favorito", "pct_empate"):
            elegiveis = [p for p in com_palpite if p.get(key) is not None]
        if not elegiveis:
            return None
        if reverse:
            best = max(elegiveis, key=lambda p: (p.get(key) or 0, p["nome"]))
            tied = [
                p
                for p in elegiveis
                if (p.get(key) or 0) == (best.get(key) or 0)
            ]
        else:
            best = min(elegiveis, key=lambda p: (p.get(key) or 0, p["nome"]))
            tied = [
                p
                for p in elegiveis
                if (p.get(key) or 0) == (best.get(key) or 0)
            ]
        if minimo and (best.get(key) or 0) < minimo and key not in (
            "media_gols",
            "pct_favorito",
            "pct_empate",
        ):
            return None
        valor = best.get(key)
        return {
            "nomes": [p["nome"] for p in tied],
            "ids": [p["participante_id"] for p in tied],
            "valor": valor,
            "valor_label": label_fn(valor, best) if label_fn else str(valor),
        }

    # Joselito: score composto pct_favorito alto e media_gols baixa
    joselito = None
    if com_palpite:
        def _jose_score(p: dict[str, Any]) -> tuple:
            pf = p.get("pct_favorito")
            mg = p.get("media_gols")
            if pf is None or mg is None or p["n"] < 1:
                return (-1, 0, p["nome"])
            # maximizar favorito, minimizar gols
            return (pf, -mg, p["nome"])

        best = max(com_palpite, key=_jose_score)
        if best.get("pct_favorito") is not None:
            joselito = {
                "nomes": [best["nome"]],
                "ids": [best["participante_id"]],
                "valor": best["pct_favorito"],
                "valor_label": (
                    f"{best['pct_favorito']}% favorito · média {best['media_gols']} gols"
                ),
            }

    placares_grupo: Counter[str] = Counter()
    for p in com_palpite:
        for jid, sig in p["assinatura"].items():
            gm, gv = sig.split("-")
            placares_grupo[f"{gm}×{gv}"] += 1
    placar_visto = None
    if placares_grupo:
        pk, pn = max(placares_grupo.items(), key=lambda kv: (kv[1], kv[0]))
        placar_visto = {
            "nomes": [pk],
            "ids": [],
            "valor": pn,
            "valor_label": f"{pk} ({pn}×)",
        }

    casal = _melhor_grupo(com_palpite, 2, maximizar=True)
    triangulo = _melhor_grupo(com_palpite, 3, maximizar=True)
    quarteto = _melhor_grupo(com_palpite, 4, maximizar=True)
    arqui = _melhor_grupo(com_palpite, 2, maximizar=False)

    cards_spec = [
        ("boquinha", _top("boquinhas", minimo=1, label_fn=lambda v, _: f"{v}×")),
        ("maria", _top("maria", minimo=1, label_fn=lambda v, _: f"{v}×")),
        ("cacador_zica", _top("zebra_ok", minimo=1, label_fn=lambda v, _: f"{v}×")),
        ("proxeneta", _top("proxeneta", minimo=1, label_fn=lambda v, _: f"{v}×")),
        ("joselito", joselito),
        ("burro", _top("burro", minimo=1, label_fn=lambda v, _: f"{v}×")),
        (
            "inimigo_jogo_bonito",
            _top("n_empate", minimo=1, label_fn=lambda v, p: f"{v}× ({p.get('pct_empate') or 0}%)"),
        ),
        ("donelli", _top("media_gols", minimo=0, label_fn=lambda v, _: f"média {v} gols")),
        ("casalzinho", casal[0] if casal else None),
        ("triangulo", triangulo[0] if triangulo else None),
        ("quarteto", quarteto[0] if quarteto else None),
        ("arqui_inimigos", None),  # multi
        ("placar_visto", placar_visto),
    ]

    badges_por_id: dict[int, list[str]] = defaultdict(list)
    cards: list[dict[str, Any]] = []
    for nick_id, winner in cards_spec:
        label, expl = EXPLICACOES_NICK[nick_id]
        if nick_id == "arqui_inimigos":
            if not arqui:
                continue
            cards.append(
                {
                    "id": nick_id,
                    "titulo": label,
                    "explicacao": expl,
                    "grupos": arqui,  # várias duplas
                    "multi": True,
                }
            )
            for g in arqui:
                for pid in g["ids"]:
                    badges_por_id[pid].append(nick_id)
            continue
        if not winner:
            continue
        cards.append(
            {
                "id": nick_id,
                "titulo": label,
                "explicacao": expl,
                "nomes": winner["nomes"],
                "ids": winner.get("ids") or [],
                "valor_label": winner.get("valor_label") or "",
                "multi": False,
            }
        )
        for pid in winner.get("ids") or []:
            badges_por_id[pid].append(nick_id)

    for p in perfis:
        p["badges"] = [
            {"id": b, "titulo": EXPLICACOES_NICK[b][0], "explicacao": EXPLICACOES_NICK[b][1]}
            for b in badges_por_id.get(p["participante_id"], [])
            if b in EXPLICACOES_NICK
        ]
        # ficha não precisa da assinatura crua no HTML
        p.pop("assinatura", None)

    return {
        "cards": cards,
        "perfis": {p["participante_id"]: p for p in perfis},
        "perfis_lista": perfis,
    }


def perfil_participante(participante_id: int, fase: str | None = None) -> dict[str, Any] | None:
    data = trofeus_hall(fase)
    return data["perfis"].get(participante_id)
