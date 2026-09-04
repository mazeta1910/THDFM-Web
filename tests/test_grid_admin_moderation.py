"""Painel Mazeta — moderação granular do Grid."""

from __future__ import annotations

from src import db as dbmod
from src.grid_game import categorias_disponiveis, dia_grid, gerar_puzzle
from src.grid_partidas import agora_iso, iniciar_raiz, iniciar_xonha, override_celula_admin
from tests.conftest import login_admin


def _login_user(client, nome: str, username: str):
    part = dbmod.criar_participante(nome, status="liberado")
    dbmod.definir_credenciais(part["id"], username, "senha12345")
    client.cookies.clear()
    client.get(f"/p/{part['token']}")
    return part


def test_admin_resumo_inclui_puzzle_salt_e_puzzles(client):
    login_admin(client)
    p = dbmod.criar_participante("Admin Hist", status="liberado")
    dia = dia_grid()
    x = iniciar_xonha(p["id"], dia)
    r = client.get(f"/grid/api/admin/resumo?dia={dia}")
    assert r.status_code == 200
    data = r.json()
    assert "puzzles" in data
    assert "" in data["puzzles"]
    row = next(x for x in data["respostas"] if x["participante_id"] == p["id"])
    assert row["puzzle_salt"] == "xonha-1"
    assert "xonha-1" in data["puzzles"]


def test_admin_override_celula_e_apagar(client):
    login_admin(client)
    p = dbmod.criar_participante("Override User", status="liberado")
    dia = dia_grid()
    part = iniciar_xonha(p["id"], dia)
    dbmod.atualizar_grid_partida(
        part["id"],
        celulas=[
            [{"ok": False, "clube": {"id": "1", "nome": "A", "rep": 1}}, None, None],
            [None, None, None],
            [None, None, None],
        ],
    )
    out = override_celula_admin(part["id"], linha=0, coluna=0, ok=True)
    assert out["celulas"][0][0]["ok"] is True
    r = client.post(
        f"/grid/api/admin/partida/{part['id']}/celula",
        json={"linha": 0, "coluna": 0, "ok": False},
    )
    assert r.status_code == 200, r.text
    assert r.json()["partida"]["celulas"][0][0]["ok"] is False
    d = client.delete(f"/grid/api/admin/partida/{part['id']}")
    assert d.status_code == 200
    assert dbmod.get_grid_partida(part["id"]) is None


def test_admin_apagar_dia_usuario(client):
    login_admin(client)
    p = dbmod.criar_participante("Wipe Day", status="liberado")
    dia = dia_grid()
    iniciar_raiz(p["id"], dia)
    iniciar_xonha(p["id"], dia)
    r = client.request(
        "DELETE",
        "/grid/api/admin/partidas-dia",
        json={"participante_id": p["id"], "dia": dia},
    )
    assert r.status_code == 200, r.text
    assert r.json()["apagados"] >= 2
    assert dbmod.listar_grid_partidas_participante(p["id"], dia) == []


def test_admin_passe_status_e_revogar(client):
    login_admin(client)
    p = dbmod.criar_participante("Passe User", status="liberado")
    g = client.get(f"/grid/api/admin/xonha-passe?participante_id={p['id']}")
    assert g.status_code == 200
    assert g.json()["ativo"] is False
    client.post(
        "/grid/api/admin/xonha-passe",
        json={"participante_id": p["id"], "dias": 30},
    )
    g2 = client.get(f"/grid/api/admin/xonha-passe?participante_id={p['id']}")
    assert g2.json()["ativo"] is True
    d = client.request(
        "DELETE",
        "/grid/api/admin/xonha-passe",
        json={"participante_id": p["id"]},
    )
    assert d.status_code == 200
    assert d.json()["ok"] is True
    assert dbmod.get_grid_xonha_passe(p["id"]) is None


def test_admin_eixo_override_e_streak(client):
    login_admin(client)
    dia = dia_grid()
    cats = list(categorias_disponiveis(dia))
    assert len(cats) >= 2
    puzzle = gerar_puzzle(dia, salt="xonha-1")
    atual = puzzle["linhas"][0]["id"]
    novo = next(c for c in cats if c.id != atual)
    r = client.post(
        "/grid/api/admin/eixo",
        json={
            "dia": dia,
            "salt": "xonha-1",
            "eixo": "linha",
            "indice": 0,
            "categoria_id": novo.id,
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["puzzle"]["linhas"][0]["id"] == novo.id
    p = dbmod.criar_participante("Streak Ov", status="liberado")
    s = client.post(
        "/grid/api/admin/streak-override",
        json={"participante_id": p["id"], "modo": "xonha", "valor": 7},
    )
    assert s.status_code == 200
    assert dbmod.grid_streak_modo(p["id"], "xonha") == 7


def test_admin_page_tem_filtros_e_drawer(client):
    login_admin(client)
    r = client.get("/grid")
    assert r.status_code == 200
    assert "data-grid-admin-busca" in r.text
    assert "data-grid-admin-drawer" in r.text
    assert "data-grid-admin-passe-revogar" in r.text
    assert "/static/grid-admin.js?v=11" in r.text
    assert "data-grid-admin-eixo-modal" in r.text
    assert "data-grid-admin-cfg-modal" in r.text
