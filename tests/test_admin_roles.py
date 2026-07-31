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


def test_toggle_aparece_apos_login_admin(client: TestClient):
    r0 = client.get("/")
    assert 'id="ui-mode-toggle"' not in r0.text
    assert 'id="ui-mode-chip-fixed"' not in r0.text

    _login_admin(client, "mazeta", "senha-dono")
    r = client.get("/")
    assert 'id="ui-mode-toggle"' in r.text
    assert 'id="ui-mode-chip-fixed"' in r.text
    assert "ui-mode-chip--fixed" in r.text
    assert "admin-shell" in r.text
    assert "Painel de Admin" in r.text
    assert "is-dono" in r.text
    assert "Ver site" in r.text


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
    _login_admin(client, "mazeta", "senha-dono")
    client.cookies.set("thdfm_ui_mode", "user")
    r = client.get("/transparencia")
    assert r.status_code == 200
    assert "site-shell" in r.text
    assert "admin-shell" not in r.text
    assert "Portal da Transparência" in r.text


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
    assert "/admin/credenciais" not in r3.text or "Credenciais" not in r3.text.split("admin-side-nav", 1)[-1].split("Ver site", 1)[0]
