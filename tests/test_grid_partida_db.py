"""Fase 2 — schema grid_partida / passe / cutover (testes de DB)."""

from __future__ import annotations

import pytest

from src import db


def test_criar_partida_raiz_unica_por_dia(client):
    p = db.criar_participante("Grid Partida", status="liberado")
    a = db.criar_grid_partida(p["id"], "2026-09-04", modo="raiz", puzzle_salt="")
    assert a["modo"] == "raiz"
    assert a["finalizado"] is False
    assert a["interrompido"] is False
    assert a["pontos"] == 0
    assert db.contar_grid_partidas_dia(p["id"], "2026-09-04", modo="raiz") == 1
    assert db.get_grid_partida_raiz(p["id"], "2026-09-04")["id"] == a["id"]

    with pytest.raises(Exception):
        db.criar_grid_partida(p["id"], "2026-09-04", modo="raiz")


def test_criar_varias_xonha_no_mesmo_dia(client):
    p = db.criar_participante("Xonha Multi", status="liberado")
    for i in range(3):
        db.criar_grid_partida(
            p["id"], "2026-09-04", modo="xonha", puzzle_salt=f"s{i}"
        )
    assert db.contar_grid_partidas_dia(p["id"], "2026-09-04", modo="xonha") == 3
    assert db.contar_grid_partidas_dia(p["id"], "2026-09-04", modo="raiz") == 0


def test_atualizar_partida_pontos_e_dicas(client):
    p = db.criar_participante("Update Partida", status="liberado")
    part = db.criar_grid_partida(p["id"], "2026-09-04", modo="xonha", puzzle_salt="x")
    celulas = [[{"ok": True, "clube": {"id": "1", "nome": "A", "rep": 100}}]]
    dicas = [{"tipo": "contagem", "custo": 10}]
    out = db.atualizar_grid_partida(
        part["id"],
        celulas=celulas,
        dicas=dicas,
        pontos=90,
        interrompido=False,
    )
    assert out["pontos"] == 90
    assert out["dicas"] == dicas
    assert out["celulas"][0][0]["ok"] is True


def test_passe_xonha_ativo_por_data(client):
    p = db.criar_participante("Passe", status="liberado")
    assert db.grid_xonha_passe_ativo(p["id"], hoje="2026-09-04") is False
    db.liberar_grid_xonha_passe(p["id"], valido_ate="2026-10-04", liberado_por="mazeta")
    assert db.grid_xonha_passe_ativo(p["id"], hoje="2026-09-04") is True
    assert db.grid_xonha_passe_ativo(p["id"], hoje="2026-10-04") is True
    assert db.grid_xonha_passe_ativo(p["id"], hoje="2026-10-05") is False


def test_cutover_raiz_xonha_zera_progresso_uma_vez(tmp_path, monkeypatch):
    from src.config import ROOT_DIR

    monkeypatch.chdir(ROOT_DIR)
    db.DB_PATH = tmp_path / "cutover.db"
    db.init_db()
    p = db.criar_participante("Legado", status="liberado")
    db.salvar_grid_progresso(p["id"], "2026-09-01", [[]], finalizado=True)
    assert db.get_grid_progresso(p["id"], "2026-09-01") is not None

    # Simula DB antigo sem a chave de cutover: apaga a meta e reinsere progresso.
    with db.get_db() as conn:
        conn.execute("DELETE FROM meta WHERE chave = 'grid_raiz_xonha_cutover_v1'")
    db.salvar_grid_progresso(p["id"], "2026-09-01", [[]], finalizado=True)

    with db.get_db() as conn:
        db._cutover_grid_raiz_xonha_v1(conn)
    assert db.get_grid_progresso(p["id"], "2026-09-01") is None

    # Segunda vez não recria dano se alguém salvar de novo e chamar cutover.
    db.salvar_grid_progresso(p["id"], "2026-09-02", [[]], finalizado=True)
    with db.get_db() as conn:
        db._cutover_grid_raiz_xonha_v1(conn)
    assert db.get_grid_progresso(p["id"], "2026-09-02") is not None
