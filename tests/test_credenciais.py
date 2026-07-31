"""Username/senha: setup obrigatório, /entrar e rate limit."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote

import pytest
from fastapi.testclient import TestClient

import src.app as app_mod
import src.db as db
from src.config import ROOT_DIR


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(ROOT_DIR)
    db.DB_PATH = tmp_path / "test.db"
    (tmp_path / "avatars").mkdir(exist_ok=True)
    (tmp_path / "comprovantes").mkdir(exist_ok=True)
    db.init_db()
    app_mod._AUTH_ATTEMPTS.clear()

    from src.app import app

    with TestClient(app) as c:
        yield c


def test_liberado_sem_credenciais_e_obrigado_a_criar(client: TestClient):
    part = db.criar_participante("SemSenha", status="liberado", celular="11999001122")
    r = client.get(f"/p/{part['token']}", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"].endswith("/credenciais")

    r2 = client.get(f"/p/{part['token']}/credenciais")
    assert r2.status_code == 200
    assert "Crie seu username e senha" in r2.text

    r3 = client.get(f"/p/{part['token']}/conta", follow_redirects=False)
    assert r3.status_code == 303
    assert "/credenciais" in r3.headers["location"]


def test_setup_credenciais_e_entrar(client: TestClient):
    part = db.criar_participante("ComSenha", status="liberado", celular="11999003344")
    r = client.post(
        f"/p/{part['token']}/credenciais",
        data={
            "usuario": "com.senha",
            "senha": "secreta12",
            "senha2": "secreta12",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert f"/p/{part['token']}" in r.headers["location"]
    assert "msg=" in r.headers["location"]

    updated = db.get_participante(part["id"])
    assert updated
    assert updated["username"] == "com.senha"
    assert updated["password_hash"]
    assert updated["credenciais_em"]

    r_palpites = client.get(f"/p/{part['token']}", follow_redirects=False)
    assert r_palpites.status_code == 200

    client.post("/conta/sair", follow_redirects=False)

    bad = client.post(
        "/entrar",
        data={"usuario": "com.senha", "senha": "errada999"},
        follow_redirects=False,
    )
    assert bad.status_code == 303
    assert "erro=" in bad.headers["location"]

    ok = client.post(
        "/entrar",
        data={"usuario": "Com.Senha", "senha": "secreta12"},
        follow_redirects=False,
    )
    assert ok.status_code == 303
    assert ok.headers["location"] == f"/p/{part['token']}"


def test_username_duplicado_rejeitado(client: TestClient):
    a = db.criar_participante("Alpha", status="liberado", celular="11999005566")
    b = db.criar_participante("Beta", status="liberado", celular="11999007788")
    db.definir_credenciais(a["id"], "mesmo.user", "senha1234")

    r = client.post(
        f"/p/{b['token']}/credenciais",
        data={
            "usuario": "Mesmo.User",
            "senha": "outrasenha",
            "senha2": "outrasenha",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    loc = unquote(r.headers["location"])
    assert "erro=" in loc
    assert "já está em uso" in loc.casefold() or "em uso" in loc.casefold()
    assert db.precisa_credenciais(db.get_participante(b["id"]))


def test_senha_curta_e_confirmacao(client: TestClient):
    part = db.criar_participante("Curta", status="liberado", celular="11999009900")
    r = client.post(
        f"/p/{part['token']}/credenciais",
        data={"usuario": "curta.ok", "senha": "curta", "senha2": "curta"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "erro=" in r.headers["location"]

    r2 = client.post(
        f"/p/{part['token']}/credenciais",
        data={
            "usuario": "curta.ok",
            "senha": "senha1234",
            "senha2": "senha9999",
        },
        follow_redirects=False,
    )
    assert r2.status_code == 303
    assert "não conferem" in unquote(r2.headers["location"]).casefold()


def test_pendente_nao_e_forcado_a_credenciais(client: TestClient):
    part = db.criar_participante("PendenteX", status="pendente", celular="11999112233")
    r = client.get(f"/p/{part['token']}", follow_redirects=False)
    assert r.status_code == 200
    assert "credenciais" not in (r.headers.get("location") or "")


def test_entrar_rate_limit(client: TestClient):
    part = db.criar_participante("RateUser", status="liberado", celular="11999223344")
    db.definir_credenciais(part["id"], "rate.user", "senha1234")

    for _ in range(8):
        r = client.post(
            "/entrar",
            data={"usuario": "rate.user", "senha": "errada"},
            follow_redirects=False,
        )
        assert r.status_code == 303

    blocked = client.post(
        "/entrar",
        data={"usuario": "rate.user", "senha": "senha1234"},
        follow_redirects=False,
    )
    assert blocked.status_code == 303
    assert "Muitas tentativas" in unquote(blocked.headers["location"])


def test_home_cta_aponta_para_entrar(client: TestClient):
    r = client.get("/")
    assert r.status_code == 200
    assert 'href="/entrar"' in r.text
    assert "Já fiz a inscrição" not in r.text or 'href="/entrar">Entrar' in r.text


def test_alterar_senha_na_conta(client: TestClient):
    part = db.criar_participante("TrocaSenha", status="liberado", celular="11999334455")
    db.definir_credenciais(part["id"], "troca.senha", "antiga123")
    client.get(f"/p/{part['token']}")

    r = client.post(
        f"/p/{part['token']}/conta/senha",
        data={
            "senha_atual": "antiga123",
            "senha_nova": "nova45678",
            "senha_nova2": "nova45678",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "msg=" in r.headers["location"]

    assert db.autenticar_por_username("troca.senha", "nova45678")
    assert db.autenticar_por_username("troca.senha", "antiga123") is None
