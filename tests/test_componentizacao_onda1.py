"""Macros Jinja da Onda 1 e fixtures compartilhados."""

from __future__ import annotations

from pathlib import Path

from src.config import ROOT_DIR


def test_macros_onda1_existem():
    macros = ROOT_DIR / "templates" / "macros"
    for name in ("table.html", "metrica.html", "avatar.html", "emblema.html"):
        assert (macros / name).is_file()


def test_conftest_compartilhado_existe():
    assert (ROOT_DIR / "tests" / "conftest.py").is_file()


def test_classificacao_usa_macro_th_sort():
    html = (ROOT_DIR / "templates" / "classificacao.html").read_text(encoding="utf-8")
    assert 'from "macros/table.html" import th_sort' in html
    assert 'from "macros/avatar.html" import avatar' in html
    assert "th_sort(" in html


def test_planilha_usa_macros_metrica_emblema_avatar():
    admin = (ROOT_DIR / "templates" / "admin_palpites.html").read_text(encoding="utf-8")
    assert 'from "macros/metrica.html" import metrica, metricas_bloco' in admin
    assert 'from "macros/emblema.html" import emblema' in admin
    assert 'from "macros/avatar.html" import avatar' in admin
    assert "metricas_bloco(" in admin
    assert "{{ emblema(" in admin
