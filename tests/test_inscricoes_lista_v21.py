"""Inscrições v2.1 — lista densa + filtro data_curta."""

from __future__ import annotations

from fastapi.testclient import TestClient

import src.db as db
from src.app import data_curta
from src.config import ROOT_DIR
from tests.conftest import login_admin


def test_data_curta_filtro():
    assert data_curta("2026-07-30 14:11:37") == "30/07/26"
    assert data_curta("2026-07-30") == "30/07/26"
    assert data_curta("") == ""
    assert data_curta(None) == ""
    assert data_curta("invalido") == "invalido"


def test_inscricoes_lista_densa_dono(client: TestClient):
    part = db.criar_participante("Lista Dense", status="liberado", celular="11990004444")
    db.definir_credenciais(part["id"], "lista.dense", "senha1234")

    login_admin(client)
    r = client.get("/admin?sec=inscricoes")
    assert r.status_code == 200
    assert "participantes-lista" in r.text
    assert "is-dono-lista" in r.text
    assert "participante-row" in r.text
    assert "participante-col-nome" in r.text
    assert "participante-col-user" in r.text
    assert "participante-col-senha" in r.text
    assert "participante-email-line" in r.text or "Manual · foto padrão" in r.text
    assert 'data-row-panel-toggle="edit"' in r.text
    assert 'data-row-panel-toggle="acesso"' in r.text
    assert "Remover foto deste participante?" in r.text
    assert "lista densa" in (ROOT_DIR / ".cursorrules").read_text(encoding="utf-8")

    css = (ROOT_DIR / "static" / "style.css").read_text(encoding="utf-8")
    assert ".participantes-lista {" in css
    assert "min-height: 36px" in css
    assert "@media (max-width: 860px)" in css
