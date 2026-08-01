"""Xonhômetro — saídas e voltas do Xonha."""

from __future__ import annotations

from datetime import date
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
    assert "saiu ou foi banido" in r.text
    assert "R$0,00" in r.text
    assert "Data com mais banimentos" in r.text
    assert "Taxa de retorno" not in r.text
    assert ">Saídas<" in r.text or "Saídas</span>" in r.text
    assert "xonha-counter-value" in r.text
    assert "/static/img/xonha.png" in r.text
    assert "xonha-status-foto" in r.text
    assert "xonha-timeline-track" in r.text or "xonha-empty" in r.text
    assert 'action="/admin/xonhometro"' not in r.text


def test_visitante_nao_cria_evento(client: TestClient):
    r = client.post(
        "/admin/xonhometro",
        data={"tipo": "saida", "data": "2026-07-01", "hora": "14:30", "motivo": "teste"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "acesso=entrar" in r.headers["location"]
    assert db.xonha_stats()["total_saidas"] == 0


def test_admin_registra_saida_e_volta_e_stats(client: TestClient):
    _login_admin(client)

    r = client.post(
        "/admin/xonhometro",
        data={
            "tipo": "saida",
            "data": "2026-07-01",
            "hora": "10:15",
            "motivo": "Brigou no zap",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "msg=" in r.headers["location"]

    client.post(
        "/admin/xonhometro",
        data={
            "tipo": "volta",
            "data": "2026-07-02",
            "hora": "18:00",
            "motivo": "Pediu desculpas",
        },
        follow_redirects=False,
    )
    client.post(
        "/admin/xonhometro",
        data={
            "tipo": "saida",
            "data": "2026-07-01",
            "hora": "22:40",
            "motivo": "Saiu de novo no mesmo dia",
        },
        follow_redirects=False,
    )

    stats = db.xonha_stats()
    assert stats["total_saidas"] == 2
    assert stats["total_voltas"] == 1
    assert stats["total_banimentos"] == 0
    assert stats["total_placar"] == 2
    assert stats["inicio_contagem"] == "2026-07-01"
    assert stats["recorde_dia"]["data"] == "2026-07-01"
    assert stats["recorde_dia"]["quantidade"] == 2
    assert stats["recorde_dia"]["saidas"] == 2
    assert stats["recorde_dia"]["banimentos"] == 0
    assert stats["media_saidas_por_mes"] == 2.0
    assert stats["recorde_mes"] is not None
    assert stats["recorde_mes"]["ano_mes"] == "2026-07"
    assert stats["recorde_mes"]["quantidade"] == 2
    assert stats["recorde_mes"]["saidas"] == 2
    assert stats["recorde_mes"]["banimentos"] == 0
    assert stats["recorde_banimento_dia"] is None
    assert stats["dias_semana"]
    assert len(stats["dias_semana"]) == 7
    assert sum(d["quantidade"] for d in stats["dias_semana"]) == 2
    assert all("saida_pct" in d and "ban_pct" in d for d in stats["dias_semana"])
    # Desde 01/07 até hoje
    dias = max((date.today() - date(2026, 7, 1)).days + 1, 1)
    assert stats["media_saidas_por_dia"] == round(2 / dias, 3)
    assert stats["status"] == "dentro"
    assert stats["media_dias_entre_saidas"] == 0.0
    assert stats["saidas_mes_atual"] >= 0
    assert stats["saidas_ultimos_30_dias"] >= 0
    assert stats["dias_desde_ultima_saida"] is not None
    assert stats["dias_no_status_atual"] is not None
    assert stats["tempo_medio_fora_dias"] is not None
    assert stats["maior_tempo_fora_dias"] is not None
    assert stats["horario_mais_comum"] is not None
    assert stats["horario_mais_comum"]["hora"] in ("10h", "22h")

    pub = client.get("/xonhometro")
    assert pub.status_code == 200
    assert "Brigou no zap" in pub.text
    assert "10:15" in pub.text
    assert "22:40" in pub.text
    assert "R$2,00" in pub.text
    assert "Contagem desde" in pub.text
    assert "01/07/2026" in pub.text
    assert "Data com mais banimentos" in pub.text
    assert "Taxa de retorno" not in pub.text
    assert "2 saídas" in pub.text
    assert "0 ban" in pub.text
    assert "xonha-weekday-seg--saida" in pub.text
    assert "xonha-timeline-track" in pub.text
    assert "xonha-timeline-event" in pub.text
    assert "Média / dia desde o início" in pub.text
    assert "Mês com mais sumiços" in pub.text
    assert "Dias da semana" in pub.text
    assert "Maior sumiço" in pub.text
    assert "Horário campeão" in pub.text
    assert "xonha-status-block--dentro" in pub.text
    assert "Gerenciar registros" in pub.text


def test_admin_atualiza_e_apaga(client: TestClient):
    _login_admin(client)
    ev = db.criar_xonha_evento("saida", "2026-06-10", "motivo antigo", hora="09:00")
    r = client.post(
        "/admin/xonhometro/atualizar",
        data={
            "evento_id": ev["id"],
            "tipo": "volta",
            "data": "2026-06-11",
            "hora": "11:30",
            "motivo": "motivo novo",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    updated = db.get_xonha_evento(ev["id"])
    assert updated is not None
    assert updated["tipo"] == "volta"
    assert updated["data"] == "2026-06-11"
    assert updated["hora"] == "11:30"
    assert updated["motivo"] == "motivo novo"

    admin = client.get("/admin/xonhometro")
    assert admin.status_code == 200
    assert "modal-xonha-apagar" in admin.text
    assert "data-xonha-apagar" in admin.text
    assert "confirm(" not in admin.text
    assert "xonha-admin-details" in admin.text
    assert 'class="xonha-admin-details"' in admin.text
    assert "xonha-btn-primary" not in admin.text
    assert 'aria-label="Registrar"' in admin.text
    assert "avatar-crop-modal" in admin.text

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
    assert "Grupo do WhatsApp" in r.text
    assert "Acervo Xonha" in r.text
    assert "Contador de Bans" in r.text
    assert "Listra" in r.text
    assert "Copypastas" in r.text
    assert "Cardápio" in r.text
    assert 'href="/xonhometro"' in r.text
    assert "Xonhômetro" in r.text
    assert 'ico(\'xonha\'' not in r.text  # rendered SVG, not macro call
    # Acervo Xonha começa maximizado no HTML
    assert 'data-group="acervo-xonha" open' in r.text
    assert "thdfm-site-menu-groups-v5" in r.text
    # Saiu do Portal
    portal = r.text.split('data-group="portal"', 1)[1].split("data-group=", 1)[0]
    assert "Xonhômetro" not in portal


def test_admin_xonhometro_nao_duplica_no_menu(client: TestClient):
    _login_admin(client)
    r = client.get("/admin")
    assert r.status_code == 200
    admin_block = r.text.split('data-group="admin"', 1)[1].split("data-group=", 1)[0]
    assert "Xonhômetro" not in admin_block
    assert "Acervo Xonha" in r.text
    assert r.text.count(">Xonhômetro<") == 1


def test_paginas_grupo_placeholder(client: TestClient):
    for path, title in (
        ("/grupo/bans", "Contador de Bans"),
        ("/grupo/listra", "Listra"),
        ("/grupo/copypastas", "Copypastas"),
        ("/grupo/cardapio", "Cardápio"),
    ):
        r = client.get(path)
        assert r.status_code == 200
        assert title in r.text
        assert "em-breve-page" in r.text
        assert "Grupo do WhatsApp" in r.text or "Acervo Xonha" in r.text


def test_moderador_tambem_gerencia(client: TestClient):
    _login_admin(client, "ramos", "senha-mod")
    r = client.get("/admin/xonhometro")
    assert r.status_code == 200
    assert "Novo registro" in r.text
    assert "xonha-select-wrap" in r.text
    assert 'value="banimento"' in r.text
    r2 = client.post(
        "/admin/xonhometro",
        data={
            "tipo": "saida",
            "data": "2026-05-05",
            "hora": "16:05",
            "motivo": "Ramos anotou",
        },
        follow_redirects=False,
    )
    assert r2.status_code == 303
    assert db.xonha_stats()["total_saidas"] == 1


def test_admin_registra_banimento(client: TestClient):
    _login_admin(client)
    client.post(
        "/admin/xonhometro",
        data={
            "tipo": "saida",
            "data": "2026-07-20",
            "hora": "10:00",
            "motivo": "Saiu de manhã",
        },
        follow_redirects=False,
    )
    r = client.post(
        "/admin/xonhometro",
        data={
            "tipo": "banimento",
            "data": "2026-07-20",
            "hora": "21:10",
            "motivo": "Passou do limite",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    stats = db.xonha_stats()
    assert stats["total_banimentos"] == 1
    assert stats["total_saidas"] == 1
    assert stats["total_placar"] == 2
    assert stats["status"] == "banido"
    assert stats["inicio_contagem"] == "2026-07-20"
    # Recorde do dia soma saída + banimento no mesmo dia
    assert stats["recorde_dia"] is not None
    assert stats["recorde_dia"]["data"] == "2026-07-20"
    assert stats["recorde_dia"]["quantidade"] == 2
    assert stats["recorde_dia"]["saidas"] == 1
    assert stats["recorde_dia"]["banimentos"] == 1
    assert stats["recorde_banimento_dia"] is not None
    assert stats["recorde_banimento_dia"]["data"] == "2026-07-20"
    assert stats["recorde_banimento_dia"]["quantidade"] == 1

    pub = client.get("/xonhometro")
    assert pub.status_code == 200
    assert "Banimento" in pub.text
    assert "banido do grupo" in pub.text
    assert "xonha-status-block--banido" in pub.text
    assert "Passou do limite" in pub.text
    assert "R$2,00" in pub.text
    assert "Contagem desde" in pub.text
    assert "20/07/2026" in pub.text
    assert "1 saída" in pub.text
    assert "1 ban" in pub.text
    assert "Data com mais banimentos" in pub.text
    assert "xonha-weekday-seg--banimento" in pub.text
