"""Contrato chrome: site_sidebar alinhado ao visual admin v2 (#409)."""

from fastapi.testclient import TestClient

from src.config import ROOT_DIR


def test_site_sidebar_v2_chrome_css_e_a11y(client: TestClient):
    r = client.get("/classificacao")
    assert r.status_code == 200
    html = r.text

    assert 'id="site-sidebar"' in html
    assert "site-side-footer" in html
    assert "site-side-sair-wrap" not in html or "site-side-footer" in html
    assert "Cobranças" not in html.split('id="site-sidebar"', 1)[1].split("</aside>", 1)[0]
    assert 'data-group="operacao"' not in html
    assert 'data-group="sistema"' not in html

    # Classificação ativa com aria-current (classe active fica antes do href)
    assert 'href="/classificacao"' in html
    marker = 'class="site-side-link active"'
    assert marker in html
    idx = html.index(marker)
    window = html[idx : idx + 280]
    assert 'href="/classificacao"' in window
    assert "aria-current" in window

    # Bolão abre no contexto; ícones semânticos no template
    side = (ROOT_DIR / "templates/partials/site_sidebar.html").read_text(encoding="utf-8")
    assert "ico('chart')" in side
    assert "ico('eye')" in side
    assert "ico('book')" in side
    assert "ico('grid')" in side
    assert "ico('home')" in side
    assert "ico('ban')" in side
    assert "site-side-footer" in side

    css = (ROOT_DIR / "static/style.css").read_text(encoding="utf-8")
    assert ".site-side-link.active::before" in css
    assert "rgba(232, 93, 4, 0.10)" in css
    # Sair neutro (não accent2 forçado) — regra própria, não a do form
    assert ".site-side-sair {\n  color: var(--text) !important;" in css or (
        "color: var(--text) !important" in css.split(".site-side-sair {", 2)[-1][:80]
    )
    assert "color: var(--accent2) !important" not in css.split(".site-side-sair {", 1)[1][:200]
    assert ".site-side-footer" in css
    assert "scrollbar-color: var(--border) transparent" in css


def test_site_sidebar_v2_nao_mistura_modulos_admin(client: TestClient):
    r = client.get("/")
    assert r.status_code == 200
    side_html = r.text.split('id="site-sidebar"', 1)[1].split("</aside>", 1)[0]
    for forbidden in (
        "Visão geral",
        "Operação",
        "Credenciais",
        "Permissões",
        "Access log",
        "Site (visualização)",
    ):
        assert forbidden not in side_html
    assert "Hall das Lendas" in side_html
    assert "Bolão CdB" in side_html
    assert "Grupo do WhatsApp" in side_html
