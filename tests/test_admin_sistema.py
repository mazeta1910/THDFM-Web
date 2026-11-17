"""Painel Sistema: guards, visão geral e catálogo de rotas (Fase 0 + A)."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from src import admin_sistema as sis
from src import db
from tests.conftest import login_admin


@pytest.fixture()
def admin_users():
    return "mazeta=senha-dono=Mazeta:dono|ramos=senha-mod=Ramos:moderador"


def test_moderador_recebe_403_em_sistema(client: TestClient):
    login_admin(client, "ramos", "senha-mod")
    r = client.get("/admin/sistema/rotas", follow_redirects=False)
    assert r.status_code == 403
    assert "Só o Dono" in r.text
    assert 'href="/admin/visao"' in r.text
    assert "Sem permissão" in r.text


def test_moderador_nao_ve_menu_sistema(client: TestClient):
    login_admin(client, "ramos", "senha-mod")
    r = client.get("/admin")
    assert r.status_code == 200
    assert "Comunidade" in r.text
    assert 'href="/admin/sistema/rotas"' not in r.text
    assert "Visão geral" in r.text


def test_dono_ve_rotas_e_filtro_sem_auth(client: TestClient):
    login_admin(client, "mazeta", "senha-dono")
    r = client.get("/admin/sistema/rotas")
    assert r.status_code == 200
    assert "admin-data-table" in r.text
    assert "Auth" in r.text
    assert "Papel" in r.text
    assert "/admin/sistema/rotas" in r.text

    r2 = client.get("/admin/sistema/rotas?sem_auth=1")
    assert r2.status_code == 200
    assert "publico" in r2.text
    assert "Limpar" in r2.text or "admin-data-table" in r2.text


def test_introspeccao_deriva_metodos_reais():
    from src.app import app

    rows = sis.introspect_routes(app)
    assert rows
    methods = {r["method"] for r in rows}
    assert "GET" in methods
    assert "POST" in methods
    assert any(r["path"] == "/health" and r["method"] == "GET" for r in rows)
    assert any(r["auth"] == "publico" and r["path"] == "/health" for r in rows)
    assert any(
        r["path"].startswith("/admin/sistema") and r["papel"] == "dono" for r in rows
    )


def test_snapshot_diff_e_export(client: TestClient):
    login_admin(client, "mazeta", "senha-dono")
    r = client.post("/admin/sistema/rotas/snapshot", follow_redirects=False)
    assert r.status_code == 303
    assert "Snapshot" in (r.headers.get("location") or "")

    snap = sis.load_snapshot()
    assert snap and snap.get("sigs")

    csv_r = client.get("/admin/sistema/rotas.csv?sem_auth=1")
    assert csv_r.status_code == 200
    assert "text/csv" in csv_r.headers.get("content-type", "")
    assert "method,path,auth" in csv_r.text

    js = client.get("/admin/sistema/rotas.json?sem_auth=1")
    assert js.status_code == 200
    data = json.loads(js.text)
    assert isinstance(data, list)
    assert all(row.get("auth") == "publico" for row in data)


def test_visao_geral(client: TestClient):
    login_admin(client, "mazeta", "senha-dono")
    r = client.get("/admin/visao")
    assert r.status_code == 200
    assert "Visão geral" in r.text
    assert "admin-breadcrumb" in r.text
    assert "Precisa de mim agora" in r.text


def test_sistema_cap_nao_grava_em_moderador():
    with pytest.raises(ValueError, match="sistema"):
        db.set_admin_capability("ramos", "sistema.ver", True)
