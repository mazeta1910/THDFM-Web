"""Fase C — Atividade / admin_audit."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from src import admin_audit as audit
from src import db
from tests.conftest import login_admin


@pytest.fixture()
def admin_users():
    return "mazeta=senha-dono=Mazeta:dono|ramos=senha-mod=Ramos:moderador"


def test_moderador_403_atividade(client: TestClient):
    login_admin(client, "ramos", "senha-mod")
    r = client.get("/admin/sistema/atividade", follow_redirects=False)
    assert r.status_code == 403


def test_dono_ve_atividade_vazia(client: TestClient):
    login_admin(client, "mazeta", "senha-dono")
    r = client.get("/admin/sistema/atividade")
    assert r.status_code == 200
    assert "Atividade" in r.text
    assert "admin-data-table" in r.text or "Sem atividade" in r.text
    assert "auditoria" in r.text.lower() or "Access log" in r.text or "Separado" in r.text


def test_liberar_gera_evento_com_antes_depois(client: TestClient):
    login_admin(client, "mazeta", "senha-dono")
    part = db.criar_participante("Audit User", celular="11999990001")
    assert part and part["status"] != "liberado"
    r = client.post(
        "/admin/liberar",
        data={"participante_id": part["id"]},
        follow_redirects=False,
    )
    assert r.status_code == 303
    events = audit.list_events(entidade="participante", entidade_id=str(part["id"]))
    assert events
    ev = events[0]
    assert ev["acao"] == "liberar"
    assert ev["autor"] == "mazeta"
    assert ev["antes_json"]
    assert ev["depois_json"]
    depois = json.loads(ev["depois_json"])
    assert depois.get("status") == "liberado"


def test_filtro_autor_e_periodo(client: TestClient):
    login_admin(client, "mazeta", "senha-dono")
    audit.record(
        autor="mazeta",
        acao="teste",
        entidade="sistema",
        resumo="evento filtro",
        path="/admin/sistema/atividade",
    )
    r = client.get("/admin/sistema/atividade?autor=mazeta&entidade=sistema")
    assert r.status_code == 200
    assert "evento filtro" in r.text or "teste" in r.text


def test_sanitize_esconde_senha():
    out = audit.sanitize({"nome": "x", "password": "segredo", "password_hash": "abc"})
    assert out["password"] == "…"
    assert out["password_hash"] == "…"
    assert out["nome"] == "x"


def test_inativar_aparece_na_ficha_bloco(client: TestClient):
    login_admin(client, "mazeta", "senha-dono")
    part = db.criar_participante(
        "Ficha Audit", status="liberado", celular="11999990002"
    )
    client.post("/admin/inativar", data={"participante_id": part["id"]})
    r = client.get("/admin?sec=inscricoes")
    assert r.status_code == 200
    assert "participante-audit-block" in r.text
    assert "inativar" in r.text
