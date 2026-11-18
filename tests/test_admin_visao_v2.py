"""Visão geral v2: KPIs reais + blocos gated por sistema.ver."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import src.db as db
from src.config import ROOT_DIR
from tests.conftest import login_admin


@pytest.fixture()
def admin_users():
    return "mazeta=senha-dono=Mazeta:dono|ramos=senha-mod=Ramos:moderador"


def test_visao_dono_ve_seis_blocos(client: TestClient):
    login_admin(client, "mazeta", "senha-dono")
    r = client.get("/admin/visao")
    assert r.status_code == 200
    html = r.text
    assert "Cobrança de palpite" in html
    assert "Jogos sem placar" in html
    assert "Liberados" in html
    assert "admin-visao-atalhos" in html
    assert "Precisa de mim agora" in html
    assert "Fase atual" in html
    assert "Confrontos" in html
    assert "Últimos acessos" in html
    assert "Atividade recente" in html
    assert 'aria-label="Sistema"' in html
    assert "admin-visao-ficha" in html
    assert "admin-visao-cols" in html
    assert "/admin/cobranca?fase=" in html
    assert 'href="/admin/sistema/saude"' in html
    assert 'href="/health"' not in html.split("admin-kpi-row", 1)[1].split("Precisa de mim", 1)[0]
    # Números da ficha não podem ficar só com "/" / "min"
    assert "Oitavas" in html or "oitavas" in html.lower()
    assert "30 min" in html


def test_visao_moderador_sem_sistema(client: TestClient):
    login_admin(client, "ramos", "senha-mod")
    r = client.get("/admin/visao")
    assert r.status_code == 200
    html = r.text
    assert "Cobrança de palpite" in html
    assert "Fase atual" in html
    assert "Últimos acessos" not in html
    assert "Atividade recente" not in html
    assert 'aria-label="Sistema"' not in html
    assert "/admin/sistema/rotas" not in html


def test_visao_precisa_cobranca_quando_incompleto(client: TestClient):
    login_admin(client, "mazeta", "senha-dono")
    falta = db.criar_participante("Visao Falta", status="liberado", celular="11990001111")
    db.definir_email_participante(falta["id"], "visao@thdfm.test")
    confrontos = db.list_confrontos_completos("oitavas")
    for c in confrontos:
        ida = next(j for j in c["jogos"] if j["perna"] == "ida")
        db.set_inicio_jogo(ida["id"], "2099-08-10 20:00")
    db.set_janela("ida")
    db.set_fase_atual("oitavas")

    r = client.get("/admin/visao")
    assert r.status_code == 200
    assert "palpite(s) incompleto(s)" in r.text
    assert 'href="/admin/cobranca?fase=oitavas&perna=ida"' in r.text


def test_visao_css_contract():
    css = (ROOT_DIR / "static/css/28-email-gate.css").read_text(encoding="utf-8")
    assert ".admin-visao-ficha" in css
    assert ".admin-visao-dl" in css
    assert ".admin-kpi-n--bad" in css
    assert ".admin-visao-atalhos" in css
    assert ".admin-visao-cols" in css
    base = (ROOT_DIR / "templates/base.html").read_text(encoding="utf-8")
    assert "style.css?v=389" in base


def test_sistema_saude_html_nao_json(client: TestClient):
    login_admin(client, "mazeta", "senha-dono")
    r = client.get("/admin/sistema/saude")
    assert r.status_code == 200
    assert "text/html" in (r.headers.get("content-type") or "")
    assert "<h1>Saúde</h1>" in r.text
    assert "admin-visao-ficha" in r.text
    # JSON bruto continua só em /health
    raw = client.get("/health")
    assert raw.status_code == 200
    assert "application/json" in (raw.headers.get("content-type") or "")
