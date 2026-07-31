"""Papéis de admin (Dono vs Moderador) e painel de credenciais."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import unquote

import pytest
from fastapi.testclient import TestClient

import src.db as db
from src.config import ROOT_DIR


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(ROOT_DIR)
    monkeypatch.setenv(
        "ADMIN_USERS",
        "mazeta=senha-dono=Mazeta:dono|ramos=senha-mod=Ramos:moderador|joaojec=senha-jec=João JEC:adminzinho",
    )
    # Recarrega parse de admins (módulo já importado lê env na chamada)
    db.DB_PATH = tmp_path / "test.db"
    (tmp_path / "avatars").mkdir(exist_ok=True)
    (tmp_path / "comprovantes").mkdir(exist_ok=True)
    db.init_db()

    from src.app import app

    with TestClient(app) as c:
        yield c


def _login_admin(client: TestClient, login: str, senha: str):
    r = client.post(
        "/admin/login",
        data={"login": login, "password": senha},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/admin"


def test_papeis_parseados(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(
        "ADMIN_USERS",
        "mazeta=x=Mazeta:dono|ramos=y=Ramos:moderador|joaojec=z=João JEC:adminzinho",
    )
    from src import admins as adm

    by_login = {a.login: a for a in adm.list_admins()}
    assert by_login["mazeta"].papel == "dono"
    assert by_login["mazeta"].is_dono
    assert by_login["ramos"].papel == "moderador"
    assert by_login["joaojec"].papel == "moderador"
    assert by_login["joaojec"].papel_label == "Moderador"


def test_admin_users_aceita_espacos_no_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(
        "ADMIN_USERS",
        " mazeta = senha-com-espaco = Mazeta:dono | ramos = outra = Ramos:moderador ",
    )
    from src import admins as adm

    by_login = {a.login: a for a in adm.list_admins()}
    assert by_login["mazeta"].senha == "senha-com-espaco"
    assert by_login["ramos"].senha == "outra"
    assert adm.autenticar_admin("mazeta", "senha-com-espaco")
    assert adm.autenticar_admin("mazeta", " senha-com-espaco ") is None


def test_toggle_aparece_apos_login_admin(client: TestClient):
    r0 = client.get("/")
    assert 'id="chrome-mode-toggle"' not in r0.text
    assert 'id="ui-mode-toggle"' not in r0.text
    assert "site-side-admin-login" not in r0.text
    assert 'href="/admin/login"' not in r0.text

    _login_admin(client, "mazeta", "senha-dono")
    r = client.get("/")
    # Só o Dono tem o atalho Usuário/Admin ao lado do tema
    assert 'id="chrome-mode-toggle"' in r.text
    assert 'id="ui-mode-toggle"' not in r.text
    assert "admin-shell" in r.text
    assert "Painel de Admin" in r.text
    assert "is-dono" in r.text
    assert "Usuário" in r.text or ">Admin<" in r.text
    assert "Ver site" not in r.text
    assert "site-side-admin-login" not in r.text
    assert "Painel (Dono)" not in r.text
    assert "site-side-admin-switch" not in r.text


def test_moderador_nao_tem_chrome_toggle(client: TestClient):
    _login_admin(client, "ramos", "senha-mod")
    r = client.get("/admin")
    assert r.status_code == 200
    assert "admin-shell" in r.text
    assert 'id="chrome-mode-toggle"' not in r.text
    assert 'id="ui-mode-toggle"' not in r.text


def test_menu_admin_um_item_ativo_por_vez(client: TestClient):
    """Credenciais não pode deixar Resultados ativo ao mesmo tempo."""
    import re

    _login_admin(client, "mazeta", "senha-dono")

    def active_admin_items(html: str) -> list[str]:
        block = html.split('data-group="admin"', 1)[1].split("data-group=", 1)[0]
        return re.findall(
            r'class="admin-side-link active"[^>]*>.*?>(Inscrições|Resultados|Palpites|Credenciais)<',
            block,
            flags=re.S,
        )

    r = client.get("/admin/credenciais")
    assert r.status_code == 200
    assert active_admin_items(r.text) == ["Credenciais"]

    r2 = client.get("/admin?sec=resultados")
    assert active_admin_items(r2.text) == ["Resultados"]

    r3 = client.get("/admin?sec=inscricoes")
    assert active_admin_items(r3.text) == ["Inscrições"]

    r4 = client.get("/admin/palpites")
    assert active_admin_items(r4.text) == ["Palpites"]


def test_classificacao_mantem_menu_admin_apos_painel(client: TestClient):
    """Depois de usar o painel, Classificação continua no menu admin."""
    _login_admin(client, "mazeta", "senha-dono")
    r_admin = client.get("/admin/palpites")
    assert r_admin.status_code == 200
    assert "admin-shell" in r_admin.text
    assert "thdfm_ui_mode=admin" in (r_admin.headers.get("set-cookie") or "")

    r = client.get("/classificacao")
    assert r.status_code == 200
    assert "admin-shell" in r.text
    assert "site-shell" not in r.text
    assert "Painel de Admin" in r.text
    assert "Classificação" in r.text


def test_admin_login_persiste_mesmo_com_outro_participante_na_sessao(client: TestClient):
    """Entrar no bolão antes não pode impedir o login admin via Entrar."""
    part = db.criar_participante("FulanoSessao", status="liberado", celular="11990009988")
    db.definir_credenciais(part["id"], "fulano.sessao", "senha1234")
    client.get(f"/p/{part['token']}")

    r = client.post(
        "/entrar",
        data={"usuario": "mazeta", "senha": "senha-dono"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/admin"
    assert "thdfm_ui_mode=admin" in (r.headers.get("set-cookie") or "")

    r2 = client.get("/admin")
    assert r2.status_code == 200
    assert "Painel de Admin" in r2.text
    assert 'id="chrome-mode-toggle"' in r2.text
    # Conta admin própria — não assalta o Fulano
    mazeta = db.get_participante_por_admin_login("mazeta")
    assert mazeta is not None
    assert mazeta["id"] != part["id"]
    assert (mazeta.get("admin_login") or "") == "mazeta"


def test_admin_login_page_redireciona_para_entrar(client: TestClient):
    r = client.get("/admin/login", follow_redirects=False)
    assert r.status_code == 303
    assert "acesso=entrar" in r.headers["location"]

    r2 = client.get("/admin", follow_redirects=False)
    assert r2.status_code == 303
    assert "acesso=entrar" in r2.headers["location"]


def test_entrar_com_credenciais_admin_abre_painel(client: TestClient):
    """mazeta + senha do .env no Entrar deve ir ao /admin (não só ao bolão)."""
    r = client.post(
        "/entrar",
        data={"usuario": "mazeta", "senha": "senha-dono"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/admin"
    assert "thdfm_ui_mode=admin" in (r.headers.get("set-cookie") or "")

    r2 = client.get("/admin")
    assert r2.status_code == 200
    assert "Painel de Admin" in r2.text
    assert 'id="chrome-mode-toggle"' in r2.text


def test_conta_vinculada_abre_painel_sem_segundo_login(client: TestClient):
    """Entrar no bolão com a conta do admin já libera /admin — sem digitar de novo."""
    _login_admin(client, "mazeta", "senha-dono")
    mazeta = db.get_participante_por_admin_login("mazeta")
    assert mazeta is not None
    db.definir_credenciais(mazeta["id"], "mazeta.bolao", "senha-bolao-99")

    # Sai de tudo e entra só pelo bolão (senha diferente da do .env)
    client.post("/conta/sair", follow_redirects=False)
    r = client.post(
        "/entrar",
        data={"usuario": "mazeta.bolao", "senha": "senha-bolao-99"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/admin"

    # Sem segundo login
    r2 = client.get("/admin", follow_redirects=False)
    assert r2.status_code == 200
    assert "Painel de Admin" in r2.text
    assert 'id="chrome-mode-toggle"' in r2.text

    home = client.get("/")
    assert "admin-shell" in home.text
    assert 'id="chrome-mode-toggle"' in home.text
    assert "Painel de Admin" in home.text


def test_sair_do_admin_limpa_tudo_e_pede_entrar(client: TestClient):
    _login_admin(client, "mazeta", "senha-dono")
    r = client.get("/admin/logout", follow_redirects=False)
    assert r.status_code == 303
    assert "acesso=entrar" in r.headers["location"]

    # Saiu de tudo — painel e bolão
    r2 = client.get("/admin", follow_redirects=False)
    assert r2.status_code == 303
    assert "acesso=entrar" in r2.headers["location"]

    home = client.get("/")
    assert "site-side-admin-login" not in home.text
    assert 'href="/admin/login"' not in home.text
    assert 'id="chrome-mode-toggle"' not in home.text
    assert 'id="ui-mode-toggle"' not in home.text
    assert 'action="/conta/sair"' not in home.text


def test_admin_mantem_menu_na_transparencia(client: TestClient):
    _login_admin(client, "mazeta", "senha-dono")
    r = client.get("/transparencia")
    assert r.status_code == 200
    assert "admin-shell" in r.text
    assert "site-shell" not in r.text
    assert "Portal da Transparência" in r.text
    assert "Painel de Admin" in r.text
    # Item ativo no menu admin
    assert "admin-side-link" in r.text
    assert "/transparencia" in r.text


def test_admin_modo_user_usa_menu_do_site(client: TestClient):
    """Só o Dono pode pré-visualizar o site; cookie user + página fora do /admin."""
    _login_admin(client, "mazeta", "senha-dono")
    # Simula o botão Site (mesmo domínio do cookie do login)
    client.cookies.set("thdfm_ui_mode", "user", domain="testserver.local")
    r = client.get("/transparencia")
    assert r.status_code == 200
    assert "site-shell" in r.text
    assert "admin-shell" not in r.text
    assert "Portal da Transparência" in r.text
    assert 'id="chrome-mode-toggle"' in r.text
    assert "Sair do admin" not in r.text
    assert "Painel (Dono)" not in r.text
    assert "site-side-admin-switch" not in r.text
    assert "site-side-sair" in r.text

    # Voltar ao painel restaura o chrome admin nas páginas do site
    r_admin = client.get("/admin")
    assert "admin-shell" in r_admin.text
    r2 = client.get("/classificacao")
    assert "admin-shell" in r2.text
    assert "site-shell" not in r2.text


def test_dono_acessa_credenciais_e_redefine(client: TestClient):
    part = db.criar_participante("Fulano", status="liberado", celular="11990001122")
    db.definir_credenciais(part["id"], "fulano.ok", "antiga123")

    _login_admin(client, "mazeta", "senha-dono")
    r = client.get("/admin/credenciais")
    assert r.status_code == 200
    assert "fulano.ok" in r.text
    assert "Gestão de credenciais" in r.text

    r2 = client.post(
        "/admin/credenciais/redefinir",
        data={
            "participante_id": part["id"],
            "username": "fulano.ok",
            "senha_nova": "nova45678",
        },
        follow_redirects=False,
    )
    assert r2.status_code == 303
    assert "credenciais" in r2.headers["location"].casefold()
    assert db.autenticar_por_username("fulano.ok", "nova45678")
    assert db.autenticar_por_username("fulano.ok", "antiga123") is None


def test_moderador_nao_acessa_credenciais_nem_apagar(client: TestClient):
    part = db.criar_participante("Alvo", status="liberado", celular="11991112233")
    db.definir_credenciais(part["id"], "alvo.ok", "senha1234")

    _login_admin(client, "ramos", "senha-mod")
    r = client.get("/admin/credenciais", follow_redirects=False)
    assert r.status_code == 303
    assert "admin" in r.headers["location"]
    loc = unquote(r.headers["location"]).casefold()
    assert "dono" in loc or "erro" in loc

    r2 = client.post(
        "/admin/apagar",
        data={"participante_id": part["id"]},
        follow_redirects=False,
    )
    assert r2.status_code == 303
    assert db.get_participante(part["id"]) is not None

    r3 = client.get("/admin")
    assert "is-moderador" in r3.text
    nav = r3.text.split("admin-side-nav", 1)[-1].split("admin-side-sair", 1)[0]
    assert "/admin/credenciais" not in nav or "Credenciais" not in nav
