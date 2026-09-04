"""Fase 5–6 — ranking por modo, UI markers, passe admin."""

from __future__ import annotations

from src import db as dbmod
from src.grid_game import dia_grid
from src.grid_partidas import iniciar_raiz, iniciar_xonha
from src.grid_score import pontos_partida
from tests.conftest import login_admin


def test_ranking_grid_modo_score_unico(client):
    a = dbmod.criar_participante("Rank A", status="liberado")
    b = dbmod.criar_participante("Rank B", status="liberado")
    dia = dia_grid()
    pa = iniciar_raiz(a["id"], dia)
    pb = iniciar_raiz(b["id"], dia)
    # A com mais pontos artificiais
    dbmod.atualizar_grid_partida(pa["id"], pontos=500, finalizado=True, celulas=[[{"ok": True, "clube": {"id": "1", "nome": "X", "rep": 100}}]])
    dbmod.atualizar_grid_partida(pb["id"], pontos=100, finalizado=True, celulas=[[{"ok": True, "clube": {"id": "2", "nome": "Y", "rep": 100}}]])
    rank = dbmod.ranking_grid_modo("raiz", limite=10)
    assert rank
    assert rank[0]["participante_id"] == a["id"]
    assert rank[0]["score"] >= rank[1]["score"]
    assert "score" in rank[0]


def test_grid_page_tem_modos_e_rankings(client):
    r = client.get("/grid")
    assert r.status_code == 200
    assert 'data-grid-mode="raiz"' in r.text
    assert 'data-grid-mode="xonha"' in r.text
    assert "Pro" in r.text
    assert "Contínuo" in r.text
    assert "data-grid-live-score" in r.text
    assert "grid-hero-block" in r.text
    assert "grid-toolbar" in r.text
    assert "data-grid-warn-modal" in r.text
    assert 'data-rank-modo="xonha"' in r.text
    assert "data-grid-rank-panel" in r.text
    assert "Detalhes" in r.text
    assert "/static/grid.js?v=22" in r.text
    assert "Modo Pro" in r.text
    assert "Modo Raiz" not in r.text

def test_admin_libera_passe_xonha(client):
    part = dbmod.criar_participante("Passe UI", status="liberado")
    login_admin(client)
    r = client.post(
        "/grid/api/admin/xonha-passe",
        json={"participante_id": part["id"], "dias": 30},
    )
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True
    assert dbmod.grid_xonha_passe_ativo(part["id"]) is True


def test_xonha_ranking_separado(client):
    p = dbmod.criar_participante("Xonha Rank", status="liberado")
    dia = dia_grid()
    part = iniciar_xonha(p["id"], dia)
    dbmod.atualizar_grid_partida(
        part["id"],
        pontos=222,
        finalizado=True,
        celulas=[[{"ok": True, "clube": {"id": "9", "nome": "Z", "rep": 400}}]],
    )
    rx = dbmod.ranking_grid_modo("xonha")
    rr = dbmod.ranking_grid_modo("raiz")
    assert any(x["participante_id"] == p["id"] for x in rx)
    assert not any(x["participante_id"] == p["id"] for x in rr)
