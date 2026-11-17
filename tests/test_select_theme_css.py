"""Contrato CSS: <select> segue o tema (evita lista nativa ilegível)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "static" / "style.css").read_text(encoding="utf-8")


def test_select_tem_color_scheme_dark_e_option_tema():
    assert "color-scheme: dark" in CSS
    assert "select option" in CSS
    assert "background-color: var(--card)" in CSS
    # Filtros do Sistema não podem forçar fundo transparente no select.
    idx = CSS.find(".admin-filter-field input")
    assert idx != -1
    bloco = CSS[idx : idx + 900]
    assert "background: transparent" not in bloco
    assert "background: var(--card)" in bloco
    assert "color-scheme: dark" in bloco
