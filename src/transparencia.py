"""Portal da Transparência — breakdown por jogo (estilo planilha)."""

from __future__ import annotations

from src.db import list_confrontos_completos, list_participantes, map_hall_bordas, palpites_do_participante, participante_ativo_no_bolao
from src.scoring import classificar_palpite, lado_por_clube, pontos_detalhados
from src.seed_data import formatar_inicio_jogo

_PTS_VAZIOS = {
    "pts_placar": 0,
    "pts_vencedor": 0,
    "pts_gols_casa": 0,
    "pts_gols_fora": 0,
    "pts_total": None,
}

_GRUPO_ORDEM = {"casa": 0, "empate": 1, "fora": 2, "sem": 3}
_ACERTOU_ORDEM = {"Placar": 0, "Gols Casa": 1, "Gols fora": 2, "Nada": 3, "": 4}


def _clube_nome(confronto: dict, clube_id: str) -> str:
    return confronto["clube_a"] if clube_id == "a" else confronto["clube_b"]


def _visitante_id(mandante_clube_id: str) -> str:
    return "b" if mandante_clube_id == "a" else "a"


def _vencedor_oficial_label(
    confronto: dict,
    *,
    gols_m: int,
    gols_v: int,
    mandante_clube_id: str,
    penaltis: str | None,
) -> str:
    lado = lado_por_clube(
        gols_m,
        gols_v,
        clube_casa_id=mandante_clube_id,
        penaltis_clube_id=penaltis,
        permite_empate=True,
    )
    if lado == "empate":
        return "Empate"
    if lado in ("a", "b"):
        return _clube_nome(confronto, lado)
    return "—"


def _grupo_lado_palpite(
    gols_m: int,
    gols_v: int,
    *,
    mandante_clube_id: str,
    visitante_clube_id: str,
    penaltis_clube_id: str | None,
) -> str:
    """Agrupa pelo time que o participante palpitou como vencedor do jogo."""
    if gols_m > gols_v:
        return "casa"
    if gols_m < gols_v:
        return "fora"
    if penaltis_clube_id == mandante_clube_id:
        return "casa"
    if penaltis_clube_id == visitante_clube_id:
        return "fora"
    return "empate"


def _linhas_agrupadas_por_time(
    palpites: list[dict],
    *,
    clube_casa: str,
    clube_fora: str,
) -> list[dict]:
    """Insere cabeçalhos de grupo (casa / empate / fora / sem) e ordena dentro de cada um."""
    buckets: dict[str, list[dict]] = {
        "casa": [],
        "empate": [],
        "fora": [],
        "sem": [],
    }
    for row in palpites:
        buckets.setdefault(row.get("grupo") or "sem", []).append(row)

    for key, items in buckets.items():
        items.sort(
            key=lambda r: (
                _ACERTOU_ORDEM.get(r.get("acertou") or "", 4),
                0 if r.get("vencedor") == "Acertou" else 1,
                (r.get("nome") or "").casefold(),
            )
        )

    labels = {
        "casa": clube_casa,
        "empate": "Empate",
        "fora": clube_fora,
        "sem": "Sem palpite",
    }
    # % só entre quem palpitou (casa/empate/fora); "sem" não entra no denominador.
    n_com = sum(len(buckets.get(k) or []) for k in ("casa", "empate", "fora"))
    out: list[dict] = []
    for key in ("casa", "empate", "fora", "sem"):
        items = buckets.get(key) or []
        if not items:
            continue
        n = len(items)
        pct = round(100.0 * n / n_com, 1) if key != "sem" and n_com else None
        out.append(
            {
                "tipo": "grupo",
                "grupo": key,
                "nome": labels[key],
                "gols_m": "",
                "gols_v": "",
                "penaltis": "",
                "acertou": "",
                "vencedor": "",
                "acertou_class": "",
                "vencedor_class": "",
                **_PTS_VAZIOS,
                "sem_palpite": False,
                "avatar_path": None,
                "n": n,
                "pct": pct,
            }
        )
        out.extend(items)
    return out


def _metricas_palpites(
    palpites_rows: list[dict],
    *,
    clube_casa: str = "",
    clube_fora: str = "",
) -> dict[str, Any]:
    """Resumo do bolão para um jogo: lados, médias e extremos."""
    com = [r for r in palpites_rows if not r.get("sem_palpite")]
    n_casa = sum(1 for r in com if r.get("grupo") == "casa")
    n_empate = sum(1 for r in com if r.get("grupo") == "empate")
    n_fora = sum(1 for r in com if r.get("grupo") == "fora")
    n_sem = sum(1 for r in palpites_rows if r.get("sem_palpite"))
    n_com = len(com)

    gols_casa: list[int] = []
    gols_fora: list[int] = []
    totais: list[int] = []
    diffs: list[int] = []
    placares: dict[str, int] = {}
    maior: dict[str, Any] | None = None

    for r in com:
        try:
            gm = int(r["gols_m"])
            gv = int(r["gols_v"])
        except (TypeError, ValueError, KeyError):
            continue
        gols_casa.append(gm)
        gols_fora.append(gv)
        totais.append(gm + gv)
        d = abs(gm - gv)
        diffs.append(d)
        key = f"{gm} x {gv}"
        placares[key] = placares.get(key, 0) + 1
        if maior is None or d > int(maior["diff"]):
            maior = {
                "diff": d,
                "placar": key,
                "gols_m": gm,
                "gols_v": gv,
                "nome": r.get("nome") or "",
            }

    placar_mais_comum: dict[str, Any] | None = None
    if placares:
        best_key, best_n = max(placares.items(), key=lambda kv: (kv[1], kv[0]))
        placar_mais_comum = {"placar": best_key, "n": best_n}

    def _media(vals: list[int]) -> float | None:
        if not vals:
            return None
        return round(sum(vals) / len(vals), 2)

    favorito = None
    favorito_label = None
    consenso_pct = None
    if n_com:
        ranking = [
            ("casa", n_casa, clube_casa or "Casa"),
            ("empate", n_empate, "Empate"),
            ("fora", n_fora, clube_fora or "Fora"),
        ]
        ranking.sort(key=lambda kv: (-kv[1], kv[0]))
        if ranking[0][1] > 0:
            favorito = ranking[0][0]
            favorito_label = ranking[0][2]
            consenso_pct = round(100.0 * ranking[0][1] / n_com, 1)

    media_gc = _media(gols_casa)
    media_gf = _media(gols_fora)
    gap_medias = None
    if media_gc is not None and media_gf is not None:
        gap_medias = round(abs(media_gc - media_gf), 2)

    mais_gols: dict[str, Any] | None = None
    menos_gols: dict[str, Any] | None = None
    for r in com:
        try:
            gm = int(r["gols_m"])
            gv = int(r["gols_v"])
        except (TypeError, ValueError, KeyError):
            continue
        total = gm + gv
        entry = {
            "nome": r.get("nome") or "",
            "total": total,
            "placar": f"{gm} x {gv}",
        }
        if mais_gols is None or total > int(mais_gols["total"]):
            mais_gols = entry
        if menos_gols is None or total < int(menos_gols["total"]):
            menos_gols = entry

    return {
        "total": n_com,
        "n_casa": n_casa,
        "n_empate": n_empate,
        "n_fora": n_fora,
        "n_sem": n_sem,
        "n_com_palpite": n_com,
        "pct_casa": round(100.0 * n_casa / n_com, 1) if n_com else None,
        "pct_empate": round(100.0 * n_empate / n_com, 1) if n_com else None,
        "pct_fora": round(100.0 * n_fora / n_com, 1) if n_com else None,
        "media_gols_casa": media_gc,
        "media_gols_fora": media_gf,
        "media_gols_partida": _media(totais),
        "media_diferenca": _media(diffs),
        "gap_medias": gap_medias,
        "maior_diferenca": maior,
        "mais_gols": mais_gols,
        "menos_gols": menos_gols,
        "placar_mais_comum": placar_mais_comum,
        "favorito": favorito,
        "favorito_label": favorito_label,
        "consenso": favorito,
        "consenso_label": favorito_label,
        "consenso_pct": consenso_pct,
    }


def ranking_apostadores(tabelas: list[dict]) -> dict[str, Any] | None:
    """Ranking geral entre participantes a partir das tabelas informadas."""
    users: dict[str, dict[str, Any]] = {}
    for t in tabelas:
        for row in t.get("linhas") or []:
            if row.get("tipo") != "palpite" or row.get("sem_palpite"):
                continue
            nome = (row.get("nome") or "").strip() or "?"
            try:
                gm = int(row["gols_m"])
                gv = int(row["gols_v"])
            except (TypeError, ValueError, KeyError):
                continue
            total = gm + gv
            u = users.setdefault(
                nome,
                {
                    "nome": nome,
                    "n": 0,
                    "gols": 0,
                    "empates": 0,
                    "casa": 0,
                    "fora": 0,
                    "max_gols": -1,
                    "max_placar": "",
                },
            )
            u["n"] += 1
            u["gols"] += total
            grupo = row.get("grupo")
            if grupo == "empate":
                u["empates"] += 1
            elif grupo == "casa":
                u["casa"] += 1
            elif grupo == "fora":
                u["fora"] += 1
            if total > int(u["max_gols"]):
                u["max_gols"] = total
                u["max_placar"] = f"{gm} x {gv}"

    if not users:
        return None

    lista = list(users.values())
    for u in lista:
        u["media_gols"] = round(u["gols"] / u["n"], 2) if u["n"] else 0.0

    def _max(key: str) -> dict[str, Any]:
        return max(lista, key=lambda u: (u[key], u["nome"]))

    def _min(key: str) -> dict[str, Any]:
        return min(lista, key=lambda u: (u[key], u["nome"]))

    mais_gols = _max("media_gols")
    menos_gols = _min("media_gols")
    mais_empates = _max("empates")
    mais_casa = _max("casa")
    mais_fora = _max("fora")
    placar_mais_alto = _max("max_gols")

    def _lado(u: dict[str, Any], key: str) -> dict[str, Any]:
        n = int(u[key])
        jogos = int(u["n"])
        return {
            "nome": u["nome"],
            "n": n,
            "jogos": jogos,
            "pct": round(100.0 * n / jogos, 1) if jogos else None,
        }

    return {
        "mais_gols": {
            "nome": mais_gols["nome"],
            "media": mais_gols["media_gols"],
            "total": mais_gols["gols"],
            "n": mais_gols["n"],
        },
        "menos_gols": {
            "nome": menos_gols["nome"],
            "media": menos_gols["media_gols"],
            "total": menos_gols["gols"],
            "n": menos_gols["n"],
        },
        "mais_empates": _lado(mais_empates, "empates"),
        "mais_casa": _lado(mais_casa, "casa"),
        "mais_fora": _lado(mais_fora, "fora"),
        "placar_mais_alto": {
            "nome": placar_mais_alto["nome"],
            "placar": placar_mais_alto["max_placar"],
            "total": placar_mais_alto["max_gols"],
        },
    }


def metricas_gerais(tabelas: list[dict]) -> dict[str, Any] | None:
    """Agrega palpites da fase/perna atual (visão Geral)."""
    rows: list[dict] = []
    for t in tabelas:
        for row in t.get("linhas") or []:
            if row.get("tipo") == "palpite":
                rows.append(row)
    if not any(not r.get("sem_palpite") for r in rows):
        return None
    return _metricas_palpites(rows, clube_casa="Casa", clube_fora="Fora")


def montar_portal(fase: str, *, exigir_resultado: bool = True) -> list[dict]:
    """Tabelas por jogo com palpites dos liberados, para a fase pedida.

    exigir_resultado=True (público): só jogos com placar oficial.
    exigir_resultado=False (admin): todos os jogos; inclui quem ainda não palpitou.
    """
    confrontos = list_confrontos_completos(fase)
    liberados = [p for p in list_participantes() if participante_ativo_no_bolao(p)]
    liberados.sort(key=lambda p: (p.get("nome") or "").casefold())
    hall_bordas = map_hall_bordas([p["id"] for p in liberados])

    cache_palpites = {p["id"]: palpites_do_participante(p["id"]) for p in liberados}
    tabelas: list[dict] = []

    for idx, c in enumerate(confrontos, start=1):
        for jogo in c.get("jogos") or []:
            tem_resultado = (
                jogo.get("gols_mandante") is not None
                and jogo.get("gols_visitante") is not None
            )
            if exigir_resultado and not tem_resultado:
                continue

            mandante_id = jogo["mandante_clube_id"]
            visitante_id = _visitante_id(mandante_id)
            clube_casa = _clube_nome(c, mandante_id)
            clube_fora = _clube_nome(c, visitante_id)
            real_m = int(jogo["gols_mandante"]) if tem_resultado else None
            real_v = int(jogo["gols_visitante"]) if tem_resultado else None
            real_pen = jogo.get("penaltis_clube_id") if tem_resultado else None
            perna = jogo.get("perna") or ""
            perna_label = {"ida": "Ida", "volta": "Volta", "unico": "Jogo"}.get(perna, perna)
            inicio_em = jogo.get("inicio_em")
            inicio_label = formatar_inicio_jogo(inicio_em)

            linhas: list[dict] = []
            if tem_resultado:
                linhas.append(
                    {
                        "tipo": "placar",
                        "grupo": "",
                        "nome": "PLACAR",
                        "gols_m": real_m,
                        "gols_v": real_v,
                        "penaltis": _clube_nome(c, real_pen) if real_pen in ("a", "b") else "",
                        "acertou": "",
                        "vencedor": _vencedor_oficial_label(
                            c,
                            gols_m=real_m,
                            gols_v=real_v,
                            mandante_clube_id=mandante_id,
                            penaltis=real_pen,
                        ),
                        "acertou_class": "",
                        "vencedor_class": "cell-venc-oficial",
                        **_PTS_VAZIOS,
                        "sem_palpite": False,
                        "avatar_path": None,
                    }
                )

            palpites_rows: list[dict] = []
            for p in liberados:
                palp = cache_palpites[p["id"]]
                pj = palp["jogos"].get(jogo["id"])
                base = {
                    "tipo": "palpite",
                    "nome": p["nome"],
                    "participante_id": p["id"],
                    "avatar_path": p.get("avatar_path"),
                    "hall_borda": hall_bordas.get(int(p["id"])),
                }
                if not pj:
                    if exigir_resultado:
                        continue
                    palpites_rows.append(
                        {
                            **base,
                            "grupo": "sem",
                            "gols_m": "—",
                            "gols_v": "—",
                            "penaltis": "",
                            "acertou": "",
                            "vencedor": "",
                            "acertou_class": "",
                            "vencedor_class": "",
                            **_PTS_VAZIOS,
                            "sem_palpite": True,
                        }
                    )
                    continue

                pen_row = palp["penaltis"].get(c["id"])
                palpite_pen = pen_row["penaltis_clube_id"] if pen_row else None
                # Pênaltis só existem na volta — na ida ignoramos escolha/exibição.
                pen_efetivo = palpite_pen if perna == "volta" else None
                real_pen_efetivo = real_pen if perna == "volta" else None
                pen_label = ""
                if (
                    perna == "volta"
                    and pj["gols_mandante"] == pj["gols_visitante"]
                    and pen_efetivo in ("a", "b")
                ):
                    pen_label = _clube_nome(c, pen_efetivo)

                grupo = _grupo_lado_palpite(
                    int(pj["gols_mandante"]),
                    int(pj["gols_visitante"]),
                    mandante_clube_id=mandante_id,
                    visitante_clube_id=visitante_id,
                    penaltis_clube_id=pen_efetivo,
                )

                if tem_resultado:
                    categoria, acertou_venc = classificar_palpite(
                        int(pj["gols_mandante"]),
                        int(pj["gols_visitante"]),
                        real_m,
                        real_v,
                        clube_casa_id=mandante_id,
                        palpite_penaltis=pen_efetivo,
                        real_penaltis=real_pen_efetivo,
                        permite_empate=True,
                    )
                    det = pontos_detalhados(
                        int(pj["gols_mandante"]),
                        int(pj["gols_visitante"]),
                        real_m,
                        real_v,
                        fase=c["fase"],
                        clube_casa_id=mandante_id,
                        palpite_penaltis=pen_efetivo,
                        real_penaltis=real_pen_efetivo,
                        permite_empate=True,
                    )
                    acertou_slug = {
                        "Placar": "placar",
                        "Gols Casa": "gols-casa",
                        "Gols fora": "gols-fora",
                        "Nada": "nada",
                    }.get(categoria, "nada")
                    palpites_rows.append(
                        {
                            **base,
                            "grupo": grupo,
                            "gols_m": pj["gols_mandante"],
                            "gols_v": pj["gols_visitante"],
                            "penaltis": pen_label,
                            "acertou": categoria,
                            "vencedor": "Acertou" if acertou_venc else "Errou",
                            "acertou_class": f"cell-acertou-{acertou_slug}",
                            "vencedor_class": "cell-venc-ok" if acertou_venc else "cell-venc-erro",
                            "pts_placar": det.placar,
                            "pts_vencedor": det.vencedor,
                            "pts_gols_casa": det.gols_casa,
                            "pts_gols_fora": det.gols_fora,
                            "pts_total": det.total,
                            "sem_palpite": False,
                        }
                    )
                else:
                    palpites_rows.append(
                        {
                            **base,
                            "grupo": grupo,
                            "gols_m": pj["gols_mandante"],
                            "gols_v": pj["gols_visitante"],
                            "penaltis": pen_label,
                            "acertou": "",
                            "vencedor": "",
                            "acertou_class": "",
                            "vencedor_class": "",
                            **_PTS_VAZIOS,
                            "sem_palpite": False,
                        }
                    )

            metricas = _metricas_palpites(
                palpites_rows,
                clube_casa=clube_casa,
                clube_fora=clube_fora,
            )
            linhas.extend(
                _linhas_agrupadas_por_time(
                    palpites_rows,
                    clube_casa=clube_casa,
                    clube_fora=clube_fora,
                )
            )

            # Zebrado nas linhas de palpite (ignora placar e cabeçalhos de grupo).
            zebra_i = 0
            for row in linhas:
                if row.get("tipo") != "palpite":
                    continue
                row["zebra"] = zebra_i % 2 == 1
                zebra_i += 1

            tabelas.append(
                {
                    "jogo_id": jogo["id"],
                    "confronto_id": c["id"],
                    "jogo_num": idx,
                    "fase": c["fase"],
                    "perna": perna,
                    "perna_label": perna_label,
                    "inicio_em": inicio_em,
                    "inicio_label": inicio_label,
                    "clube_casa": clube_casa,
                    "clube_fora": clube_fora,
                    "titulo": f"Jogo {idx} · {clube_casa} x {clube_fora} · {perna_label}",
                    "tem_resultado": tem_resultado,
                    "linhas": linhas,
                    "metricas": metricas,
                }
            )

    return tabelas
