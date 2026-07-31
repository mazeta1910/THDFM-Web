"""Xonhômetro — saídas e voltas do Xonha."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import src.db as db
from src.config import ROOT_DIR


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(ROOT_DIR)
    monkeypatch.setenv(
        "ADMIN_USERS",
        "mazeta=senha-dono=Mazeta:dono|ramos=senha-mod=Ramos:moderador",
    )
    db.DB_PATH = tmp_path / "test.db"
    (tmp_path / "avatars").mkdir(exist_ok=True)
    (tmp_path / "comprovantes").mkdir(exist_ok=True)
    db.init_db()

    from src.app import app

    with TestClient(app) as c:
        yield c


def _login_admin(client: TestClient, login: str = "mazeta", senha: str = "senha-dono"):
    r = client.post(
        "/admin/login",
        data={"login": login, "password": senha},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/admin"


def test_xonhometro_publico_vazio(client: TestClient):
    r = client.get("/xonhometro")
    assert r.status_code == 200
    assert "Xonhômetro" in r.text
    assert "Saídas registradas" in r.text
    assert "xonha-counter-value" in r.text
    assert 'action="/admin/xonhometro"' not in r.text


def test_visitante_nao_cria_evento(client: TestClient):
    r = client.post(
        "/admin/xonhometro",
        data={"tipo": "saida", "data": "2026-07-01", "motivo": "teste"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "acesso=entrar" in r.headers["location"]
    assert db.xonha_stats()["total_saidas"] == 0


def test_admin_registra_saida_e_volta_e_stats(client: TestClient):
    _login_admin(client)

    r = client.post(
        "/admin/xonhometro",
        data={"tipo": "saida", "data": "2026-07-01", "motivo": "Brigou no zap"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "msg=" in r.headers["location"]

    client.post(
        "/admin/xonhometro",
        data={"tipo": "volta", "data": "2026-07-02", "motivo": "Pediu desculpas"},
        follow_redirects=False,
    )
    client.post(
        "/admin/xonhometro",
        data={
            "tipo": "saida",
            "data": "2026-07-01",
            "motivo": "Saiu de novo no mesmo dia",
        },
        follow_redirects=False,
    )

    stats = db.xonha_stats()
    assert stats["total_saidas"] == 2
    assert stats["total_voltas"] == 1
    assert stats["recorde_dia"] is not None
    assert stats["recorde_dia"]["data"] == "2026-07-01"
    assert stats["recorde_dia"]["quantidade"] == 2
    assert stats["media_saidas_por_mes"] == 2.0
    # Último evento por data: volta em 02/07 → dentro
    assert stats["status"] == "dentro"
    assert stats["media_dias_entre_saidas"] == 0.0  # duas saídas no mesmo dia

    pub = client.get("/xonhometro")
    assert pub.status_code == 200
    assert "Brigou no zap" in pub.text
    assert "Pediu desculpas" in pub.text
    assert "Recorde" in pub.text
    assert "Gerenciar registros" in pub.text


def test_admin_atualiza_e_apaga(client: TestClient):
    _login_admin(client)
    ev = db.criar_xonha_evento("saida", "2026-06-10", "motivo antigo")
    r = client.post(
        "/admin/xonhometro/atualizar",
        data={
            "evento_id": ev["id"],
            "tipo": "volta",
            "data": "2026-06-11",
            "motivo": "motivo novo",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    updated = db.get_xonha_evento(ev["id"])
    assert updated is not None
    assert updated["tipo"] == "volta"
    assert updated["data"] == "2026-06-11"
    assert updated["motivo"] == "motivo novo"

    r2 = client.post(
        "/admin/xonhometro/apagar",
        data={"evento_id": ev["id"]},
        follow_redirects=False,
    )
    assert r2.status_code == 303
    assert db.get_xonha_evento(ev["id"]) is None


def test_menu_tem_xonhometro(client: TestClient):
    r = client.get("/")
    assert r.status_code == 200
    assert 'href="/xonhometro"' in r.text
    assert "Xonhômetro" in r.text


def test_moderador_tambem_gerencia(client: TestClient):
    _login_admin(client, "ramos", "senha-mod")
    r = client.get("/admin/xonhometro")
    assert r.status_code == 200
    assert "Novo registro" in r.text
    r2 = client.post(
        "/admin/xonhometro",
        data={"tipo": "saida", "data": "2026-05-05", "motivo": "Ramos anotou"},
        follow_redirects=False,
    )
    assert r2.status_code == 303
    assert db.xonha_stats()["total_saidas"] == 1
