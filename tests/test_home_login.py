"""Home, login e recuperação de link."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote

import pytest
from fastapi.testclient import TestClient

import src.db as db
from src.config import ROOT_DIR


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(ROOT_DIR)
    db.DB_PATH = tmp_path / "test.db"
    (tmp_path / "avatars").mkdir(exist_ok=True)
    (tmp_path / "comprovantes").mkdir(exist_ok=True)
    db.init_db()

    from src.app import app

    with TestClient(app) as c:
        yield c


def test_raiz_mostra_home_para_visitante(client: TestClient):
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 200
    text = r.text
    assert "THDFM" in text
    assert "Técnicos Horríveis do Futebol Mundial" in text
    assert "Site em desenvolvimento" in text
    assert "Fazer inscrição" in text
    assert "Já fiz a inscrição" in text
    assert "home-hero-slider" in text
    assert "site-footer" in text


def test_home_alias_tambem_renderiza(client: TestClient):
    r = client.get("/home", follow_redirects=False)
    assert r.status_code == 200
    assert "Bolão da Copa do Brasil" in r.text
    assert "PIX da inscrição" in r.text

def test_raiz_mostra_home_mesmo_com_sessao_participante(client: TestClient):
    part = db.criar_participante("Fulano", status="liberado", celular="11999887766")
    r = client.get(f"/p/{part['token']}", follow_redirects=False)
    assert r.status_code == 200
    r2 = client.get("/", follow_redirects=False)
    assert r2.status_code == 200
    assert "Técnicos Horríveis do Futebol Mundial" in r2.text
    assert f"/p/{part['token']}" in r2.text  # link Meus Palpites no menu


def test_login_cria_pedido_para_liberado(client: TestClient):
    part = db.criar_participante("Beltrano", status="liberado", celular="11988776655")
    r = client.post("/login", data={"celular": "(11) 98877-6655"}, follow_redirects=False)
    assert r.status_code == 303
    assert "enviado=1" in r.headers["location"]
    pedidos = db.list_pedidos_recuperacao_pendentes()
    assert len(pedidos) == 1
    assert pedidos[0]["participante_id"] == part["id"]
    assert pedidos[0]["nome"] == "Beltrano"


def test_login_celular_inexistente_nao_cria_pedido(client: TestClient):
    r = client.post("/login", data={"celular": "11911112222"}, follow_redirects=False)
    assert r.status_code == 303
    assert "enviado=1" in r.headers["location"]
    assert db.list_pedidos_recuperacao_pendentes() == []


def test_login_pendente_nao_cria_pedido(client: TestClient):
    db.criar_participante("Pendente", status="pendente", celular="11977665544")
    r = client.post("/login", data={"celular": "11977665544"}, follow_redirects=False)
    assert r.status_code == 303
    assert db.list_pedidos_recuperacao_pendentes() == []


def test_login_rate_limit(client: TestClient):
    db.criar_participante("Rate", status="liberado", celular="11966554433")
    for _ in range(3):
        r = client.post("/login", data={"celular": "11966554433"}, follow_redirects=False)
        assert r.status_code == 303
    assert len(db.list_pedidos_recuperacao_pendentes()) == 3
    r = client.post("/login", data={"celular": "11966554433"}, follow_redirects=False)
    assert r.status_code == 303
    assert "enviado=1" in r.headers["location"]
    assert len(db.list_pedidos_recuperacao_pendentes()) == 3


def test_admin_atender_recuperacao(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    import src.app as app_mod

    part = db.criar_participante("Zap", status="liberado", celular="11955443322")
    pedido_id = db.criar_pedido_recuperacao(part["id"], "11955443322", ip="1.2.3.4")

    monkeypatch.setattr(app_mod, "admin_ok", lambda request: True)

    r = client.get(f"/admin/recuperacao/{pedido_id}/atender", follow_redirects=False)
    assert r.status_code == 303
    loc = unquote(r.headers["location"])
    assert "wa.me/5511955443322" in loc
    assert f"/p/{part['token']}" in loc
    assert db.list_pedidos_recuperacao_pendentes() == []
    updated = db.get_participante(part["id"])
    assert updated and updated.get("link_enviado_em")
