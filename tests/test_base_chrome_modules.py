"""Scripts de chrome extraídos do base.html."""
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from tests.conftest import login_admin

ROOT = Path(__file__).resolve().parents[1]
BASE = (ROOT / "templates" / "base.html").read_text(encoding="utf-8")


def test_base_carrega_modulos_chrome():
    for src in (
        "/static/theme-boot.js",
        "/static/theme.js",
        "/static/collapse-panels.js",
        "/static/site-chrome.js",
        "/static/avatar-crop.js",
        "/static/drawers.js",
    ):
        assert src in BASE


def test_base_nao_mantem_logica_inline_pesada():
    assert 'getElementById("avatar-crop-modal")' not in BASE
    assert 'getElementById("acesso-drawer-root")' not in BASE
    assert 'const KEY = "thdfm-theme"' not in BASE
    assert "thdfmBindAvatarCrop" not in BASE
    assert "maxAge = 60 * 60 * 24 * 180" not in BASE
    # easter egg Marlon pode permanecer inline
    assert "data-marlon-sobrenome" in BASE


def test_modulos_existem_e_expoem_apis():
    crop = (ROOT / "static" / "avatar-crop.js").read_text(encoding="utf-8")
    assert "thdfmBindAvatarCrop" in crop
    assert "thdfmOpenAvatarCrop" in crop
    drawers = (ROOT / "static" / "drawers.js").read_text(encoding="utf-8")
    assert "acesso-drawer-root" in drawers
    assert "conta-drawer-root" in drawers
    assert "loguin-drawer-root" in drawers
    theme = (ROOT / "static" / "theme.js").read_text(encoding="utf-8")
    assert "thdfm-theme" in theme
    assert "theme-toggle" in theme
    chrome = (ROOT / "static" / "site-chrome.js").read_text(encoding="utf-8")
    assert "chrome-mode-toggle" in chrome
    assert "password-toggle" in chrome
    assert "initSidebarSortable" in chrome or "data-menu-sortable" in chrome


def test_static_modulos_servidos(client: TestClient):
    for path in (
        "/static/theme-boot.js",
        "/static/theme.js",
        "/static/site-chrome.js",
        "/static/avatar-crop.js",
        "/static/drawers.js",
    ):
        r = client.get(path)
        assert r.status_code == 200
        assert len(r.text) > 100


def test_home_e_admin_carregam_chrome(client: TestClient):
    home = client.get("/")
    assert home.status_code == 200
    assert "/static/theme-boot.js" in home.text
    assert "/static/drawers.js" in home.text
    assert "/static/site-chrome.js" in home.text

    login_admin(client)
    admin = client.get("/admin")
    assert admin.status_code == 200
    assert "/static/avatar-crop.js" in admin.text
    assert "/static/theme.js" in admin.text
