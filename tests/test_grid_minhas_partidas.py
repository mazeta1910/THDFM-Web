"""APIs Minhas tentativas (dono)."""

from __future__ import annotations

from src import db as dbmod
from src.grid_game import dia_grid
from src.grid_partidas import agora_iso, iniciar_raiz, iniciar_xonha


def _login(client, nome: str, username: str):
    part = dbmod.criar_participante(nome, status="liberado")
    dbmod.definir_credenciais(part["id"], username, "senha12345")
    client.cookies.clear()
    r = client.get(f"/p/{part['token']}", follow_redirects=False)
    assert r.status_code in (200, 303)
    return part


def test_minhas_partidas_exige_login(client):
    client.cookies.clear()
    r = client.get("/grid/api/minhas-partidas")
    assert r.status_code == 401


def test_minhas_partidas_lista_do_dono(client):
    a = _login(client, "Hist A", "hist.a")
    dia = dia_grid()
    pro = iniciar_raiz(a["id"], dia)
    dbmod.atualizar_grid_partida(
        pro["id"],
        finalizado=True,
        pontos=100,
        iniciado_em=agora_iso(),
        celulas=[[{"ok": True, "clube": {"id": "1", "nome": "A", "rep": 1}}]],
    )
    x1 = iniciar_xonha(a["id"], dia)
    dbmod.atualizar_grid_partida(
        x1["id"],
        finalizado=True,
        pontos=50,
        iniciado_em=agora_iso(),
        celulas=[[{"ok": False, "clube": {"id": "2", "nome": "B", "rep": 1}}]],
    )
    r = client.get(f"/grid/api/minhas-partidas?dia={dia}")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["dia"] == dia
    assert len(data["partidas"]) == 2
    rotulos = {p["modo_rotulo"] for p in data["partidas"]}
    assert "Pro" in rotulos
    assert "Contínuo 1" in rotulos
    assert any(d["dia"] == dia for d in data["dias"])

    b = dbmod.criar_participante("Hist B", status="liberado")
    dbmod.definir_credenciais(b["id"], "hist.b", "senha12345")
    iniciar_xonha(b["id"], dia)
    r2 = client.get(f"/grid/api/minhas-partidas?dia={dia}")
    assert len(r2.json()["partidas"]) == 2


def test_partida_dono_e_alheia(client):
    a = _login(client, "Dono P", "dono.p")
    dia = dia_grid()
    part = iniciar_xonha(a["id"], dia)
    ok = client.get(f"/grid/api/partida/{part['id']}")
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["partida"]["id"] == part["id"]
    assert body["puzzle"]["modo"] == "xonha"
    assert body["partida"]["modo_rotulo"] == "Contínuo 1"

    client.cookies.clear()
    _login(client, "Outro P", "outro.p")
    neg = client.get(f"/grid/api/partida/{part['id']}")
    assert neg.status_code == 404


def test_grid_page_tem_minhas_tentativas(client):
    _login(client, "UI Minhas", "ui.minhas")
    r = client.get("/grid")
    assert r.status_code == 200
    assert "data-grid-minhas" in r.text
    assert "Minhas tentativas" in r.text
    assert "data-grid-hist-modal" in r.text
    assert "/static/grid.js?v=39" in r.text
