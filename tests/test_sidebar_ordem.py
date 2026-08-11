"""Menu lateral: Hall das Lendas, Portal fixo e ordem arrastável persistida."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from src import db as dbmod
from src.config import ROOT_DIR
from tests.conftest import login_admin


def test_site_sidebar_hall_lendas_e_portal_fixos(client: TestClient):
    r = client.get("/")
    assert r.status_code == 200
    html = r.text
    assert "site-hall-lendas" in html
    assert "Hall das Lendas" in html
    assert 'disabled' in html.split("site-hall-lendas", 1)[1].split(">", 1)[0]
    assert 'aria-disabled="true"' in html
    assert "site-hall-star" in html
    assert 'data-menu-pinned' in html
    assert 'data-group="portal"' in html
    assert "data-menu-sortable" in html
    assert "site-menu-drag" in html
    # Hall aparece antes do Portal no markup
    assert html.index("site-hall-lendas") < html.index('data-group="portal"')
    assert html.index('data-group="portal"') < html.index("data-menu-sortable")
    js = (ROOT_DIR / "templates" / "base.html").read_text(encoding="utf-8")
    assert "initSidebarSortable" in js
    assert "thdfm-sidebar-ordem-v1" in js
    css = (ROOT_DIR / "static" / "style.css").read_text(encoding="utf-8")
    assert ".site-hall-lendas" in css
    assert ".site-menu-drag" in css


def test_sidebar_ordem_api_e_persistencia(client: TestClient):
    part = dbmod.criar_participante("Sidebar Ordem", status="liberado", celular="11990001122")
    dbmod.definir_credenciais(part["id"], "sidebar.ordem", "senha12345")
    client.get(f"/p/{part['token']}")

    r = client.put(
        "/conta/sidebar-ordem",
        json={"scope": "site", "ordem": ["grupo-whatsapp", "bolao", "jogos-passatempos"]},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["ordem"]["site"] == ["grupo-whatsapp", "bolao", "jogos-passatempos"]

    fresh = dbmod.get_participante(part["id"])
    saved = json.loads(fresh["sidebar_ordem_json"] or "{}")
    assert saved["site"][0] == "grupo-whatsapp"

    page = client.get("/")
    assert page.status_code == 200
    assert "grupo-whatsapp" in page.text
    assert 'data-sidebar-ordem="' in page.text


def test_sidebar_ordem_exige_login(client: TestClient):
    r = client.put(
        "/conta/sidebar-ordem",
        json={"scope": "site", "ordem": ["bolao"]},
        follow_redirects=False,
    )
    assert r.status_code in (303, 401, 302)


def test_admin_sidebar_admin_fixo_e_sortable(client: TestClient):
    login_admin(client)
    r = client.get("/admin")
    assert r.status_code == 200
    html = r.text
    assert 'data-group="admin"' in html
    assert "data-menu-sortable" in html
    assert html.index('data-group="admin"') < html.index("data-menu-sortable")
    assert "site-menu-drag" in html
