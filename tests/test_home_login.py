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
    assert 'href="/?acesso=entrar"' in text or 'data-acesso-open="entrar"' in text
    assert "home-hero-slider" in text
    assert "site-footer" in text
    assert "chat.whatsapp.com/DQX2VHp6aQl6ILcwHT7nRz" in text
    assert "Entrar no grupo" in text


def test_home_alias_tambem_renderiza(client: TestClient):
    r = client.get("/home", follow_redirects=False)
    assert r.status_code == 200
    assert "Bolão da Copa do Brasil" in r.text
    assert "PIX da inscrição" in r.text
    # Bolão é o primeiro slide (is-active no #bolao)
    bolao_pos = r.text.find('id="bolao"')
    apres_pos = r.text.find('id="apresentacao"')
    assert 0 <= bolao_pos < apres_pos
    assert 'id="bolao" aria-hidden="false"' in r.text or 'is-active" data-slide="0" id="bolao"' in r.text

def test_raiz_mostra_home_mesmo_com_sessao_participante(client: TestClient):
    part = db.criar_participante("Fulano", status="liberado", celular="11999887766")
    db.definir_credenciais(part["id"], "fulano.ok", "senha1234")
    r = client.get(f"/p/{part['token']}", follow_redirects=False)
    assert r.status_code == 200
    r2 = client.get("/", follow_redirects=False)
    assert r2.status_code == 200
    assert "Técnicos Horríveis do Futebol Mundial" in r2.text
    assert f"/p/{part['token']}" in r2.text  # link Meus Palpites no menu
    assert 'action="/conta/sair"' in r2.text
    assert "site-side-sair" in r2.text


def test_conta_sair_limpa_sessao(client: TestClient):
    part = db.criar_participante("SaiFora", status="liberado", celular="11991234567")
    db.definir_credenciais(part["id"], "sai.fora", "senha1234")
    client.get(f"/p/{part['token']}")
    r = client.post("/conta/sair", follow_redirects=False)
    assert r.status_code == 303
    assert "acesso=entrar" in r.headers["location"]
    r2 = client.get("/", follow_redirects=False)
    assert 'action="/conta/sair"' not in r2.text

def test_admin_logout_vai_para_home(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    import src.app as app_mod

    monkeypatch.setattr(app_mod, "admin_ok", lambda request: True)
    r = client.get("/admin/logout", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/"

def test_raiz_mostra_home_mesmo_com_admin_logado(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    import src.app as app_mod

    monkeypatch.setattr(app_mod, "admin_ok", lambda request: True)
    monkeypatch.setattr(app_mod, "admin_nome", lambda request: "Mazeta")
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 200
    assert "Técnicos Horríveis do Futebol Mundial" in r.text
    assert "home-hero-slider" in r.text
    assert "admin-shell" not in r.text
    assert "site-shell" in r.text
    assert 'id="ui-mode-toggle"' in r.text
    assert "ui-mode-toggle-label" in r.text

def test_token_sem_senha_abre_setup(client: TestClient):
    part = db.criar_participante("SemCred", status="liberado", celular="11999776655")
    r = client.get(f"/p/{part['token']}", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"].endswith("/credenciais")
    r2 = client.get("/", follow_redirects=False)
    assert r2.status_code == 200
    assert "Criar senha" in r2.text or "/credenciais" in r2.text

def test_login_cria_pedido_para_liberado(client: TestClient):
    part = db.criar_participante("Beltrano", status="liberado", celular="11988776655")
    r = client.post("/login", data={"celular": "(11) 98877-6655"}, follow_redirects=False)
    assert r.status_code == 303
    assert "enviado=1" in r.headers["location"]
    assert "acesso=recuperar" in r.headers["location"]
    pedidos = db.list_pedidos_recuperacao_pendentes()
    assert len(pedidos) == 1
    assert pedidos[0]["participante_id"] == part["id"]
    assert pedidos[0]["nome"] == "Beltrano"


def test_login_celular_inexistente_nao_cria_pedido(client: TestClient):
    r = client.post("/login", data={"celular": "11911112222"}, follow_redirects=False)
    assert r.status_code == 303
    assert "enviado=1" in r.headers["location"]
    assert "acesso=recuperar" in r.headers["location"]
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


def test_loguin_so_aceita_marlon(client: TestClient):
    r = client.get("/loguin")
    assert r.status_code == 200
    assert "LOGUIN" in r.text
    assert "Marlon Wietzikowski" in r.text
    assert 'data-group="marlon"' in r.text
    assert "Sub-menu exclusivo" in r.text
    assert "ortografia" not in r.text.casefold()

    r_home = client.get("/")
    assert 'data-group="marlon"' in r_home.text
    assert 'href="/loguin"' in r_home.text
    # LOGUIN saiu do grupo Portal
    portal_block = r_home.text.split('data-group="portal"', 1)[1].split("data-group=", 1)[0]
    assert 'href="/loguin"' not in portal_block
    # Entrar vive em Acesso, não misturado no Bolão
    assert 'data-group="acesso"' in r_home.text
    acesso_block = r_home.text.split('data-group="acesso"', 1)[1].split("data-group=", 1)[0]
    assert 'href="/?acesso=entrar"' in acesso_block or 'data-acesso-open="entrar"' in acesso_block
    assert "Entrar" in acesso_block
    assert 'href="/?acesso=recuperar"' in acesso_block or 'data-acesso-open="recuperar"' in acesso_block
    bolao_block = r_home.text.split('data-group="bolao"', 1)[1].split("data-group=", 1)[0]
    assert 'data-acesso-open="entrar"' not in bolao_block
    assert 'href="/inscricao"' in bolao_block
    r2 = client.post(
        "/loguin",
        data={"usuario": "João", "senha": "123"},
        follow_redirects=False,
    )
    assert r2.status_code == 303
    assert "erro=" in r2.headers["location"]
    loc2 = unquote(r2.headers["location"])
    assert "exclusivo" in loc2.casefold() or "animal" in loc2.casefold()

    r3 = client.post(
        "/loguin",
        data={"usuario": "Marlon Wietzikowski", "senha": "loguin"},
        follow_redirects=False,
    )
    assert r3.status_code == 303
    assert "sucesso=1" in r3.headers["location"]
    r4 = client.get("/loguin?sucesso=1")
    assert "LOGUIN efetuado" in r4.text


def test_marlon_nao_entra_pela_porta_certa(client: TestClient):
    part = db.criar_participante(
        "Marlon Wietzikowski", status="liberado", celular="11990001122"
    )
    db.definir_credenciais(part["id"], "marlon.w", "senha1234")

    # Pelo username civilizado → LOGUIN
    r = client.post(
        "/entrar",
        data={"usuario": "marlon.w", "senha": "senha1234"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    loc = unquote(r.headers["location"])
    assert loc.startswith("/loguin")
    assert "erro=" in loc
    assert "marlon" in loc.casefold() or "loguin" in loc.casefold()

    # Pelo nome no campo usuário → LOGUIN
    r2 = client.post(
        "/entrar",
        data={"usuario": "Marlon Wietzikowski", "senha": "qualquer"},
        follow_redirects=False,
    )
    assert r2.status_code == 303
    assert unquote(r2.headers["location"]).startswith("/loguin")

    # LOGUIN com senha certa → entra no bolão
    r3 = client.post(
        "/loguin",
        data={"usuario": "Marlon Wietzikowski", "senha": "senha1234"},
        follow_redirects=False,
    )
    assert r3.status_code == 303
    assert r3.headers["location"].startswith(f"/p/{part['token']}")

    # LOGUIN com senha errada → fica no ritual
    client.post("/conta/sair", follow_redirects=False)
    r4 = client.post(
        "/loguin",
        data={"usuario": "Marlon Wietzikowski", "senha": "errada999"},
        follow_redirects=False,
    )
    assert r4.status_code == 303
    assert "erro=" in r4.headers["location"]
    assert "/loguin" in r4.headers["location"]


def test_loguin_recusa_usuario_normal_mesmo_com_senha_valida(client: TestClient):
    part = db.criar_participante("Fulano Normal", status="liberado", celular="11991112233")
    db.definir_credenciais(part["id"], "fulano.n", "senha1234")
    r = client.post(
        "/loguin",
        data={"usuario": "fulano.n", "senha": "senha1234"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "/loguin" in r.headers["location"]
    assert "erro=" in r.headers["location"]
    # Não autenticou no bolão
    r2 = client.get(f"/p/{part['token']}/conta", follow_redirects=False)
    # Sem sessão de participante criada pelo loguin — conta exige gate/sessão ok via token URL
    # O token na URL ainda funciona; o ponto é que /loguin não setou login de fulano.
    # Garantimos só que a resposta do loguin foi erro:
    assert "exclusivo" in unquote(r.headers["location"]).casefold() or "animal" in unquote(
        r.headers["location"]
    ).casefold() or "entrar" in unquote(r.headers["location"]).casefold()