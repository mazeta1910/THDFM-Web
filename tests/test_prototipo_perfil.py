"""Protótipo de perfil estilo Orkut (edição + visão pública)."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_prototipo_perfil_pagina(client: TestClient):
    r = client.get("/prototipo/perfil")
    assert r.status_code == 200
    assert "Meu perfil" in r.text
    assert 'id="proto-times"' in r.text
    assert 'id="proto-karma-edit"' in r.text
    assert "confiável" in r.text.lower()
    assert "esquema de amizade" in r.text.lower()
    assert "depoimentos" in r.text.lower()
    assert "quem sou eu" in r.text.lower()
    assert 'data-proto-frase' in r.text
    # tag pode existir; não anunciar a regra no texto embutido
    assert "aparece a tag" not in r.text.lower()
    assert "com dois ou mais" not in r.text.lower()
    assert "/static/prototipo-perfil.js" in r.text
    assert "/static/prototipo-times.js" in r.text


def test_prototipo_perfil_publico(client: TestClient):
    r = client.get("/prototipo/perfil/publico")
    assert r.status_code == 200
    assert "visão pública" in r.text.lower()
    assert 'id="public-times"' in r.text
    assert 'id="public-karma"' in r.text
    assert "burro" in r.text.lower()
    assert "esquema de amizade" in r.text.lower()
    assert "depoimentos" in r.text.lower()


def test_menu_aponta_para_perfil(client: TestClient):
    r = client.get("/")
    assert r.status_code == 200
    assert 'href="/prototipo/perfil"' in r.text
