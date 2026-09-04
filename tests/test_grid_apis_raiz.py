"""Fase 3 — APIs Raiz: iniciar / chute com partida_id / interromper."""

from __future__ import annotations

from src import db as dbmod
from src.grid_game import dia_grid, gerar_puzzle, pool_celula


def _login_grid(client, nome: str = "Raiz API", username: str = "raiz.api"):
    part = dbmod.criar_participante(nome, status="liberado")
    dbmod.definir_credenciais(part["id"], username, "senha12345")
    client.cookies.clear()
    r = client.get(f"/p/{part['token']}", follow_redirects=False)
    assert r.status_code in (200, 303)
    return part


def _clube_valido_celula0() -> dict:
    from src.grid_game import categoria_por_id

    p = gerar_puzzle(dia_grid())
    row = categoria_por_id(p["linhas"][0]["id"])
    col = categoria_por_id(p["colunas"][0]["id"])
    assert row and col
    pool = pool_celula(row, col)
    assert pool, "pool da célula 0,0 deve ter clubes"
    return pool[0]


def test_iniciar_raiz_idempotente(client):
    _login_grid(client)
    r1 = client.post("/grid/api/iniciar", json={"modo": "raiz"})
    assert r1.status_code == 200, r1.text
    data1 = r1.json()
    assert data1["modo"] == "raiz"
    assert data1["partida"]["modo"] == "raiz"
    assert data1["partida"]["iniciado_em"]
    pid = data1["partida"]["id"]

    r2 = client.post("/grid/api/iniciar", json={"modo": "raiz"})
    assert r2.status_code == 200
    assert r2.json()["partida"]["id"] == pid


def test_iniciar_raiz_nao_confunde_com_xonha(client):
    _login_grid(client, "Raiz Only", "raiz.only")
    r = client.post("/grid/api/iniciar", json={"modo": "raiz"})
    assert r.status_code == 200
    assert r.json()["modo"] == "raiz"
    assert r.json()["partida"]["modo"] == "raiz"


def test_chute_com_partida_e_interromper_bloqueia(client):
    from src.grid_game import categoria_por_id

    part = _login_grid(client, "Raiz Chute", "raiz.chute")
    ini = client.post("/grid/api/iniciar", json={"modo": "raiz"}).json()
    partida_id = ini["partida"]["id"]
    clube = _clube_valido_celula0()

    ok = client.post(
        "/grid/api/chute",
        json={
            "partida_id": partida_id,
            "linha": 0,
            "coluna": 0,
            "clube_id": clube["id"],
        },
    )
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["resultado"]["ok"] is True
    assert body["partida"]["id"] == partida_id
    assert body["celulas"][0][0]["clube"]["id"] == clube["id"]
    assert body["score_parcial"] > 0
    # Espelho legado
    prog = dbmod.get_grid_progresso(part["id"], dia_grid())
    assert prog is not None
    assert prog["celulas"][0][0]["ok"] is True

    inter = client.post(
        "/grid/api/interromper",
        json={"partida_id": partida_id},
    )
    assert inter.status_code == 200, inter.text
    assert inter.json()["partida"]["interrompido"] is True
    assert inter.json()["partida"]["celulas"][0][0]["ok"] is True

    puzzle = gerar_puzzle(dia_grid())
    pool1 = pool_celula(
        categoria_por_id(puzzle["linhas"][0]["id"]),
        categoria_por_id(puzzle["colunas"][1]["id"]),
    )
    clube2 = next(c for c in pool1 if c["id"] != clube["id"])
    blocked = client.post(
        "/grid/api/chute",
        json={
            "partida_id": partida_id,
            "linha": 0,
            "coluna": 1,
            "clube_id": clube2["id"],
        },
    )
    assert blocked.status_code == 409
    assert "encerrada" in blocked.json()["erro"].casefold()


def test_interromper_idempotente(client):
    _login_grid(client, "Raiz Inter", "raiz.inter")
    partida_id = client.post("/grid/api/iniciar", json={"modo": "raiz"}).json()[
        "partida"
    ]["id"]
    a = client.post("/grid/api/interromper", json={"partida_id": partida_id})
    b = client.post("/grid/api/interromper", json={"partida_id": partida_id})
    assert a.status_code == 200 and b.status_code == 200
    assert b.json()["partida"]["interrompido"] is True


def test_chute_legado_sem_partida_id_ainda_funciona(client):
    """Regressão: fluxo antigo sem partida_id permanece."""
    _login_grid(client, "Legado Chute", "legado.chute")
    clube = _clube_valido_celula0()
    r = client.post(
        "/grid/api/chute",
        json={"linha": 0, "coluna": 0, "clube_id": clube["id"]},
    )
    assert r.status_code == 200, r.text
    assert "progresso" in r.json()
    assert "partida" not in r.json()
