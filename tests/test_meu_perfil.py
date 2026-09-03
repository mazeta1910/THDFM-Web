"""Perfil do usuário: /meu-perfil e /perfil/{id}."""

from __future__ import annotations

from fastapi.testclient import TestClient

from src.config import ROOT_DIR
from tests.conftest import login_admin


def test_meu_perfil_exige_login(client: TestClient):
    r = client.get("/meu-perfil", follow_redirects=False)
    assert r.status_code in (303, 302)
    assert "/meu-perfil" not in (r.headers.get("location") or "")


def test_meu_perfil_liberado_acessa(client: TestClient):
    from src import db as dbmod

    part = dbmod.criar_participante("Perfil User", status="liberado", celular="11990009901")
    dbmod.definir_credenciais(part["id"], "perfil.user", "senha12345")
    client.get(f"/p/{part['token']}")

    r = client.get("/meu-perfil/editar")
    assert r.status_code == 200
    assert "Editar perfil" in r.text

    r = client.get("/meu-perfil")
    assert r.status_code == 200
    assert 'data-own="1"' in r.text


def test_meu_perfil_editar_pagina(client: TestClient):
    login_admin(client)
    from src import db as dbmod

    part = dbmod.get_participante_por_admin_login("mazeta")
    assert part
    if not part.get("password_hash"):
        dbmod.definir_credenciais(part["id"], "mazeta", "senha-bolao1")

    r = client.get("/meu-perfil/editar")
    assert r.status_code == 200
    assert "Editar perfil" in r.text
    assert 'class="proto-edit"' in r.text
    assert 'id="proto-times"' in r.text
    assert 'id="times"' in r.text
    assert 'data-clubes-src="/meu-perfil/clubes.json"' in r.text
    assert 'id="proto-karma-edit"' not in r.text
    assert "data-karma-cycle" not in r.text
    assert "nutela" not in r.text.lower()
    assert 'id="banner"' in r.text
    assert "banner-crop-modal" in r.text
    assert 'id="proto-feed-form"' not in r.text
    assert "depoimentos" not in r.text.lower()
    assert "Perfil do Benevides" not in r.text
    assert 'href="/perfil/' not in r.text or "Ver meu perfil" in r.text
    assert "Ver meu perfil" in r.text
    assert "Ver como visitante" in r.text
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
    assert 'href="/meu-perfil"' in r.text
    assert "/static/prototipo-perfil.js?v=34" in r.text
    assert "/static/prototipo-times.js?v=19" in r.text
    assert 'id="proto-perfil-soft"' in r.text
    assert "/static/style.css?v=323" in r.text
    assert 'id="proto-ufs-toggle"' in r.text
    assert 'class="proto-times-ufs is-collapsed"' in r.text
    assert 'id="proto-uf-grid" hidden' in r.text
    assert 'id="proto-dindao"' in r.text
    assert "Dindão" in r.text
    # Sugestões ficam logo abaixo da busca; Por estado vem depois
    assert r.text.index('id="proto-list"') < r.text.index('id="proto-times-ufs"')
    times_js = (ROOT_DIR / "static" / "prototipo-times.js").read_text(encoding="utf-8")
    times_css = (ROOT_DIR / "static" / "style.css").read_text(encoding="utf-8")
    assert "selected.length < 4" in times_js
    assert "ensureClubes().then(() => renderList())" in times_js
    assert ".proto-times-ufs.is-collapsed .proto-times-uf-grid" in times_css
    assert "display: none !important" in times_css
    assert "Protótipo ·" not in r.text


def test_meu_perfil_alterar_senha_volta_ao_editar(client: TestClient):
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
            "next": "/meu-perfil/editar",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    loc = r.headers.get("location") or ""
    assert loc.startswith("/meu-perfil/editar")
    assert "msg=" in loc
    assert dbmod.autenticar_por_username("mazeta", "senha-nova99")


def test_meu_perfil_publico(client: TestClient):
    login_admin(client)
    from src import db as dbmod

    dono = dbmod.get_participante_por_admin_login("mazeta")
    assert dono
    r = client.get("/meu-perfil")
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
    assert 'data-viewer-id="' in r.text
    assert f'data-viewer-id="{dono["id"]}"' in r.text
    assert "/static/prototipo-perfil.js?v=34" in r.text
    js = (ROOT_DIR / "static" / "prototipo-perfil.js").read_text(encoding="utf-8")
    assert "proto-steam-post-nome" in js
    assert "proto-steam-post-av-link" in js
    assert "autor_id" in js
    assert 'id="proto-recados"' in r.text
    assert "postRecado" in js
    assert "loadRecadosEmbedded" in js
    assert "resolveAutorId" in js
    assert "perfilHref" in js
    assert 'id="public-recados-pager"' in r.text
    css = (ROOT_DIR / "static" / "style.css").read_text(encoding="utf-8")
    assert "proto-recados-pager" in css
    assert "grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr)" in css
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
    assert 'href="/meu-perfil/editar"' in r.text
    assert 'proto-steam-hero-bolao' not in r.text
    assert r.text.index('class="proto-steam-card"') < r.text.index('id="bolao"')
    assert r.text.index('id="bolao"') < r.text.index('id="recados"')
    assert "Protótipo ·" not in r.text


def test_sidebar_logado_brand_leva_ao_perfil(client: TestClient):
    """Nome/avatar no topo da sidebar abre Meu perfil."""
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
    assert 'href="/prototipo/perfil/publico"' not in r.text
    assert 'href="/meu-perfil"' in r.text
    assert 'class="site-brand-hint">Meu perfil</span>' in r.text
    brand = r.text.split('href="/meu-perfil" class="site-brand-user', 1)[1].split("</a>", 1)[0]
    assert "data-conta-open" not in brand
    assert "Meu perfil" in brand
    assert "Minha conta" not in brand
    assert 'href="/meu-perfil/editar"' in r.text
    assert "avatar-edit-trigger" in r.text


def test_meu_perfil_visitante(client: TestClient):
    login_admin(client)
    r = client.get("/meu-perfil?como=visitante")
    assert r.status_code == 200
    assert "visão de visitante" in r.text.lower()
    assert 'data-own="0"' in r.text
    assert 'id="public-amigo-pedir"' not in r.text
    assert 'id="public-recado-form"' in r.text
    assert 'id="public-feed-form"' not in r.text
    assert 'id="pedidos"' not in r.text
    assert "esquema de amizade" not in r.text.lower()
    # Preview do próprio perfil: não permite votar (agregação real)
    assert 'data-pode-votar="0"' in r.text
    assert "data-karma-cycle" not in r.text
    assert "proto-steam-karma--votavel" not in r.text
    assert "proto-steam-karma--line" in r.text
    assert "/static/prototipo-perfil.js?v=34" in r.text


def test_meu_perfil_dono_nao_vota_karma(client: TestClient):
    login_admin(client)
    r = client.get("/meu-perfil")
    assert r.status_code == 200
    assert 'data-own="1"' in r.text
    assert 'data-pode-votar="0"' in r.text
    assert "data-karma-cycle" not in r.text
    assert "proto-steam-karma--votavel" not in r.text
    assert "proto-steam-karma--line" in r.text
    assert 'id="proto-karma-resumo"' in r.text
    assert "/static/prototipo-perfil.js?v=34" in r.text


def test_perfil_outro_usuario(client: TestClient):
    from pathlib import Path

    from src import db as dbmod
    from src.config import AVATARES_DIR

    part = dbmod.criar_participante("Comum Bene", status="liberado", celular="11990009903")
    dbmod.definir_credenciais(part["id"], "comum.bene", "senha12345")
    client.get(f"/p/{part['token']}")

    alvo = dbmod.criar_participante("Benevides", status="liberado", celular="11990001122")
    av = Path(AVATARES_DIR) / "benevides-teste.jpg"
    av.parent.mkdir(parents=True, exist_ok=True)
    av.write_bytes(b"\xff\xd8\xff\xd9")
    dbmod.salvar_avatar(alvo["id"], "benevides-teste.jpg")

    r = client.get(f"/perfil/{alvo['id']}")
    assert r.status_code == 200
    assert "Benevides" in r.text
    assert 'data-fixado="1"' in r.text
    assert 'data-own="0"' in r.text
    assert f'data-viewer-id="{part["id"]}"' in r.text
    assert f'data-target-id="{alvo["id"]}"' in r.text
    assert 'id="proto-perfil-fixado"' in r.text
    assert 'id="public-amigo-pedir"' not in r.text
    assert 'id="recados"' in r.text
    assert 'id="public-recado-form"' in r.text
    assert "/avatars/benevides-teste.jpg" in r.text
    assert "data-public-avatar" in r.text
    assert "Protótipo ·" not in r.text


def test_perfil_proprio_id_redireciona_meu_perfil(client: TestClient):
    from src import db as dbmod

    part = dbmod.criar_participante("Self Redirect", status="liberado", celular="11990009904")
    dbmod.definir_credenciais(part["id"], "self.redir", "senha12345")
    client.get(f"/p/{part['token']}")
    r = client.get(f"/perfil/{part['id']}", follow_redirects=False)
    assert r.status_code in (303, 302)
    assert (r.headers.get("location") or "").startswith("/meu-perfil")


def test_legado_prototipo_redireciona(client: TestClient):
    login_admin(client)
    from src import db as dbmod

    part_b = dbmod.criar_participante("Benevides", status="liberado", celular="11990001122")

    r = client.get("/prototipo/perfil", follow_redirects=False)
    assert r.status_code == 301
    assert (r.headers.get("location") or "").startswith("/meu-perfil/editar")

    r = client.get("/prototipo/perfil/publico", follow_redirects=False)
    assert r.status_code == 301
    assert (r.headers.get("location") or "").startswith("/meu-perfil")

    r = client.get("/prototipo/perfil/benevides", follow_redirects=False)
    assert r.status_code == 301
    assert (r.headers.get("location") or "") == f"/perfil/{part_b['id']}"

    r = client.get("/prototipo/times/clubes.json", follow_redirects=False)
    assert r.status_code == 301
    assert (r.headers.get("location") or "") == "/meu-perfil/clubes.json"


def test_menu_perfil_fora_do_portal(client: TestClient):
    """Portal não lista atalhos de perfil; acesso só pelo brand Meu perfil."""
    r = client.get("/")
    assert r.status_code == 200
    assert 'href="/prototipo/perfil"' not in r.text
    assert "Protótipo: perfil" not in r.text
    assert "Perfil: Benevides" not in r.text

    login_admin(client)
    client.cookies.set("thdfm_ui_mode", "user", domain="testserver.local")
    r = client.get("/")
    assert r.status_code == 200
    assert "Protótipo: perfil" not in r.text
    assert "Perfil: Benevides" not in r.text
    assert 'href="/meu-perfil"' in r.text
    assert 'class="site-brand-hint">Meu perfil</span>' in r.text

    r = client.get("/admin")
    assert r.status_code == 200
    assert "Protótipo perfil" not in r.text
