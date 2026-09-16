"""Páginas públicas de perfil do Acervo (clube e competição)."""

from __future__ import annotations

from fastapi.testclient import TestClient

import src.db as db


def _cenario():
    comp = db.criar_acervo_competicao(
        "Campeonato Série A", ambito="nacional", cobertura="completa"
    )
    fla = db.criar_acervo_clube("Athletico Paranaense", uf="PR")
    gal = db.criar_acervo_clube("Atlético Mineiro", uf="MG")
    ed = db.criar_acervo_edicao(
        comp["id"], 2024, campeao_clube_id=fla["id"], vice_clube_id=gal["id"]
    )
    db.upsert_acervo_classificacao(
        ed["id"], clube_id=fla["id"], posicao=1, v=20, e=8, d=10, gp=60, gc=40, auto=True
    )
    db.upsert_acervo_classificacao(
        ed["id"], clube_id=gal["id"], posicao=2, v=19, e=9, d=10, gp=55, gc=38, auto=True
    )
    return comp, fla, gal, ed


def test_helpers_titulos_e_participacoes(client: TestClient):
    comp, fla, gal, ed = _cenario()

    titulos = db.list_acervo_titulos_clube(fla["id"])
    assert len(titulos) == 1
    assert titulos[0]["papel"] == "campeao"
    assert titulos[0]["ano"] == 2024
    assert titulos[0]["competicao_slug"] == comp["slug"]

    titulos_gal = db.list_acervo_titulos_clube(gal["id"])
    assert titulos_gal[0]["papel"] == "vice"

    parts = db.list_acervo_participacoes_clube(fla["id"])
    assert len(parts) == 1
    assert parts[0]["posicao"] == 1
    assert parts[0]["pts"] == 68  # 20*3 + 8
    assert parts[0]["competicao_nome"] == "Campeonato Série A"


def test_pagina_clube_publica(client: TestClient):
    comp, fla, gal, ed = _cenario()

    r = client.get(f"/acervo/clube/{fla['id']}")
    assert r.status_code == 200
    assert "Athletico Paranaense" in r.text
    assert "Campeão" in r.text
    # Link para a competição e para a tabela (participações)
    assert f'/acervo/competicao/{comp["slug"]}' in r.text
    assert "Participações" in r.text
    assert "2024" in r.text


def test_pagina_competicao_publica(client: TestClient):
    comp, fla, gal, ed = _cenario()

    r = client.get(f"/acervo/competicao/{comp['slug']}")
    assert r.status_code == 200
    assert "Campeonato Série A" in r.text
    assert "Athletico Paranaense" in r.text
    assert "Atlético Mineiro" in r.text
    # Campeão e vice linkam para as páginas dos clubes
    assert f'/acervo/clube/{fla["id"]}' in r.text
    assert f'/acervo/clube/{gal["id"]}' in r.text


def test_paginas_inexistentes_dao_404(client: TestClient):
    assert client.get("/acervo/clube/999999").status_code == 404
    assert client.get("/acervo/competicao/nao-existe").status_code == 404


def test_nomes_no_admin_linkam_para_paginas(client: TestClient):
    from tests.conftest import login_admin

    comp, fla, gal, ed = _cenario()
    login_admin(client, "mazeta", "senha-dono")

    r = client.get("/admin/acervo?sec=clubes")
    assert f'href="/acervo/clube/{fla["id"]}"' in r.text

    r = client.get("/admin/acervo?sec=competicoes")
    assert f'href="/acervo/competicao/{comp["slug"]}"' in r.text

    r = client.get("/admin/acervo?sec=edicoes")
    assert f'href="/acervo/clube/{fla["id"]}"' in r.text
    assert f'href="/acervo/competicao/{comp["slug"]}"' in r.text
