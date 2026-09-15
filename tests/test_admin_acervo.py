"""Admin Acervo — painel Mazeta (HTTP)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.conftest import login_admin


@pytest.fixture()
def admin_users():
    return (
        "mazeta=senha-dono=Mazeta:dono|"
        "ramos=senha-mod=Ramos:moderador"
    )


def test_acervo_exige_login(client: TestClient):
    r = client.get("/admin/acervo", follow_redirects=False)
    assert r.status_code == 303
    assert "acesso=entrar" in (r.headers.get("location") or "")


def test_acervo_so_mazeta(client: TestClient):
    login_admin(client, "ramos", "senha-mod")
    r = client.get("/admin/acervo", follow_redirects=False)
    assert r.status_code == 303
    assert "/admin?erro=" in (r.headers.get("location") or "")


def test_acervo_fluxo_crud_http(client: TestClient):
    login_admin(client, "mazeta", "senha-dono")

    r = client.get("/admin/acervo")
    assert r.status_code == 200
    assert "Acervo" in r.text
    assert 'href="/admin/acervo"' in r.text
    assert "Novo clube" in r.text

    r = client.post(
        "/admin/acervo/clubes/salvar",
        data={
            "nome": "São Raimundo-RR",
            "nome_popular": "São Raimundo",
            "uf": "RR",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "sec=clubes" in r.headers["location"]
    assert "msg=" in r.headers["location"]

    r = client.post(
        "/admin/acervo/competicoes/salvar",
        data={
            "nome": "Campeonato Roraimense",
            "ambito": "estadual",
            "uf": "RR",
            "cobertura": "campeao_apenas",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "sec=competicoes" in r.headers["location"]

    # IDs via listagens no HTML da seção edições
    r = client.get("/admin/acervo?sec=edicoes")
    assert r.status_code == 200
    assert "Campeonato Roraimense" in r.text
    assert "São Raimundo-RR" in r.text

    import src.db as db

    clubes = db.list_acervo_clubes()
    comps = db.list_acervo_competicoes()
    assert len(clubes) == 1
    assert len(comps) == 1

    r = client.post(
        "/admin/acervo/edicoes/salvar",
        data={
            "competicao_id": str(comps[0]["id"]),
            "ano": "2024",
            "campeao_clube_id": str(clubes[0]["id"]),
            "fonte_url": "https://example.com/rr-2024",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "sec=edicoes" in r.headers["location"]

    r = client.get("/admin/acervo?sec=edicoes")
    assert "2024" in r.text
    assert "São Raimundo-RR" in r.text
    assert "1</strong> edições" in r.text or ">1</strong> edições" in r.text

    eds = db.list_acervo_edicoes()
    assert len(eds) == 1
    r = client.post(
        "/admin/acervo/edicoes/apagar",
        data={"id": str(eds[0]["id"])},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert db.list_acervo_edicoes() == []


def test_acervo_classificacao_http(client: TestClient):
    login_admin(client, "mazeta", "senha-dono")
    import src.db as db

    clube = db.criar_acervo_clube("GAS", uf="RR")
    outro = db.criar_acervo_clube("Náutico-RR", uf="RR")
    comp = db.criar_acervo_competicao(
        "Roraimense", ambito="estadual", uf="RR", cobertura="parcial"
    )
    ed = db.criar_acervo_edicao(comp["id"], 2023, campeao_clube_id=clube["id"])

    r = client.get(f"/admin/acervo?sec=edicoes&edicao_id={ed['id']}")
    assert r.status_code == 200
    assert "Tabela ·" in r.text
    assert "Roraimense 2023" in r.text

    r = client.post(
        "/admin/acervo/classificacao/salvar",
        data={
            "edicao_id": str(ed["id"]),
            "clube_id": str(clube["id"]),
            "posicao": "1",
            "pts": "12",
            "j": "4",
            "v": "4",
            "e": "0",
            "d": "0",
            "gp": "10",
            "gc": "2",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert f"edicao_id={ed['id']}" in r.headers["location"]

    r = client.post(
        "/admin/acervo/classificacao/salvar",
        data={
            "edicao_id": str(ed["id"]),
            "clube_id": str(outro["id"]),
            "posicao": "2",
            "pts": "6",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303

    r = client.get(f"/admin/acervo?sec=edicoes&edicao_id={ed['id']}")
    assert "GAS" in r.text
    assert "Náutico-RR" in r.text
    assert db.get_acervo_edicao(ed["id"])["tem_tabela"] is True

    rows = db.list_acervo_classificacao(ed["id"])
    r = client.post(
        "/admin/acervo/classificacao/apagar",
        data={"id": str(rows[1]["id"]), "edicao_id": str(ed["id"])},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert len(db.list_acervo_classificacao(ed["id"])) == 1

    r = client.post(
        "/admin/acervo/classificacao/limpar",
        data={"edicao_id": str(ed["id"])},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert db.list_acervo_classificacao(ed["id"]) == []
    assert db.get_acervo_edicao(ed["id"])["tem_tabela"] is False
