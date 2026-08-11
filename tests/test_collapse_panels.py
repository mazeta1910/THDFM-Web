"""Collapse custom: módulo compartilhado em static/collapse-panels.js."""
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from tests.conftest import login_admin

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / "static" / "collapse-panels.js").read_text(encoding="utf-8")
BASE = (ROOT / "templates" / "base.html").read_text(encoding="utf-8")
ADMIN = (ROOT / "templates" / "admin.html").read_text(encoding="utf-8")


def test_collapse_panels_js_expoe_api():
    assert "ThdfmCollapse" in JS
    assert "bindPanel" in JS
    assert "initFases" in JS
    assert "initPlanilha" in JS
    assert "initSimple" in JS
    assert "initAll" in JS
    assert "data-fases-collapse" in JS
    assert "data-planilha-collapse" in JS
    assert "data-planilha-grupo-toggle" in JS
    assert "data-collapse" in JS


def test_base_carrega_collapse_panels_js():
    assert "/static/collapse-panels.js" in BASE
    assert "data-planilha-grupo-toggle" not in BASE
    assert "btn-toggle-fases-label" not in BASE
    assert 'DEFAULT_KEY = "thdfm-fases-collapsed"' not in BASE


def test_admin_template_liberados_usa_data_collapse():
    assert 'id="liberados-col"' in ADMIN
    assert "data-collapse" in ADMIN
    assert 'data-collapse-toggle="#btn-toggle-liberados"' in ADMIN
    assert 'data-collapse-storage="admin-liberados-collapsed"' in ADMIN
    assert "setLiberadosCollapsed" not in ADMIN


def test_transparencia_carrega_collapse_js(client: TestClient):
    login_admin(client)
    r = client.get("/transparencia")
    assert r.status_code == 200
    assert "/static/collapse-panels.js" in r.text
    assert "data-fases-collapse" in r.text


def test_admin_liberados_renderiza_data_collapse(client: TestClient):
    login_admin(client)
    admin = client.get("/admin")
    assert admin.status_code == 200
    assert 'id="liberados-col"' in admin.text
    assert 'data-collapse-toggle="#btn-toggle-liberados"' in admin.text
    assert 'data-collapse-storage="admin-liberados-collapsed"' in admin.text
