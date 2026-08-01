"""Testes da Listra THDFM."""

from __future__ import annotations

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


def test_listra_publica_com_anos(client: TestClient):
    from html import unescape

    from src.listra_seed import LISTRA_SEED_FRASES, listra_seed_por_ano

    r = client.get("/grupo/listra")
    assert r.status_code == 200
    body = unescape(r.text)
    assert "Listra" in body
    assert "listra-page" in body
    assert "listra-ano-card--atual" in body
    assert "listra-ano-toggle" in body
    assert "listra-ano-toggle-icon--fechar" in body
    assert "listra-ano-summary" in body
    assert "LISTRA THDFM 2026" in body
    assert "LISTRA THDFM 2025" in body
    assert "LISTRA THDFM 2024" in body
    assert LISTRA_SEED_FRASES[0] in body
    assert listra_seed_por_ano(2025)[0] in body
    assert listra_seed_por_ano(2024)[0] in body
    assert "Nova frase" not in body
    assert "data-listra-enviar" not in body


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


def test_admin_adiciona_no_ano_atual(client: TestClient):
    from src.listra_seed import LISTRA_ANO_ATUAL

    _login_admin(client)
    r = client.post(
        "/grupo/listra",
        data={
            "texto": "Nova pérola do teste",
            "responsavel": "Mazeta",
            "ano": str(LISTRA_ANO_ATUAL),
        },
        follow_redirects=False,
    )
    assert r.status_code == 303

    from src import db

    frase = next(
        f for f in db.list_listra_frases(LISTRA_ANO_ATUAL)
        if f["texto"] == "Nova pérola do teste"
    )
    assert frase["ano"] == LISTRA_ANO_ATUAL
    assert frase.get("criado_em")
    pub = client.get("/grupo/listra")
    assert "Nova pérola do teste" in pub.text
    assert "Mazeta" in pub.text
    assert "listra-editar-btn" in pub.text
    assert "/grupo/listra/atualizar" in pub.text


def test_admin_edita_frase(client: TestClient):
    from src.listra_seed import LISTRA_ANO_ATUAL
    from src import db

    _login_admin(client)
    criada = db.criar_listra_frase(
        "Texto original", "Fulano", ano=LISTRA_ANO_ATUAL
    )
    r = client.post(
        "/grupo/listra/atualizar",
        data={
            "frase_id": criada["id"],
            "texto": "Texto editado",
            "responsavel": "Ciclano",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "atualizada" in (r.headers.get("location") or "").lower()
    atualizada = db.get_listra_frase(criada["id"])
    assert atualizada["texto"] == "Texto editado"
    assert atualizada["responsavel"] == "Ciclano"
    pub = client.get("/grupo/listra")
    assert "Texto editado" in pub.text
    assert "Ciclano" in pub.text


def test_visitante_nao_edita(client: TestClient):
    from src.listra_seed import LISTRA_ANO_ATUAL
    from src import db
    from urllib.parse import unquote

    frase = db.list_listra_frases(LISTRA_ANO_ATUAL)[0]
    r = client.post(
        "/grupo/listra/atualizar",
        data={
            "frase_id": frase["id"],
            "texto": "Hack",
            "responsavel": "Ninguém",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    loc = unquote(r.headers.get("location") or "").lower()
    assert "administração" in loc or "editar" in loc
    assert db.get_listra_frase(frase["id"])["texto"] != "Hack"


def test_admin_permissoes_painel(client: TestClient):
    part = _criar_liberado()
    _login_admin(client)
    r = client.get("/admin/listra")
    assert r.status_code == 200
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


def test_participante_com_permissao_enviar(client: TestClient):
    part = _criar_liberado(
        nome="Envio", username="envio", senha="senha12345", celular="11999990002"
    )
    from src import db

    db.salvar_listra_permissao(part["id"], pode_adicionar=False, pode_enviar=True)
    _login_participante(client, part)
    r = client.get("/grupo/listra")
    assert "data-listra-copiar" in r.text
    assert "data-listra-abrir-grupo" in r.text or "Abrir grupo" in r.text
    assert "Copiar 2026" in r.text
    assert 'data-ano="2026"' in r.text
    assert 'data-ano="2025"' in r.text
    assert 'data-ano="2024"' in r.text


def test_export_por_ano(client: TestClient):
    _login_admin(client)
    r26 = client.get("/grupo/listra/export.txt?ano=2026")
    r25 = client.get("/grupo/listra/export.txt?ano=2025")
    r24 = client.get("/grupo/listra/export.txt?ano=2024")
    assert r26.status_code == 200
    assert r25.status_code == 200
    assert r24.status_code == 200
    assert "LISTRA THDFM 2026" in r26.text
    assert "LISTRA THDFM 2025" in r25.text
    assert "LISTRA THDFM 2024" in r24.text
    assert "📺 Progama" in r25.text or "Progama" in r25.text
    assert "Chooping" in r24.text


def test_export_exige_permissao(client: TestClient):
    r = client.get("/grupo/listra/export.txt")
    assert r.status_code == 403


def test_texto_whatsapp_formatado():
    from src import db
    from src.listra_seed import LISTRA_TITULO

    texto = db.listra_texto_whatsapp(
        [{"texto": "Uma", "ano": 2026}, {"texto": "Duas\nlinhas", "ano": 2026}],
        ano=2026,
    )
    assert texto.startswith(f"*{LISTRA_TITULO}*")
    assert "* Uma" in texto
    assert "* Duas" in texto
