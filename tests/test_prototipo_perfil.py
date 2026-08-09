"""Perfil: disponível para participantes liberados; Benevides só Dono."""

from __future__ import annotations

from fastapi.testclient import TestClient

from src.config import ROOT_DIR
from tests.conftest import login_admin


def test_prototipo_perfil_exige_login(client: TestClient):
    r = client.get("/prototipo/perfil", follow_redirects=False)
    assert r.status_code in (303, 302)
    assert "/prototipo/perfil" not in (r.headers.get("location") or "")


def test_prototipo_perfil_liberado_acessa(client: TestClient):
    from src import db as dbmod

    part = dbmod.criar_participante("Perfil User", status="liberado", celular="11990009901")
    dbmod.definir_credenciais(part["id"], "perfil.user", "senha12345")
    client.get(f"/p/{part['token']}")

    r = client.get("/prototipo/perfil")
    assert r.status_code == 200
    assert "Editar perfil" in r.text
    assert "Perfil do Benevides" not in r.text

    r = client.get("/prototipo/perfil/publico")
    assert r.status_code == 200
    assert 'data-own="1"' in r.text
    assert "Perfil do Benevides" not in r.text


def test_prototipo_perfil_pagina(client: TestClient):
    login_admin(client)
    from src import db as dbmod

    # Garante senha do bolão para exibir o formulário de alteração
    part = dbmod.get_participante_por_admin_login("mazeta")
    assert part
    if not part.get("password_hash"):
        dbmod.definir_credenciais(part["id"], "mazeta", "senha-bolao1")

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
    assert 'href="/prototipo/perfil/benevides"' not in r.text
    assert "Ver meu perfil" in r.text
    assert "Ver como visitante" in r.text
    assert "Perfil do Benevides" not in r.text
    assert 'id="proto-avatar-edit"' in r.text
    assert 'id="proto-avatar-form"' in r.text
    assert 'name="next"' in r.text
    assert "Tema do banner" in r.text
    assert "avatar-edit-camera" in r.text
    assert 'id="proto-banner-edit"' in r.text
    assert "proto-edit-banner-camera" in r.text
    assert "proto-edit-cover-actions" not in r.text
    assert "Salvar alterações" in r.text
    assert 'id="proto-edit-save"' in r.text
    assert 'id="proto-aniv"' in r.text
    assert 'type="date"' in r.text
    assert 'data-proto-aniversario' in r.text
    assert 'id="senha"' in r.text
    assert "Alterar senha" in r.text
    assert 'id="proto-senha-atual"' in r.text
    assert 'name="senha_nova"' in r.text
    assert 'action="/p/' in r.text and "/conta/senha" in r.text
    assert "/prototipo/perfil/publico" in r.text
    assert "/static/prototipo-perfil.js?v=21" in r.text
    assert "/static/prototipo-times.js?v=13" in r.text
    assert "/static/style.css?v=279" in r.text
    assert 'id="proto-dindao"' in r.text
    assert "Dindão" in r.text
    assert "selected.length < 4" in (ROOT_DIR / "static" / "prototipo-times.js").read_text(
        encoding="utf-8"
    )


def test_prototipo_perfil_alterar_senha_volta_ao_editar(client: TestClient):
    login_admin(client)
    from src import db as dbmod

    part = dbmod.get_participante_por_admin_login("mazeta")
    assert part
    if not part.get("password_hash"):
        dbmod.definir_credenciais(part["id"], "mazeta", "senha-bolao1")
    else:
        dbmod.admin_redefinir_credenciais(part["id"], senha_nova="senha-bolao1")

    r = client.post(
        f"/p/{part['token']}/conta/senha",
        data={
            "senha_atual": "senha-bolao1",
            "senha_nova": "senha-nova99",
            "senha_nova2": "senha-nova99",
            "next": "/prototipo/perfil",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    loc = r.headers.get("location") or ""
    assert loc.startswith("/prototipo/perfil")
    assert "msg=" in loc
    assert dbmod.autenticar_por_username("mazeta", "senha-nova99")


def test_prototipo_perfil_publico_dono(client: TestClient):
    login_admin(client)
    r = client.get("/prototipo/perfil/publico")
    assert r.status_code == 200
    assert "meu perfil" in r.text.lower()
    assert 'data-own="1"' in r.text
    assert 'id="public-feed-form"' not in r.text
    assert 'id="feed"' not in r.text
    assert 'id="pedidos"' not in r.text
    assert 'id="public-amigo-pedir"' not in r.text
    assert "esquema de amizade" not in r.text.lower()
    assert "depoimentos" not in r.text.lower()
    assert 'id="bolao"' in r.text
    assert 'id="recados"' in r.text
    assert 'class="proto-steam-panel"' in r.text
    assert "No bolão" in r.text
    assert 'href="/classificacao"' in r.text
    assert "assinatura {" not in r.text
    assert "{'placar':" not in r.text
    assert 'id="public-dindao"' in r.text
    assert "Dindão" in r.text
    assert "Perfil do Benevides" not in r.text
    assert 'aria-label="Editar perfil"' in r.text
    assert "proto-text-btn--icon" in r.text
    assert 'href="/prototipo/perfil"' in r.text
    # Bolão em card próprio abaixo do hero, antes dos recados
    assert 'proto-steam-hero-bolao' not in r.text
    assert r.text.index('class="proto-steam-card"') < r.text.index('id="bolao"')
    assert r.text.index('id="bolao"') < r.text.index('id="recados"')


def test_sidebar_logado_brand_leva_ao_perfil(client: TestClient):
    """Nome/avatar no topo da sidebar abre o perfil (Meu perfil), não Minha conta."""
    from src import db as dbmod

    part = dbmod.criar_participante("Brand User", status="liberado", celular="11990009902")
    dbmod.definir_credenciais(part["id"], "brand.user", "senha12345")
    client.get(f"/p/{part['token']}")
    r = client.get("/")
    assert r.status_code == 200
    assert "site-shell" in r.text
    assert "Protótipo: perfil" not in r.text
    assert "Perfil: Benevides" not in r.text
    assert 'href="/prototipo/perfil"' not in r.text
    assert 'href="/prototipo/perfil/benevides"' not in r.text
    assert 'href="/prototipo/perfil/publico"' in r.text
    assert 'class="site-brand-hint">Meu perfil</span>' in r.text
    brand = r.text.split('class="site-brand-user', 1)[1].split("</a>", 1)[0]
    assert "data-conta-open" not in brand
    assert "Meu perfil" in brand
    assert "Minha conta" not in brand


def test_prototipo_perfil_publico_visitante(client: TestClient):
    login_admin(client)
    r = client.get("/prototipo/perfil/publico?como=visitante")
    assert r.status_code == 200
    assert "visão de visitante" in r.text.lower()
    assert 'data-own="0"' in r.text
    assert 'id="public-amigo-pedir"' not in r.text
    assert 'id="public-recado-form"' in r.text
    assert 'id="public-feed-form"' not in r.text
    assert 'id="pedidos"' not in r.text
    assert "esquema de amizade" not in r.text.lower()
    assert "data-karma-cycle" in r.text
    assert "proto-steam-karma--votavel" in r.text
    assert "proto-steam-karma--line" in r.text


def test_prototipo_perfil_publico_dono_nao_vota_karma(client: TestClient):
    login_admin(client)
    r = client.get("/prototipo/perfil/publico")
    assert r.status_code == 200
    assert 'data-own="1"' in r.text
    assert "data-karma-cycle" not in r.text
    assert "proto-steam-karma--votavel" not in r.text
    assert "proto-steam-karma--line" in r.text


def test_prototipo_perfil_benevides_liberado(client: TestClient):
    r = client.get("/prototipo/perfil/benevides", follow_redirects=False)
    assert r.status_code in (303, 302)

    from src import db as dbmod

    part = dbmod.criar_participante("Comum Bene", status="liberado", celular="11990009903")
    dbmod.definir_credenciais(part["id"], "comum.bene", "senha12345")
    client.get(f"/p/{part['token']}")
    part_b = dbmod.criar_participante("Benevides", status="liberado", celular="11990001122")
    dbmod.salvar_avatar(part_b["id"], "benevides-teste.jpg")

    r = client.get("/prototipo/perfil/benevides")
    assert r.status_code == 200
    assert "Benevides" in r.text
    assert 'data-fixado="1"' in r.text
    assert 'data-own="0"' in r.text
    assert "Palmeiras" in r.text
    assert 'id="proto-perfil-fixado"' in r.text
    assert 'id="public-amigo-pedir"' not in r.text
    assert 'id="recados"' in r.text
    assert 'id="public-recado-form"' in r.text
    assert "/avatars/benevides-teste.jpg" in r.text
    assert "data-public-avatar" in r.text


def test_menu_perfil_fora_do_portal(client: TestClient):
    """Portal não lista atalhos de perfil; acesso só pelo brand Meu perfil."""
    r = client.get("/")
    assert r.status_code == 200
    assert 'href="/prototipo/perfil"' not in r.text
    assert 'href="/prototipo/perfil/benevides"' not in r.text
    assert "Protótipo: perfil" not in r.text
    assert "Perfil: Benevides" not in r.text

    login_admin(client)
    client.cookies.set("thdfm_ui_mode", "user", domain="testserver.local")
    r = client.get("/")
    assert r.status_code == 200
    assert "Protótipo: perfil" not in r.text
    assert "Perfil: Benevides" not in r.text
    assert 'href="/prototipo/perfil/benevides"' not in r.text
    # Brand continua apontando ao perfil público
    assert 'href="/prototipo/perfil/publico"' in r.text
    assert 'class="site-brand-hint">Meu perfil</span>' in r.text

    r = client.get("/admin")
    assert r.status_code == 200
    assert "Protótipo perfil" not in r.text
    assert 'href="/prototipo/perfil/benevides"' not in r.text
