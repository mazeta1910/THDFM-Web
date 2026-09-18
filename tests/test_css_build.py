"""Garante que o bundle servido (static/style.css) permaneça sincronizado com
os partials modulares em static/css/.

Se alguém editar o style.css diretamente (em vez dos partials) ou esquecer de
rodar `python scripts/build_css.py`, este teste falha e aponta o conserto.
"""

from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
CSS_DIR = ROOT / "static" / "css"
BUNDLE = ROOT / "static" / "style.css"


def _ler(p: pathlib.Path) -> str:
    with open(p, encoding="utf-8", newline="") as fh:
        return fh.read()


def test_partials_existem():
    partials = sorted(CSS_DIR.glob("*.css"))
    assert partials, "Nenhum partial em static/css/ — rode o split/modularização."


def test_style_css_sincronizado_com_partials():
    partials = sorted(CSS_DIR.glob("*.css"))
    bundle = "".join(_ler(p) for p in partials)
    atual = _ler(BUNDLE)
    assert bundle == atual, (
        "static/style.css está dessincronizado dos partials em static/css/. "
        "Rode: python scripts/build_css.py"
    )
