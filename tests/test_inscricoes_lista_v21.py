"""Inscrições v2.1 — lista densa + filtro data_curta."""

from __future__ import annotations

from fastapi.testclient import TestClient

import src.db as db
from src.app import TEMPLATES, _participantes_admin_ctx, data_curta
from src.config import ROOT_DIR
from tests.conftest import login_admin


def test_data_curta_filtro():
    assert data_curta("2026-07-30 14:11:37") == "30/07/26"
    assert data_curta("2026-07-30") == "30/07/26"
    assert data_curta("") == ""
    assert data_curta(None) == ""
    assert data_curta("invalido") == "invalido"


def test_participantes_admin_ctx_desde_curta():
    rows = _participantes_admin_ctx(
        [
            {
                "id": 1,
                "nome": "A",
                "criado_em": "2026-07-30 14:11:37",
                "inativo_em": None,
            },
            {
                "id": 2,
                "nome": "B",
                "criado_em": "2026-01-01 00:00:00",
                "inativo_em": "2026-08-15 12:00:00",
            },
        ]
    )
    assert rows[0]["desde_curta"] == "30/07/26"
    assert rows[1]["desde_curta"] == "15/08/26"


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
    # data curta vem do ctx Python (não só do filtro Jinja)
    assert "participante-col-desde" in r.text

    assert 'data-page-size="10"' in r.text
    assert "data-participantes-pager" in r.text
    assert "data-page-prev" in r.text
    assert "data-page-next" in r.text
    assert "Remover foto deste participante?" in r.text

    css = (ROOT_DIR / "static" / "style.css").read_text(encoding="utf-8")
    assert ".participantes-lista {" in css
    assert "min-height: 42px" in css
    assert ".participante-edit-avatar {\n  position: relative;\n  width: 36px;" in css or "width: 36px;\n  height: 36px;" in css
    assert ".participantes-pager {" in css
    assert "@media (max-width: 860px)" in css
    assert "@media (hover: none)" in css


def test_admin_html_nao_depende_do_filtro_data_curta():
    html = (ROOT_DIR / "templates" / "admin.html").read_text(encoding="utf-8")
    assert "|data_curta" not in html
    assert "desde_curta" in html
    assert "(p.nome or '?')[:2]" in html


def test_admin_shell_sobrevive_sem_filtro_data_curta(client: TestClient):
    """Regressão do 500: inscricoes+resultados usam o mesmo admin.html."""
    db.criar_participante("Shell Ok", status="liberado", celular="11990005555")
    login_admin(client)

    removed = TEMPLATES.env.filters.pop("data_curta", None)
    TEMPLATES.env.globals.pop("data_curta", None)
    try:
        for path in ("/admin?sec=inscricoes", "/admin?sec=resultados", "/admin"):
            r = client.get(path)
            assert r.status_code == 200, path
            assert "Internal Server Error" not in r.text
            assert "participantes-lista" in r.text
            assert "Painel de Admin" in r.text or "Inscrições" in r.text or "Resultados" in r.text
    finally:
        TEMPLATES.env.filters["data_curta"] = removed or data_curta
        TEMPLATES.env.globals["data_curta"] = removed or data_curta
