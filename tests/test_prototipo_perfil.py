"""Protótipo de perfil (edição + visão pública) com times e karma."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_prototipo_perfil_pagina(client: TestClient):
    r = client.get("/prototipo/perfil")
    assert r.status_code == 200
    assert "Meu perfil" in r.text
    assert 'id="proto-times"' in r.text
    assert 'id="karma"' in r.text
    assert "Confiável" in r.text
    assert "Torcedor Misto" in r.text
    assert "/static/prototipo-perfil.js" in r.text
    assert "/static/prototipo-times.js" in r.text


def test_prototipo_perfil_publico(client: TestClient):
    r = client.get("/prototipo/perfil/publico")
    assert r.status_code == 200
    assert "visão pública" in r.text.lower() or "Perfil na THDFM" in r.text
    assert 'id="public-times"' in r.text
    assert "Burro" in r.text


def test_menu_aponta_para_perfil(client: TestClient):
    r = client.get("/")
    assert r.status_code == 200
    assert 'href="/prototipo/perfil"' in r.text
