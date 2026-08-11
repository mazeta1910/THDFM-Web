"""Hall das Lendas — protótipo só Mazeta."""

from __future__ import annotations

from fastapi.testclient import TestClient

from src.config import ROOT_DIR
from tests.conftest import login_admin


def test_hall_lendas_bloqueado_sem_mazeta(client: TestClient):
    r = client.get("/hall-lendas", follow_redirects=False)
    assert r.status_code in (303, 302)
    loc = r.headers.get("location") or ""
    assert "acesso=entrar" in loc or "/admin" in loc or loc.startswith("/")


def test_hall_lendas_so_mazeta(client: TestClient):
    login_admin(client)
    r = client.get("/hall-lendas")
    assert r.status_code == 200
    assert "Hall das Lendas" in r.text
    assert "Protótipo visual" in r.text
    assert "Ramos" in r.text
    assert "João JEC" in r.text
    assert "Benevides" in r.text
    assert "R$ 500,00" in r.text
    assert "Total doado" in r.text
    assert "Visão Mazeta" in r.text
    assert "hall-lendas-badge" in r.text
    assert "hall-lendas-avatar--anel" in r.text


def test_sidebar_hall_lendas_link_so_mazeta(client: TestClient):
    # Visitante: botão disabled "Em breve"
    r = client.get("/")
    assert r.status_code == 200
    assert "Hall das Lendas" in r.text
    assert 'disabled' in r.text.split("site-hall-lendas", 1)[1].split(">", 1)[0]
    assert 'href="/hall-lendas"' not in r.text.split("site-menu-fixed", 1)[1].split(
        "data-menu-sortable", 1
    )[0]

    login_admin(client)
    r2 = client.get("/")
    assert r2.status_code == 200
    fixed = r2.text.split("site-menu-fixed", 1)[1].split("data-menu-sortable", 1)[0]
    assert 'href="/hall-lendas"' in fixed
    assert "disabled" not in fixed.split("site-hall-lendas", 1)[1].split(">", 1)[0]

    side = (ROOT_DIR / "templates" / "partials" / "site_sidebar.html").read_text(
        encoding="utf-8"
    )
    assert "is_mazeta" in side
    assert 'href="/hall-lendas"' in side
