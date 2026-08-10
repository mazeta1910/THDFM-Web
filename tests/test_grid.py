"""THDFM Grid — puzzle diário privado (Mazeta)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from src.config import ROOT_DIR
from src.grid_game import (
    DENSIDADE_MIN,
    categoria_por_id,
    clubes_grid,
    clubes_por_id,
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


def test_vancouver_whitecaps_no_catalogo_fora_do_puzzle():
    from src.clubes_catalogo import carregar_clubes

    carregar_clubes.cache_clear()
    clubes_grid.cache_clear()
    clubes_por_id.cache_clear()

    white = next(c for c in carregar_clubes() if "Whitecaps" in c["nome"])
    assert white["uf"] == "EX"
    assert white["tem_emblema"] is True
    assert white["id_arquivo"] == "4400014"
    assert (ROOT_DIR / "data/clubes/emblemas-por-id/4400014.png").is_file()
    assert white["id"] not in {c["id"] for c in clubes_grid()}


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
    assert "/static/grid.js?v=2" in r.text
    assert 'href="/grid"' in (
        ROOT_DIR / "templates" / "partials" / "admin_sidebar.html"
    ).read_text(encoding="utf-8")
    assert 'href="/grid/ranking"' in (
        ROOT_DIR / "templates" / "partials" / "admin_sidebar.html"
    ).read_text(encoding="utf-8")
    js = (ROOT_DIR / "static" / "grid.js").read_text(encoding="utf-8")
    assert "MIN_CHARS = 3" in js

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

    # 1–2 letras não revelam lista
    curto = client.get(
        "/grid/api/buscar",
        params={"linha": 0, "coluna": 0, "q": clube["nome"][:1]},
    )
    assert curto.status_code == 200
    assert curto.json()["pronto"] is False
    assert curto.json()["itens"] == []
    assert curto.json()["min_chars"] == 3

    busca = client.get(
        "/grid/api/buscar",
        params={"linha": 0, "coluna": 0, "q": clube["nome"][:3]},
    )
    assert busca.status_code == 200
    assert busca.json()["pronto"] is True
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


def _celula_ok(clube_id: str = "1") -> dict:
    return {"ok": True, "clube": {"id": clube_id, "nome": "Clube X"}}


def test_ranking_e_stats_grid(client: TestClient):
    from src import db as dbmod

    a = dbmod.criar_participante("Grid Ace", status="liberado", celular="11991110001")
    b = dbmod.criar_participante("Grid Rookie", status="liberado", celular="11991110002")
    full = [[_celula_ok(str(i * 3 + j)) for j in range(3)] for i in range(3)]
    half = [[_celula_ok("9") if (i, j) == (0, 0) else None for j in range(3)] for i in range(3)]

    dbmod.salvar_grid_progresso(a["id"], "2026-08-08", full, finalizado=True)
    dbmod.salvar_grid_progresso(a["id"], "2026-08-09", full, finalizado=True)
    dbmod.salvar_grid_progresso(b["id"], "2026-08-09", half, finalizado=False)

    ranking = dbmod.ranking_grid(limite=10)
    assert ranking[0]["participante_id"] == a["id"]
    assert ranking[0]["dias_finalizados"] == 2
    assert ranking[0]["celulas_ok"] == 18
    assert ranking[1]["participante_id"] == b["id"]
    assert ranking[1]["dias_finalizados"] == 0
    assert ranking[1]["celulas_ok"] == 1

    stats_a = dbmod.grid_stats_participante(a["id"])
    assert stats_a["jogou"] is True
    assert stats_a["dias_finalizados"] == 2
    assert stats_a["posicao"] == 1
    assert stats_a["taxa"] == 100

    stats_b = dbmod.grid_stats_participante(b["id"])
    assert stats_b["posicao"] == 2
    assert stats_b["celulas_preenchidas"] == 1


def test_perfil_mostra_bloco_grid(client: TestClient):
    from src import db as dbmod

    part = dbmod.criar_participante("Perfil Grid", status="liberado", celular="11991110003")
    dbmod.definir_credenciais(part["id"], "perfil.grid", "senha12345")
    client.get(f"/p/{part['token']}")

    full = [[_celula_ok(str(i * 3 + j)) for j in range(3)] for i in range(3)]
    dbmod.salvar_grid_progresso(part["id"], "2026-08-09", full, finalizado=True)

    r = client.get("/meu-perfil")
    assert r.status_code == 200
    assert 'id="grid"' in r.text
    assert "THDFM Grid" in r.text
    assert "Dias zerados" in r.text
    assert 'href="/grid/ranking"' in r.text


def test_grid_ranking_page(client: TestClient):
    r = client.get("/grid/ranking", follow_redirects=False)
    assert r.status_code in (303, 302)

    from src import db as dbmod

    part = dbmod.criar_participante("Rank Viewer", status="liberado", celular="11991110004")
    dbmod.definir_credenciais(part["id"], "rank.viewer", "senha12345")
    client.get(f"/p/{part['token']}")

    full = [[_celula_ok("1") for _ in range(3)] for _ in range(3)]
    dbmod.salvar_grid_progresso(part["id"], "2026-08-09", full, finalizado=True)

    r = client.get("/grid/ranking")
    assert r.status_code == 200
    assert "Ranking" in r.text
    assert "Rank Viewer" in r.text
    assert "Dias" in r.text
