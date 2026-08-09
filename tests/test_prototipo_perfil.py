"""Protótipo de perfil: card unificado, recados logados, pedidos de amizade."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_prototipo_perfil_pagina(client: TestClient):
    r = client.get("/prototipo/perfil")
    assert r.status_code == 200
    assert "Meu perfil" in r.text
    assert 'class="proto-steam-card"' in r.text
    assert 'id="proto-times"' in r.text
    assert 'id="times"' in r.text
    assert 'data-clubes-src="/prototipo/times/clubes.json"' in r.text
    assert 'id="proto-karma-edit"' in r.text
    assert "nutela" in r.text.lower()
    assert 'id="banner"' in r.text
    assert "banner-crop-modal" in r.text
    assert 'id="proto-feed-form"' not in r.text
    assert "depoimentos" not in r.text.lower()
    assert "enviar pedido de amizade" not in r.text.lower()
    assert 'id="proto-amigo-form"' not in r.text
    assert "/static/style.css?v=251" in r.text


def test_prototipo_perfil_publico_dono(client: TestClient):
    r = client.get("/prototipo/perfil/publico")
    assert r.status_code == 200
    assert "meu perfil" in r.text.lower()
    assert 'data-own="1"' in r.text
    assert 'id="public-feed-form"' in r.text
    assert 'id="pedidos"' in r.text
    assert 'id="public-amigo-pedir"' not in r.text
    assert "depoimentos" not in r.text.lower()
    assert "seu nome" not in r.text.lower()
    assert "mais que amigos, irmães" in r.text.lower()


def test_prototipo_perfil_publico_visitante(client: TestClient):
    r = client.get("/prototipo/perfil/publico?como=visitante")
    assert r.status_code == 200
    assert "visão de visitante" in r.text.lower()
    assert 'data-own="0"' in r.text
    assert 'id="public-amigo-pedir"' in r.text
    assert 'id="public-recado-form"' in r.text
    assert 'id="public-feed-form"' not in r.text
    assert 'id="pedidos"' not in r.text


def test_menu_aponta_para_perfil(client: TestClient):
    r = client.get("/")
    assert r.status_code == 200
    assert 'href="/prototipo/perfil"' in r.text
