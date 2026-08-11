"""Hall das Lendas — protótipo público."""

from __future__ import annotations

from fastapi.testclient import TestClient

from src.config import ROOT_DIR
from tests.conftest import login_admin


def test_hall_lendas_publico_sem_login(client: TestClient):
    r = client.get("/hall-lendas", follow_redirects=False)
    assert r.status_code == 200
    assert "Hall das Lendas" in r.text
    assert "Protótipo visual" in r.text
    assert "Ramos" in r.text
    assert "João JEC" in r.text
    assert "Benevides" in r.text
    # Valor oculto para visitante
    assert "R$ 500,00" not in r.text
    assert "Total doado" not in r.text
    assert "hall-lendas-badge" in r.text
    assert "hall-lendas-avatar--anel" in r.text


def test_hall_lendas_valor_so_mazeta(client: TestClient):
    login_admin(client)
    r = client.get("/hall-lendas")
    assert r.status_code == 200
    assert "R$ 500,00" in r.text
    assert "Total doado" in r.text
    assert "Visão Mazeta" in r.text


def test_sidebar_hall_lendas_vira_link(client: TestClient):
    r = client.get("/")
    assert r.status_code == 200
    html = r.text
    assert 'href="/hall-lendas"' in html
    chunk = html.split("site-hall-lendas", 1)[1].split(">", 1)[0]
    assert "disabled" not in chunk
    side = (ROOT_DIR / "templates" / "partials" / "site_sidebar.html").read_text(
        encoding="utf-8"
    )
    assert 'href="/hall-lendas"' in side
    assert "disabled" not in side.split("site-hall-lendas", 1)[1].split("</a>", 1)[0]
