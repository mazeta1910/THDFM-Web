"""Contrato: modais de feedback com Ok à direita e sucesso auto-fecha."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "static" / "style.css").read_text(encoding="utf-8")
CHROME = (ROOT / "static" / "site-chrome.js").read_text(encoding="utf-8")
PALPITES = (ROOT / "templates" / "palpites.html").read_text(encoding="utf-8")
BASE = (ROOT / "templates" / "base.html").read_text(encoding="utf-8")


def test_modal_ok_compacto_a_direita():
    assert ".modal-ok-row" in CSS
    assert "justify-content: flex-end" in CSS
    assert "button.modal-ok" in CSS
    bloco = CSS[CSS.find("button.modal-ok") : CSS.find("button.modal-ok") + 350]
    assert "width: auto !important" in bloco
    assert "max-width: max-content !important" in bloco


def test_site_chrome_autoclose_sucesso():
    assert "data-modal-feedback" in CHROME
    assert "sucesso-modal" in CHROME
    assert "2200" in CHROME


def test_palpites_sucesso_usa_feedback_global():
    assert 'data-modal-feedback' in PALPITES
    assert 'class="modal-ok-row"' in PALPITES
    assert "bindModal(" not in PALPITES
    assert "site-chrome.js?v=4" in BASE
