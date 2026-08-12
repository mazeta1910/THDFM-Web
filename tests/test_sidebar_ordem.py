"""Menu lateral: Hall das Lendas, Portal fixo e ordem arrastável persistida."""

from __future__ import annotations

import json
import re

from fastapi.testclient import TestClient

from src import db as dbmod
from src.config import ROOT_DIR
from tests.conftest import login_admin


def _chrome_js() -> str:
    return (ROOT_DIR / "static" / "site-chrome.js").read_text(encoding="utf-8")


def test_site_sidebar_hall_lendas_e_portal_fixos(client: TestClient):
    r = client.get("/")
    assert r.status_code == 200
    html = r.text
    assert "site-hall-lendas" in html
    assert "Hall das Lendas" in html
    # Público: link ativo para todos
    chunk = html.split("site-hall-lendas", 1)[1].split(">", 1)[0]
    assert "disabled" not in chunk
    assert 'href="/hall-lendas"' in html
    assert "site-hall-star" in html
    assert 'data-menu-pinned' in html
    assert 'data-group="portal"' in html
    assert "data-menu-sortable" in html
    assert "site-menu-drag" in html
    # Hall aparece antes do Portal no markup
    assert html.index("site-hall-lendas") < html.index('data-group="portal"')
    assert html.index('data-group="portal"') < html.index("data-menu-sortable")
    js = _chrome_js()
    assert "initSidebarSortable" in js
    assert "thdfm-sidebar-ordem-v1" in js
    css = (ROOT_DIR / "static" / "style.css").read_text(encoding="utf-8")
    assert ".site-hall-lendas" in css
    assert ".site-menu-drag" in css
    assert "touch-action: none" in css
    assert ".hall-lendas-page" in css
    side = (ROOT_DIR / "templates" / "partials" / "site_sidebar.html").read_text(
        encoding="utf-8"
    )
    assert 'href="/hall-lendas"' in side
    assert "Em breve" not in side


def test_sidebar_sortable_usa_pointer_events_para_mobile():
    """HTML5 DnD falha no toque; o menu precisa de Pointer Events + captura."""
    js = _chrome_js()
    assert "addEventListener(\"pointerdown\"" in js or "addEventListener('pointerdown'" in js
    assert "pointermove" in js
    assert "pointerup" in js
    assert "pointercancel" in js
    assert "setPointerCapture" in js
    assert "touch-action" not in js  # fica no CSS do handle
    # Não depende do drag nativo no mobile
    assert 'setAttribute("draggable", "false")' in js or "draggable\", \"false\"" in js
    assert "reorderAt" in js or "insertBefore(dragging" in js

    css = (ROOT_DIR / "static" / "style.css").read_text(encoding="utf-8")
    drag_block = css.split(".site-menu-drag {", 1)[1].split("}", 1)[0]
    assert "touch-action: none" in drag_block
    assert "-webkit-user-drag: none" in drag_block

    for name in ("site_sidebar.html", "admin_sidebar.html"):
        html = (ROOT_DIR / "templates" / "partials" / name).read_text(encoding="utf-8")
        assert 'class="site-menu-drag"' in html
        assert 'draggable="false"' in html
        assert not re.search(
            r'class="site-menu-drag"[^>]*draggable="true"', html
        )


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
    assert 'draggable="false"' in html
