"""Fase B — Access log: política, IP truncado, UI dono-only, purge."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from src import access_log as alog
from src import db
from tests.conftest import login_admin


@pytest.fixture()
def admin_users():
    return "mazeta=senha-dono=Mazeta:dono|ramos=senha-mod=Ramos:moderador"


def test_truncate_ip_v4_e_v6():
    assert alog.truncate_ip("203.0.113.77") == "203.0.113.0"
    assert alog.truncate_ip("203.0.113.77, 10.0.0.1") == "203.0.113.0"
    assert alog.truncate_ip("2001:db8:85a3:0000:0000:8a2e:0370:7334").startswith(
        "2001:db8:85a3::"
    )
    assert alog.truncate_ip("") == "—"


def test_politica_detail_vs_agg():
    assert alog.wants_detail(path="/admin", method="GET", autenticado=False)
    assert alog.wants_detail(path="/classificacao", method="POST", autenticado=False)
    assert alog.wants_detail(path="/bolao/meus-palpites", method="GET", autenticado=True)
    assert not alog.wants_detail(
        path="/classificacao", method="GET", autenticado=False
    )
    assert alog.should_skip("/static/style.css", "GET")
    assert alog.should_skip("/health", "GET")


def test_record_detail_e_agg_e_filtros(client: TestClient):
    alog.record_hit(
        method="GET",
        path="/admin/visao",
        status=200,
        quem="mazeta",
        quem_tipo="admin",
        ip_raw="198.51.100.42",
        ua_raw="Mozilla/5.0 TestAgent/1.0",
        autenticado=True,
        ts="2026-11-12 15:40:00",
    )
    alog.record_hit(
        method="GET",
        path="/classificacao",
        status=200,
        quem="—",
        quem_tipo="anon",
        ip_raw="198.51.100.99",
        ua_raw="curl/8",
        autenticado=False,
        ts="2026-11-12 15:41:00",
    )
    hits = alog.list_hits(path="/admin", dia="2026-11-12")
    assert len(hits) == 1
    assert hits[0]["quem"] == "mazeta"
    assert hits[0]["ip_trunc"] == "198.51.100.0"
    assert hits[0]["method"] == "GET"

    agg = alog.list_agg(dia="2026-11-12", path="/classificacao")
    assert len(agg) == 1
    assert agg[0]["hits"] == 1


def test_purge_retencao_com_registro(client: TestClient):
    velho = (datetime.now() - timedelta(days=20)).strftime("%Y-%m-%d %H:%M:%S")
    alog.record_hit(
        method="GET",
        path="/admin",
        status=200,
        quem="mazeta",
        quem_tipo="admin",
        ip_raw="10.0.0.8",
        ua_raw="t",
        autenticado=True,
        ts=velho,
    )
    assert alog.count_hits() >= 1
    reg = alog.purge_expired(por="teste", force_record=True)
    assert reg["removidos_detalhe"] >= 1
    assert alog.ultimo_purge() is not None
    assert alog.count_hits(path="/admin") == 0


def test_moderador_403_access_log(client: TestClient):
    login_admin(client, "ramos", "senha-mod")
    r = client.get("/admin/sistema/access-log", follow_redirects=False)
    assert r.status_code == 403
    assert "Só o Dono" in r.text


def test_dono_ve_access_log_e_filtra(client: TestClient):
    login_admin(client, "mazeta", "senha-dono")
    # Gera hit autenticado em outra rota admin (access-log GET é skip).
    client.get("/admin/visao")
    alog.record_hit(
        method="GET",
        path="/admin/palpites",
        status=200,
        quem="mazeta",
        quem_tipo="admin",
        ip_raw="203.0.113.10",
        ua_raw="pytest",
        autenticado=True,
        ts=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )
    dia = datetime.now().strftime("%Y-%m-%d")
    r = client.get(f"/admin/sistema/access-log?path=/admin&dia={dia}&quem=mazeta")
    assert r.status_code == 200
    assert "admin-data-table" in r.text
    assert "Access log" in r.text
    assert "retenção 14d" in r.text
    assert "/admin" in r.text
    assert "Filtrar" in r.text


def test_purge_endpoint_dono(client: TestClient):
    login_admin(client, "mazeta", "senha-dono")
    r = client.post("/admin/sistema/access-log/purge", follow_redirects=False)
    assert r.status_code == 303
    assert "/admin/sistema/access-log" in (r.headers.get("location") or "")
    assert alog.ultimo_purge() is not None


def test_atividade_nao_e_mais_placeholder(client: TestClient):
    login_admin(client, "mazeta", "senha-dono")
    r = client.get("/admin/sistema/atividade")
    assert r.status_code == 200
    assert "Fase C (auditoria" not in r.text
    assert "Atividade" in r.text


def test_middleware_grava_admin_hit(client: TestClient):
    login_admin(client, "mazeta", "senha-dono")
    before = alog.count_hits(path="/admin/visao")
    client.get("/admin/visao")
    after = alog.count_hits(path="/admin/visao")
    assert after >= before + 1
