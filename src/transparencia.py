"""Portal da Transparência — breakdown por jogo (estilo planilha)."""

from __future__ import annotations

from src.db import list_confrontos_completos, list_participantes, palpites_do_participante
from src.scoring import classificar_palpite, lado_por_clube


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


def montar_portal(fase: str) -> list[dict]:
    """Tabelas por jogo com placar oficial, para a fase pedida."""
    confrontos = list_confrontos_completos(fase)
    liberados = [p for p in list_participantes() if p.get("status") == "liberado"]
    liberados.sort(key=lambda p: (p.get("nome") or "").casefold())

    cache_palpites = {p["id"]: palpites_do_participante(p["id"]) for p in liberados}
    tabelas: list[dict] = []

    for c in confrontos:
        for jogo in c.get("jogos") or []:
            if jogo.get("gols_mandante") is None or jogo.get("gols_visitante") is None:
                continue

            mandante_id = jogo["mandante_clube_id"]
            visitante_id = _visitante_id(mandante_id)
            clube_casa = _clube_nome(c, mandante_id)
            clube_fora = _clube_nome(c, visitante_id)
            real_m = int(jogo["gols_mandante"])
            real_v = int(jogo["gols_visitante"])
            real_pen = jogo.get("penaltis_clube_id")
            perna = jogo.get("perna") or ""
            perna_label = {"ida": "Ida", "volta": "Volta", "unico": "Jogo"}.get(perna, perna)

            linhas: list[dict] = [
                {
                    "tipo": "placar",
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
                }
            ]

            for p in liberados:
                palp = cache_palpites[p["id"]]
                pj = palp["jogos"].get(jogo["id"])
                if not pj:
                    continue
                pen_row = palp["penaltis"].get(c["id"])
                palpite_pen = pen_row["penaltis_clube_id"] if pen_row else None
                pen_label = ""
                if pj["gols_mandante"] == pj["gols_visitante"] and palpite_pen in ("a", "b"):
                    pen_label = _clube_nome(c, palpite_pen)

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

                linhas.append(
                    {
                        "tipo": "palpite",
                        "nome": p["nome"],
                        "gols_m": pj["gols_mandante"],
                        "gols_v": pj["gols_visitante"],
                        "penaltis": pen_label,
                        "acertou": categoria,
                        "vencedor": "Acertou" if acertou_venc else "Errou",
                        "acertou_class": f"cell-acertou-{acertou_slug}",
                        "vencedor_class": "cell-venc-ok" if acertou_venc else "cell-venc-erro",
                    }
                )

            tabelas.append(
                {
                    "jogo_id": jogo["id"],
                    "confronto_id": c["id"],
                    "fase": c["fase"],
                    "perna": perna,
                    "perna_label": perna_label,
                    "clube_casa": clube_casa,
                    "clube_fora": clube_fora,
                    "titulo": f"{clube_casa} x {clube_fora} · {perna_label}",
                    "linhas": linhas,
                }
            )

    return tabelas
