"""Contrato chrome: menu lateral admin v2 (Harness)."""

from pathlib import Path

from fastapi.testclient import TestClient

from src.config import ROOT_DIR
from tests.conftest import login_admin


def test_admin_sidebar_v2_estrutura_e_css(client: TestClient):
    login_admin(client)
    r = client.get("/admin/visao")
    assert r.status_code == 200
    html = r.text

    assert "Cobranças" in html
    assert ">Quem palpitou<" not in html
    assert "Site (visualização)" in html
    assert 'data-group="site-visualizacao"' in html
    assert 'data-group="bolao-publico"' not in html
    assert 'data-group="comunidade"' not in html
    assert 'data-group="meu-bolao"' not in html
    assert "admin-side-tag" in html
    assert "em breve" in html.lower()
    assert "admin-side-footer-meta" not in html
    assert "/bolao/meuspalpites" not in html
    assert "admin-brand-quick" in html
    assert "Meus Palpites" in html

    sidebar = (ROOT_DIR / "templates/partials/admin_sidebar.html").read_text(encoding="utf-8")
    assert "ico('bell')" in sidebar
    assert "ico('home')" in sidebar
    assert "ico('globe'" in sidebar
    assert "ico('external'" in sidebar

    icons = (ROOT_DIR / "templates/partials/nav_icons.html").read_text(encoding="utf-8")
    assert "('inicio', 'home')" in icons
    assert "('admin', 'shield')" in icons
    for name in (
        "bell",
        "key",
        "archive",
        "list",
        "activity",
        "routes",
        "grid",
        "medal",
        "external",
        "globe",
        "health",
        "image",
    ):
        assert f"name == '{name}'" in icons

    css = (ROOT_DIR / "static/style.css").read_text(encoding="utf-8")
    assert "--count:" in css
    assert "admin-menu-group[open] > .admin-menu-summary > .admin-badge" in css
    assert ".admin-side-link.active::before" in css
    assert ".admin-side-tag" in css


def test_admin_sidebar_v2_aria_current_em_ativo(client: TestClient):
    login_admin(client)
    r = client.get("/admin/visao")
    assert r.status_code == 200
    chunk = r.text.split('href="/admin/visao"', 1)[1][:240]
    assert "aria-current" in chunk
    assert "active" in chunk
