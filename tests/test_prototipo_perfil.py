"""Protótipo de perfil: privado do Dono + rota Benevides."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import login_admin


def test_prototipo_perfil_exige_dono(client: TestClient):
    r = client.get("/prototipo/perfil", follow_redirects=False)
    assert r.status_code in (303, 302)
    assert "/prototipo/perfil" not in (r.headers.get("location") or "")


def test_prototipo_perfil_pagina(client: TestClient):
    login_admin(client)
    r = client.get("/prototipo/perfil")
    assert r.status_code == 200
    assert "Editar perfil" in r.text
    assert 'class="proto-edit"' in r.text
    assert 'id="proto-times"' in r.text
    assert 'id="times"' in r.text
    assert 'data-clubes-src="/prototipo/times/clubes.json"' in r.text
    assert 'id="proto-karma-edit"' not in r.text
    assert "data-karma-cycle" not in r.text
    assert "nutela" not in r.text.lower()
    assert 'id="banner"' in r.text
    assert "banner-crop-modal" in r.text
    assert 'id="proto-feed-form"' not in r.text
    assert "depoimentos" not in r.text.lower()
    assert 'href="/prototipo/perfil/benevides"' in r.text
    assert "Ver meu perfil" in r.text
    assert "Ver como visitante" in r.text
    assert "Perfil do Benevides" in r.text
    assert "/static/style.css?v=256" in r.text


def test_prototipo_perfil_publico_dono(client: TestClient):
    login_admin(client)
    r = client.get("/prototipo/perfil/publico")
    assert r.status_code == 200
    assert "meu perfil" in r.text.lower()
    assert 'data-own="1"' in r.text
    assert 'id="public-feed-form"' in r.text
    assert 'id="pedidos"' in r.text
    assert 'id="public-amigo-pedir"' not in r.text
    assert "depoimentos" not in r.text.lower()
    assert "mais que amigos, irmães" in r.text.lower()


def test_prototipo_perfil_publico_visitante(client: TestClient):
    login_admin(client)
    r = client.get("/prototipo/perfil/publico?como=visitante")
    assert r.status_code == 200
    assert "visão de visitante" in r.text.lower()
    assert 'data-own="0"' in r.text
    assert 'id="public-amigo-pedir"' in r.text
    assert 'id="public-recado-form"' in r.text
    assert 'id="public-feed-form"' not in r.text
    assert 'id="pedidos"' not in r.text
    assert "data-karma-cycle" in r.text
    assert "proto-steam-karma--votavel" in r.text


def test_prototipo_perfil_publico_dono_nao_vota_karma(client: TestClient):
    login_admin(client)
    r = client.get("/prototipo/perfil/publico")
    assert r.status_code == 200
    assert 'data-own="1"' in r.text
    assert "data-karma-cycle" not in r.text
    assert "proto-steam-karma--votavel" not in r.text
    assert "Karma da galera" in r.text


def test_prototipo_perfil_benevides_privado(client: TestClient):
    r = client.get("/prototipo/perfil/benevides", follow_redirects=False)
    assert r.status_code in (303, 302)

    login_admin(client)
    r = client.get("/prototipo/perfil/benevides")
    assert r.status_code == 200
    assert "Benevides" in r.text
    assert 'data-fixado="1"' in r.text
    assert 'data-own="0"' in r.text
    assert "Palmeiras" in r.text
    assert 'id="proto-perfil-fixado"' in r.text
    assert 'id="public-amigo-pedir"' in r.text


def test_menu_prototipo_so_dono(client: TestClient):
    r = client.get("/")
    assert r.status_code == 200
    assert 'href="/prototipo/perfil"' not in r.text
    assert 'href="/prototipo/perfil/benevides"' not in r.text

    login_admin(client)
    r = client.get("/")
    assert r.status_code == 200
    assert 'href="/prototipo/perfil"' in r.text
    assert 'href="/prototipo/perfil/benevides"' in r.text
