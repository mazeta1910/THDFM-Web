#!/usr/bin/env python3
"""Concatena os partials de CSS em static/css/ para gerar static/style.css.

O `style.css` continua sendo o arquivo servido (nada muda no runtime): ele é
apenas o *bundle* gerado a partir dos módulos em `static/css/`. Edite os
partials e rode este script para regenerar o bundle.

Uso:
  python scripts/build_css.py           # regenera static/style.css
  python scripts/build_css.py --check   # falha (exit 1) se o bundle estiver
                                         # dessincronizado dos partials (CI)
"""

from __future__ import annotations

import argparse
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
CSS_DIR = ROOT / "static" / "css"
BUNDLE = ROOT / "static" / "style.css"


def montar() -> str:
    partials = sorted(CSS_DIR.glob("*.css"))
    if not partials:
        raise SystemExit(f"Nenhum partial encontrado em {CSS_DIR}")
    partes: list[str] = []
    for p in partials:
        with open(p, encoding="utf-8", newline="") as fh:
            partes.append(fh.read())
    return "".join(partes)


def main() -> int:
    ap = argparse.ArgumentParser(description="Build do CSS a partir de static/css/*.css")
    ap.add_argument(
        "--check",
        action="store_true",
        help="Não escreve; verifica se o bundle bate com os partials.",
    )
    args = ap.parse_args()

    novo = montar()
    if BUNDLE.exists():
        with open(BUNDLE, encoding="utf-8", newline="") as fh:
            atual = fh.read()
    else:
        atual = None

    if args.check:
        if novo != atual:
            print(
                "style.css está dessincronizado dos partials. "
                "Rode: python scripts/build_css.py",
                file=sys.stderr,
            )
            return 1
        print("style.css sincronizado com os partials.")
        return 0

    if novo == atual:
        print("style.css já está atualizado (sem mudanças).")
        return 0

    with open(BUNDLE, "w", encoding="utf-8", newline="") as fh:
        fh.write(novo)
    print(f"style.css regenerado a partir de {len(list(CSS_DIR.glob('*.css')))} partials.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
