"""THDFM Grid — puzzle diário privado (Mazeta)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from src.config import ROOT_DIR
from src.grid_game import (
    DENSIDADE_MIN,
    categoria_por_id,
    clubes_grid,
    gerar_puzzle,
    pool_celula,
    validar_chute,
)
from tests.conftest import login_admin


def test_gerar_puzzle_deterministico_e_denso():
    a = gerar_puzzle("2026-08-10")
    b = gerar_puzzle("2026-08-10")
    assert a == b
    assert a["tamanho"] == 3
    assert len(a["linhas"]) == 3
    assert len(a["colunas"]) == 3
    for row in a["densidades"]:
        assert all(n >= DENSIDADE_MIN for n in row)


def test_grid_exige_login(client: TestClient):
    r = client.get("/grid", follow_redirects=False)
    assert r.status_code in (303, 302)


def test_grid_bloqueia_nao_mazeta(client: TestClient, monkeypatch):
    login_admin(client)
    monkeypatch.setattr("src.app.is_mazeta", lambda request: False)
    r = client.get("/grid", follow_redirects=False)
    assert r.status_code in (303, 302)
    assert "/admin" in (r.headers.get("location") or "")
    api = client.get("/grid/api/hoje")
    assert api.status_code == 403


def test_grid_mazeta_fluxo(client: TestClient):
    login_admin(client)
    r = client.get("/grid")
    assert r.status_code == 200
    assert "THDFM Grid" in r.text
    assert "Prévia privada" in r.text
    assert 'id="thdfm-grid"' in r.text
    assert "/static/grid.js?v=1" in r.text
    assert 'href="/grid"' in (
        ROOT_DIR / "templates" / "partials" / "admin_sidebar.html"
    ).read_text(encoding="utf-8")

    hoje = client.get("/grid/api/hoje")
    assert hoje.status_code == 200
    data = hoje.json()
    assert data["puzzle"]["tamanho"] == 3
    assert data["pode_salvar"] is True

    puzzle = data["puzzle"]
    row = categoria_por_id(puzzle["linhas"][0]["id"])
    col = categoria_por_id(puzzle["colunas"][0]["id"])
    assert row and col
    clube = pool_celula(row, col)[0]

    busca = client.get(
        "/grid/api/buscar",
        params={"linha": 0, "coluna": 0, "q": clube["nome"][:3]},
    )
    assert busca.status_code == 200
    assert busca.json()["total"] >= DENSIDADE_MIN
    assert any(x["id"] == clube["id"] for x in busca.json()["itens"])

    chute = client.post(
        "/grid/api/chute",
        json={"linha": 0, "coluna": 0, "clube_id": clube["id"]},
    )
    assert chute.status_code == 200
    body = chute.json()
    assert body["resultado"]["ok"] is True
    assert body["celulas"][0][0]["clube"]["id"] == clube["id"]

    chute2 = client.post(
        "/grid/api/chute",
        json={"linha": 0, "coluna": 0, "clube_id": clube["id"]},
    )
    assert chute2.status_code == 409


def test_chute_errado_marca_miss():
    puzzle = gerar_puzzle("2026-08-15")
    row = categoria_por_id(puzzle["linhas"][0]["id"])
    col = categoria_por_id(puzzle["colunas"][0]["id"])
    assert row and col
    pool_ids = {c["id"] for c in pool_celula(row, col)}
    outro = next(c for c in clubes_grid() if c["id"] not in pool_ids)
    res = validar_chute(dia="2026-08-15", linha=0, coluna=0, clube_id=outro["id"])
    assert res["ok"] is False
