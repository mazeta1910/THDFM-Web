"""Limite de caracteres do nome exibido."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import src.db as db
from src.config import NOME_MAX_LEN, ROOT_DIR


@pytest.fixture()
def db_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(ROOT_DIR)
    db.DB_PATH = tmp_path / "test.db"
    (tmp_path / "avatars").mkdir(exist_ok=True)
    (tmp_path / "comprovantes").mkdir(exist_ok=True)
    db.init_db()
    return db


@pytest.fixture()
def client(db_tmp, monkeypatch: pytest.MonkeyPatch):
    from src.app import app

    with TestClient(app) as c:
        yield c


def test_nome_max_30_na_criacao(db_tmp):
    ok = db_tmp.criar_participante("A" * NOME_MAX_LEN, status="pendente")
    assert ok["nome"] == "A" * NOME_MAX_LEN
    with pytest.raises(ValueError, match="30"):
        db_tmp.criar_participante("A" * (NOME_MAX_LEN + 1), status="pendente")


def test_nome_max_30_ao_atualizar(db_tmp):
    part = db_tmp.criar_participante("Curto", status="liberado")
    db_tmp.atualizar_nome_participante(part["id"], "B" * NOME_MAX_LEN)
    assert db_tmp.get_participante(part["id"])["nome"] == "B" * NOME_MAX_LEN
    with pytest.raises(ValueError, match="30"):
        db_tmp.atualizar_nome_participante(part["id"], "B" * (NOME_MAX_LEN + 1))


def test_forms_tem_maxlength_30(client: TestClient):
    part = db.criar_participante("ComNome", status="liberado", celular="11990001122")
    db.definir_credenciais(part["id"], "com.nome", "senha1234")
    client.get(f"/p/{part['token']}")

    # Conta full page (?page=1) e drawer (?conta=1)
    r = client.get(f"/p/{part['token']}/conta?page=1")
    assert r.status_code == 200
    assert 'maxlength="30"' in r.text

    r_drawer = client.get(f"/p/{part['token']}?conta=1")
    assert r_drawer.status_code == 200
    assert 'id="conta-drawer-nome"' in r_drawer.text
    assert 'maxlength="30"' in r_drawer.text

    r2 = client.get("/inscricao")
    assert r2.status_code == 200
    # Inscrições encerradas após 01/08 13:30 — formulário some.
    assert "Inscrições encerradas" in r2.text
