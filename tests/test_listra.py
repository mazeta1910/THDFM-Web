"""Testes da Listra THDFM."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(ROOT_DIR)
    monkeypatch.setenv(
        "ADMIN_USERS",
        "mazeta=senha-dono=Mazeta:dono|ramos=senha-mod=Ramos:moderador",
    )
    from src import db

    db.DB_PATH = tmp_path / "test.db"
    (tmp_path / "avatars").mkdir(exist_ok=True)
    (tmp_path / "comprovantes").mkdir(exist_ok=True)
    db.init_db()
    from src.app import app

    with TestClient(app) as c:
        yield c


def _login_admin(client: TestClient, login="mazeta", senha="senha-dono"):
    r = client.post(
        "/admin/login",
        data={"login": login, "password": senha},
        follow_redirects=False,
    )
    assert r.status_code == 303


def _criar_liberado(
    nome="Fulano",
    username="fulano",
    senha="senha12345",
    celular="11999990001",
):
    from src import db

    part = db.criar_participante(nome, status="liberado", celular=celular)
    db.definir_credenciais(part["id"], username, senha)
    return db.get_participante(part["id"])


def _login_participante(client: TestClient, part: dict):
    r = client.get(f"/p/{part['token']}", follow_redirects=False)
    assert r.status_code in (200, 303, 302)


def test_listra_publica_com_seed(client: TestClient):
    from html import unescape

    from src.listra_seed import LISTRA_SEED_FRASES, LISTRA_TITULO

    r = client.get("/grupo/listra")
    assert r.status_code == 200
    body = unescape(r.text)
    assert "Listra" in body
    assert "listra-page" in body
    assert "em-breve-page" not in body
    assert str(len(LISTRA_SEED_FRASES)) in body
    assert LISTRA_SEED_FRASES[0] in body
    assert LISTRA_SEED_FRASES[-1] in body
    assert LISTRA_TITULO in body or "LISTRA THDFM" in body
    # Sem permissão: não mostra form nem botão WA
    assert "Nova frase" not in body
    assert "listra-enviar-wa" not in body


def test_visitante_nao_adiciona(client: TestClient):
    from urllib.parse import unquote

    r = client.post(
        "/grupo/listra",
        data={"texto": "pérola teste", "responsavel": "Alguém"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    loc = unquote(r.headers.get("location") or "").lower()
    assert "permiss" in loc


def test_admin_adiciona_e_apaga(client: TestClient):
    _login_admin(client)
    r = client.get("/grupo/listra")
    assert r.status_code == 200
    assert "Nova frase" in r.text
    assert "listra-enviar-wa" in r.text
    assert "Gerenciar permissões" in r.text

    r = client.post(
        "/grupo/listra",
        data={"texto": "Nova pérola do teste", "responsavel": "Mazeta"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "adicionada" in (r.headers.get("location") or "").lower()

    pub = client.get("/grupo/listra")
    assert "Nova pérola do teste" in pub.text
    assert "Mazeta" in pub.text

    from src import db

    frase = next(
        f for f in db.list_listra_frases() if f["texto"] == "Nova pérola do teste"
    )
    r = client.post(
        "/grupo/listra/apagar",
        data={"frase_id": frase["id"]},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "Nova pérola do teste" not in client.get("/grupo/listra").text


def test_admin_permissoes_painel(client: TestClient):
    part = _criar_liberado()
    _login_admin(client)
    r = client.get("/admin/listra")
    assert r.status_code == 200
    assert "permissões" in r.text.lower()
    assert part["nome"] in r.text

    r = client.post(
        "/admin/listra/permissoes",
        data={f"add_{part['id']}": "1", f"env_{part['id']}": "1"},
        follow_redirects=False,
    )
    assert r.status_code == 303

    from src import db

    perm = db.get_listra_permissao(part["id"])
    assert perm["pode_adicionar"] is True
    assert perm["pode_enviar"] is True


def test_participante_com_permissao_adiciona(client: TestClient):
    part = _criar_liberado()
    from src import db

    db.salvar_listra_permissao(part["id"], pode_adicionar=True, pode_enviar=False)
    _login_participante(client, part)

    r = client.get("/grupo/listra")
    assert "Nova frase" in r.text
    assert "listra-enviar-wa" not in r.text

    r = client.post(
        "/grupo/listra",
        data={"texto": "Frase do fulano", "responsavel": "Fulano"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "Frase do fulano" in client.get("/grupo/listra").text


def test_participante_com_permissao_enviar(client: TestClient):
    part = _criar_liberado(
        nome="Envio", username="envio", senha="senha12345", celular="11999990002"
    )
    from src import db

    db.salvar_listra_permissao(part["id"], pode_adicionar=False, pode_enviar=True)
    _login_participante(client, part)
    r = client.get("/grupo/listra")
    assert "Nova frase" not in r.text
    assert "listra-enviar-wa" in r.text
    assert "listra-wa-texto" in r.text


def test_texto_whatsapp_formatado():
    from src import db
    from src.listra_seed import LISTRA_TITULO

    texto = db.listra_texto_whatsapp(
        [{"texto": "Uma"}, {"texto": "Duas\nlinhas"}]
    )
    assert texto.startswith(f"*{LISTRA_TITULO}*")
    assert "* Uma" in texto
    assert "* Duas" in texto
