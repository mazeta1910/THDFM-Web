"""Portal da Transparência — breakdown por jogo (estilo planilha)."""

from __future__ import annotations

from src.db import list_confrontos_completos, list_participantes, palpites_do_participante
from src.scoring import classificar_palpite, lado_por_clube
from src.seed_data import formatar_inicio_jogo

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
    out: list[dict] = []
    for key in ("casa", "empate", "fora", "sem"):
        items = buckets.get(key) or []
        if not items:
            continue
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
                "sem_palpite": False,
                "avatar_path": None,
                "n": len(items),
            }
        )
        out.extend(items)
    return out


def montar_portal(fase: str, *, exigir_resultado: bool = True) -> list[dict]:
    """Tabelas por jogo com palpites dos liberados, para a fase pedida.

    exigir_resultado=True (público): só jogos com placar oficial.
    exigir_resultado=False (admin): todos os jogos; inclui quem ainda não palpitou.
    """
    confrontos = list_confrontos_completos(fase)
    liberados = [p for p in list_participantes() if p.get("status") == "liberado"]
    liberados.sort(key=lambda p: (p.get("nome") or "").casefold())

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
                    "avatar_path": p.get("avatar_path"),
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
                            "sem_palpite": True,
                        }
                    )
                    continue

                pen_row = palp["penaltis"].get(c["id"])
                palpite_pen = pen_row["penaltis_clube_id"] if pen_row else None
                pen_label = ""
                if pj["gols_mandante"] == pj["gols_visitante"] and palpite_pen in ("a", "b"):
                    pen_label = _clube_nome(c, palpite_pen)

                grupo = _grupo_lado_palpite(
                    int(pj["gols_mandante"]),
                    int(pj["gols_visitante"]),
                    mandante_clube_id=mandante_id,
                    visitante_clube_id=visitante_id,
                    penaltis_clube_id=palpite_pen,
                )

                if tem_resultado:
                    categoria, acertou_venc = classificar_palpite(
                        int(pj["gols_mandante"]),
                        int(pj["gols_visitante"]),
                        real_m,
                        real_v,
                        clube_casa_id=mandante_id,
                        palpite_penaltis=palpite_pen,
                        real_penaltis=real_pen,
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
                            "sem_palpite": False,
                        }
                    )

            linhas.extend(
                _linhas_agrupadas_por_time(
                    palpites_rows,
                    clube_casa=clube_casa,
                    clube_fora=clube_fora,
                )
            )

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
                }
            )

    return tabelas
