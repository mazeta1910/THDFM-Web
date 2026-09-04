"""Gradientes de raridade por tier (%)."""

from __future__ import annotations

from pathlib import Path

from src.config import ROOT_DIR


def test_grid_raridade_tiers_css_e_js():
    css = (ROOT_DIR / "static" / "style.css").read_text(encoding="utf-8")
    js = (ROOT_DIR / "static" / "grid.js").read_text(encoding="utf-8")
    assert 'data-rarity="1"' in css
    assert "#ffd700" in css.lower() or "#FFD700" in css
    assert "#ff8c00" in css.lower() or "#FF8C00" in css
    assert "#8a2be2" in css.lower() or "#8A2BE2" in css
    assert "#ff00ff" in css.lower() or "#FF00FF" in css
    assert "#0000cd" in css.lower() or "#0000CD" in css
    assert "#00ffff" in css.lower() or "#00FFFF" in css
    assert "#228b22" in css.lower() or "#228B22" in css
    assert "#32cd32" in css.lower() or "#32CD32" in css
    assert "#708090" in css
    assert "#d3d3d3" in css.lower() or "#D3D3D3" in css
    assert 'rotulo = "Lendário"' in js
    assert 'rotulo = "Épico"' in js
    assert 'rotulo = "Raro"' in js
    assert 'rotulo = "Incomum"' in js
    assert 'rotulo = "Comum"' in js
    assert "pctNum >= 95" in js
    assert "pctNum >= 75" in js
    assert "pctNum >= 50" in js
    assert "pctNum >= 20" in js


def test_grid_assets_bump_raridade(client):
    from tests.conftest import login_admin

    login_admin(client)
    r = client.get("/grid")
    assert r.status_code == 200
    assert "/static/grid.js?v=41" in r.text
    assert "/static/style.css?v=334" in r.text
