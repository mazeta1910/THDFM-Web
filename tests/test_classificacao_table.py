"""Classificação: colocação, nomes e ordenação."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import src.db as db
from src.config import ROOT_DIR


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(ROOT_DIR)
    monkeypatch.setenv(
        "ADMIN_USERS",
        "mazeta=senha-dono=Mazeta:dono",
    )
    db.DB_PATH = tmp_path / "test.db"
    (tmp_path / "avatars").mkdir(exist_ok=True)
    (tmp_path / "comprovantes").mkdir(exist_ok=True)
    db.init_db()

    from src.app import app

    with TestClient(app) as c:
        yield c


def _login_admin(client: TestClient):
    r = client.post(
        "/admin/login",
        data={"login": "mazeta", "password": "senha-dono"},
        follow_redirects=False,
    )
    assert r.status_code == 303


def test_classificacao_tem_coluna_pos_e_ordenacao(client: TestClient):
    db.criar_participante("Alesson Evangelista Longo", status="liberado", celular="11990000101")
    db.criar_participante("Beta Curto", status="liberado", celular="11990000102")
    _login_admin(client)

    r = client.get("/classificacao")
    assert r.status_code == 200
    assert "col-pos" in r.text
    assert "1º" in r.text
    assert "2º" in r.text
    assert "data-classificacao-sort" in r.text
    assert 'data-sort-key="pos"' in r.text
    assert 'data-sort-key="nome"' in r.text
    assert 'data-sort-key="soma"' in r.text
    assert "Alesson Evangelista Longo" in r.text
    assert "th-sort" in r.text
    assert "is-sortable" in r.text
    assert "/static/style.css?v=202" in r.text
    assert "th-sort-up" in r.text
    assert "th-sort-down" in r.text
    assert 'viewBox="0 0 12 16"' in r.text
    assert "zona-meio" in r.text or "zona-" in r.text
