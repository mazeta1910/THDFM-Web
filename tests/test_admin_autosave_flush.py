"""Contrato: flush de autosave antes de trocar fase/perna no admin."""

from src.config import ROOT_DIR


def test_admin_js_flush_antes_de_trocar_fase():
    html = (ROOT_DIR / "templates/admin.html").read_text(encoding="utf-8")
    assert "let autosaveTimer = null" in html
    assert "clearTimeout(autosaveTimer)" in html
    assert "await salvarPlacaresAtivos()" in html
    # Flush só quando o painel de resultados está dirty.
    assert "admin-panel[data-panel='resultados'].is-dirty" in html
    assert "showFasePerna(fase, perna)" in html
    # Ordem: flush (salvar) aparece antes da chamada a showFasePerna no handler.
    click_chunk = html.split("placaresNav.querySelectorAll(\"button[data-fase]\")")[1]
    click_chunk = click_chunk.split("const initialCol")[0]
    assert click_chunk.index("await salvarPlacaresAtivos()") < click_chunk.index(
        "showFasePerna(fase, perna)"
    )
