"""Papéis de admin (Dono vs Moderador) e painel de credenciais."""

from __future__ import annotations

import os
from urllib.parse import unquote

import pytest
from fastapi.testclient import TestClient

import src.db as db
from tests.conftest import login_admin as _login_admin
from src.config import ROOT_DIR


@pytest.fixture()
def admin_users():
    return "mazeta=senha-dono=Mazeta:dono|ramos=senha-mod=Ramos:moderador|joaojec=senha-jec=João JEC:adminzinho"


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
        # Grupo Admin vai até o próximo grupo de topo (Bolão / data-group=competicao)
        block = html.split('data-group="admin"', 1)[1].split(
            'data-group="competicao"', 1
        )[0]
        return re.findall(
            r'class="admin-side-link active"[^>]*>.*?>(Inscrições|Resultados|Palpites|Credenciais|Quem palpitou)<',
            block,
            flags=re.S,
        )

    r = client.get("/admin/credenciais")
    assert r.status_code == 200
    assert active_admin_items(r.text) == ["Credenciais"]
    assert 'data-group="admin-participantes"' in r.text
    assert 'data-group="admin-competicao"' in r.text

    r2 = client.get("/admin?sec=resultados")
    assert active_admin_items(r2.text) == ["Resultados"]

    r3 = client.get("/admin?sec=inscricoes")
    assert active_admin_items(r3.text) == ["Inscrições"]

    r4 = client.get("/admin/palpites")
    assert active_admin_items(r4.text) == ["Palpites"]

    r5 = client.get("/admin/cobranca")
    assert active_admin_items(r5.text) == ["Quem palpitou"]

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

@pytest.mark.parametrize(
    "login,senha,username_bolao,celular",
    [
        ("ramos", "senha-mod", "ramos", "11998887701"),
        ("joaojec", "senha-jec", "joaojec", "11998887702"),
    ],
)
def test_moderador_um_login_basta(
    client: TestClient, login: str, senha: str, username_bolao: str, celular: str
):
    """Ramos/JV: Entrar com a conta do bolão (mesmo username do .env) abre o painel."""
    # Conta de bolão com username = login do .env, senha diferente
    part = db.criar_participante(
        f"Conta {login}", status="liberado", celular=celular
    )
    db.definir_credenciais(part["id"], username_bolao, "senha-bolao-mod")

    r = client.post(
        "/entrar",
        data={"usuario": username_bolao, "senha": "senha-bolao-mod"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/admin"

    r2 = client.get("/admin", follow_redirects=False)
    assert r2.status_code == 200
    assert "Painel de Admin" in r2.text
    assert "admin-shell" in r2.text

    vinculado = db.get_participante_por_admin_login(login)
    assert vinculado is not None
    assert vinculado["id"] == part["id"]

@pytest.mark.parametrize("login,senha", [("ramos", "senha-mod"), ("joaojec", "senha-jec")])
def test_entrar_credenciais_env_moderador_abre_painel(
    client: TestClient, login: str, senha: str
):
    r = client.post(
        "/entrar",
        data={"usuario": login, "senha": senha},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/admin"
    r2 = client.get("/admin")
    assert r2.status_code == 200
    assert "Painel de Admin" in r2.text
    assert "is-moderador" in r2.text
    assert 'id="chrome-mode-toggle"' not in r2.text

def test_admin_sidebar_sem_item_listra_permissoes(client: TestClient):
    _login_admin(client, "mazeta", "senha-dono")
    r = client.get("/admin")
    assert r.status_code == 200
    assert "Listra · Permissões" not in r.text
    assert 'href="/admin/listra"' not in r.text
    assert 'href="/grupo/listra"' in r.text
    # Gestor/permissões continuam acessíveis pela página da Listra
    r2 = client.get("/grupo/listra")
    assert "/admin/listra" in r2.text
    assert "Gestor de meliantes" in r2.text

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
    assert "data-cred-busca" in r.text
    assert "data-cred-ir" in r.text
    assert "cred-dono-save" in r.text
    assert "Redefinir e anotar no Zap" not in r.text
    css = (ROOT_DIR / "static" / "style.css").read_text(encoding="utf-8")
    assert "grid-template-columns: repeat(auto-fill" in css
    assert ".cred-dono-page {\n  max-width: 1100px;" in css or "max-width: 1100px" in css

    r2 = client.post(
        "/admin/credenciais/redefinir",
        data={
            "participante_id": part["id"],
            "acao": "senha",
            "senha_nova": "nova45678",
        },
        follow_redirects=False,
    )
    assert r2.status_code == 303
    assert "credenciais" in r2.headers["location"].casefold()
    assert "senha" in unquote(r2.headers["location"]).casefold()
    assert db.autenticar_por_username("fulano.ok", "nova45678")
    assert db.autenticar_por_username("fulano.ok", "antiga123") is None

    r3 = client.post(
        "/admin/credenciais/redefinir",
        data={
            "participante_id": part["id"],
            "acao": "username",
            "username": "fulano.novo",
        },
        follow_redirects=False,
    )
    assert r3.status_code == 303
    assert "username" in unquote(r3.headers["location"]).casefold()
    assert db.autenticar_por_username("fulano.novo", "nova45678")
    assert db.get_participante(part["id"])["username"] == "fulano.novo"
    # Senha permanece ao mudar só o username
    assert db.autenticar_por_username("fulano.ok", "nova45678") is None

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
