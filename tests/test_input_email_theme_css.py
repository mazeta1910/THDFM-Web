"""Contrato CSS: input[type=email|url] entram no estilo global de formulário."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "static" / "style.css").read_text(encoding="utf-8")


def test_input_email_e_url_no_seletor_global():
    # Evita gate/esqueci/conta com input nativo claro no tema escuro.
    idx = CSS.find('input[type="email"]')
    assert idx != -1
    bloco = CSS[max(0, idx - 220) : idx + 280]
    assert 'input[type="text"]' in bloco
    assert 'input[type="url"]' in bloco
    assert "background: var(--bg)" in bloco
    assert "border: 1px solid var(--border)" in bloco
    assert "color: var(--text)" in bloco
