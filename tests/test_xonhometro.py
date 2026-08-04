"""Xonhômetro — saídas e voltas do Xonha."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import src.db as db
from src.config import ROOT_DIR
from tests.conftest import login_admin as _login_admin


@pytest.fixture()
def admin_users():
    return "mazeta=senha-dono=Mazeta:dono|ramos=senha-mod=Ramos:moderador"


def test_xonhometro_publico_vazio(client: TestClient):
    part = db.criar_participante("Xonha Leitor", status="liberado", celular="11990005555")
    db.definir_credenciais(part["id"], "xonha.leitor", "senha12345")
    client.get(f"/p/{part['token']}")
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
    assert stats["status"] == "dentro"
    # Saídas no mesmo dia 10:15 → 22:40 = 12h25m
    assert stats["media_dias_entre_saidas"] == 0.5
    assert stats["media_tempo_entre_saidas_texto"] == (
        "12 horas, 25 minutos e 0 segundos"
    )
    assert stats["saidas_mes_atual"] >= 0
    assert stats["saidas_ultimos_30_dias"] >= 0
    assert stats["dias_desde_ultima_saida"] is not None
    assert stats["tempo_desde_ultima_saida_texto"]
    assert "segundo" in stats["tempo_desde_ultima_saida_texto"] or "minuto" in stats["tempo_desde_ultima_saida_texto"] or "hora" in stats["tempo_desde_ultima_saida_texto"] or "dia" in stats["tempo_desde_ultima_saida_texto"]
    assert stats["dias_no_status_atual"] is not None
    assert stats["status_desde"] == "2026-07-02T18:00:00"
    assert stats["status_duracao_texto"]
    assert "nesse status." in stats["status_duracao_texto"]
    # Tempo fora: última saída 22:40 → volta 18:00 = 19h20
    assert stats["tempo_medio_fora_texto"] == "19 horas, 20 minutos e 0 segundos"
    assert stats["maior_tempo_fora_texto"] == "19 horas, 20 minutos e 0 segundos"
    assert stats["tempo_medio_fora_dias"] == 0.81
    assert stats["recorde_permanencia_texto"]
    assert stats["recorde_permanencia_dias"] is not None
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
    assert "xonha-timeline-scroll" in pub.text
    assert "xonha-timeline-track" in pub.text
    assert "xonha-timeline-event" in pub.text
    assert "xonha-timeline-rail" in pub.text
    assert "xonha-timeline-anos" in pub.text
    assert "xonha-timeline-year" in pub.text
    assert "xonha-timeline-year-title" in pub.text
    assert ">2026<" in pub.text
    assert "xonha-motivo-mais" in pub.text
    assert "xonha-motivo-dialog" in pub.text
    assert "data-xonha-motivo-preview" in pub.text
    assert "data-xonha-motivo-full=" in pub.text
    assert "xonha-motivo-mais-icon" in pub.text
    assert "xonha-motivo-mais-slot" in pub.text
    assert 'role="button"' in pub.text
    assert "showModal" in pub.text
    assert "motivoTruncado" in pub.text
    css = (ROOT_DIR / "static" / "style.css").read_text(encoding="utf-8")
    assert "Altura fixa de 3 linhas" in css
    assert "transformava o + num bloco laranja enorme" in css
    assert "style.css?v=223" in (ROOT_DIR / "templates" / "base.html").read_text(encoding="utf-8")
    assert "overflow-x: hidden" in css
    assert "overscroll-behavior-x: contain" in css
    assert "Recorde de permanência" in pub.text
    assert "Média / dia desde o início" not in pub.text
    assert "Média de saída / mês" in pub.text
    assert "Mês com mais sumiços" in pub.text
    assert "Dias da semana" in pub.text
    assert "Maior sumiço" in pub.text
    assert "Horário campeão" in pub.text
    assert "xonha-status-block--dentro" in pub.text
    assert "Gerenciar registros" in pub.text
    assert "xonha-status-foto-wrap" in pub.text
    assert 'id="xonha-status-relogio"' in pub.text
    assert 'data-xonha-status-desde="2026-07-02T18:00:00"' in pub.text
    assert "nesse status." in pub.text
    assert "setInterval" in pub.text
    assert "Média de tempo entre saídas" in pub.text
    assert "Tempo desde a última saída" in pub.text
    assert "Dias desde a última saída" not in pub.text
    assert "12 horas, 25 minutos e 0 segundos" in pub.text
    assert "19 horas, 20 minutos e 0 segundos" in pub.text

def test_formatar_duracao_status_unidades():
    f = db.formatar_duracao_status
    assert f(0) == "Há 0 segundos nesse status."
    assert f(1) == "Há 1 segundo nesse status."
    assert f(59) == "Há 59 segundos nesse status."
    assert f(60) == "Há 1 minuto e 0 segundos nesse status."
    assert f(125) == "Há 2 minutos e 5 segundos nesse status."
    assert f(3600) == "Há 1 hora, 0 minutos e 0 segundos nesse status."
    assert f(4815) == "Há 1 hora, 20 minutos e 15 segundos nesse status."
    assert f(90061) == "Há 1 dia, 1 hora, 1 minuto e 1 segundo nesse status."
    assert f(2592000) == "Há 1 mês, 0 horas, 0 minutos e 0 segundos nesse status."
    assert f(31536000) == "Há 1 ano, 0 horas, 0 minutos e 0 segundos nesse status."

def test_formatar_duracao_sem_sufixo_de_status():
    assert db.formatar_duracao(3725, prefixo="", sufixo="") == (
        "1 hora, 2 minutos e 5 segundos"
    )


def test_agrupar_xonha_eventos_por_ano(client: TestClient):
    part = db.criar_participante("Leitor Anos", status="liberado", celular="11990007777")
    db.definir_credenciais(part["id"], "leitor.anos", "senha12345")
    client.get(f"/p/{part['token']}")

    db.criar_xonha_evento("saida", "2024-12-31", "fim 24", hora="23:00")
    db.criar_xonha_evento("volta", "2025-01-01", "ano novo", hora="00:10")
    db.criar_xonha_evento("banimento", "2025-06-15", "ban", hora="12:00")
    db.criar_xonha_evento("saida", "2026-03-01", "saiu", hora="09:00")

    grupos = db.agrupar_xonha_eventos_por_ano()
    assert [g["ano"] for g in grupos] == ["2026", "2025", "2024"]
    assert grupos[0]["quantidade"] == 1
    assert grupos[1]["quantidade"] == 2
    assert grupos[2]["quantidade"] == 1
    # Dentro do ano: ordem cronológica (antigo → novo)
    assert [e["data"] for e in grupos[1]["eventos"]] == ["2025-01-01", "2025-06-15"]

    pub = client.get("/xonhometro")
    assert pub.status_code == 200
    assert "xonha-timeline-anos" in pub.text
    assert ">2024<" in pub.text
    assert ">2025<" in pub.text
    assert ">2026<" in pub.text
    # Motivo longo deve trazer botão + e template do texto completo
    longo = "X" * 160
    db.criar_xonha_evento("saida", "2026-04-01", longo, hora="10:00")
    pub2 = client.get("/xonhometro")
    assert "xonha-motivo-mais" in pub2.text
    assert longo in pub2.text
    assert "data-xonha-motivo-mais" in pub2.text


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
    # Apagar usa modal custom; o único confirm() é o da importação WhatsApp.
    assert admin.text.count("confirm(") == 1
    assert "importar-whatsapp" in admin.text
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
    part = db.criar_participante("Menu Xonha", status="liberado", celular="11990006666")
    db.definir_credenciais(part["id"], "menu.xonha", "senha12345")
    client.get(f"/p/{part['token']}")
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
    part = db.criar_participante("Grupo Leitor", status="liberado", celular="11990007777")
    db.definir_credenciais(part["id"], "grupo.leitor", "senha12345")
    client.get(f"/p/{part['token']}")
    for path, title in (
        ("/grupo/bans", "Contador de Bans"),
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
    assert "xonha-status-foto-wrap" in pub.text
    assert "Passou do limite" in pub.text
    assert "R$2,00" in pub.text
    assert "Contagem desde" in pub.text
    assert "20/07/2026" in pub.text
    assert "1 saída" in pub.text
    assert "1 ban" in pub.text
    assert "Data com mais banimentos" in pub.text
    assert "xonha-weekday-seg--banimento" in pub.text


def test_xonha_metricas_mes_gaps_e_permanencia(client: TestClient):
    """Mês atual conta bans; gaps incluem bans; tempo fora e permanência em texto."""
    from datetime import date, timedelta

    _login_admin(client)
    hoje = date.today()
    ontem = hoje - timedelta(days=1)
    hoje_s = hoje.isoformat()
    ontem_s = ontem.isoformat()

    client.post(
        "/admin/xonhometro",
        data={"tipo": "saida", "data": ontem_s, "hora": "10:00", "motivo": "antes"},
        follow_redirects=False,
    )
    client.post(
        "/admin/xonhometro",
        data={"tipo": "volta", "data": ontem_s, "hora": "12:00", "motivo": "voltou rápido"},
        follow_redirects=False,
    )
    client.post(
        "/admin/xonhometro",
        data={"tipo": "banimento", "data": hoje_s, "hora": "09:00", "motivo": "ban do mês"},
        follow_redirects=False,
    )
    client.post(
        "/admin/xonhometro",
        data={"tipo": "volta", "data": hoje_s, "hora": "11:30", "motivo": "voltou do ban"},
        follow_redirects=False,
    )
    client.post(
        "/admin/xonhometro",
        data={"tipo": "saida", "data": hoje_s, "hora": "15:00", "motivo": "saiu de novo"},
        follow_redirects=False,
    )

    stats = db.xonha_stats()
    # Mês atual: pelo menos ban + saida de hoje (ontem pode ser outro mês no dia 1)
    assert stats["saidas_mes_atual"] >= 2
    assert stats["saidas_ultimos_30_dias"] >= 3
    # Gaps entre sumiços (saida + ban + saida)
    assert stats["media_tempo_entre_saidas_texto"]
    assert stats["media_dias_entre_saidas"] is not None
    # Tempos fora: 2h (ontem) e 2h30 (hoje) → média 2h15
    assert stats["tempo_medio_fora_texto"] == "2 horas, 15 minutos e 0 segundos"
    assert stats["maior_tempo_fora_texto"] == "2 horas, 30 minutos e 0 segundos"
    # Permanência: volta 12:00 → ban 09:00; volta 11:30 → saida 15:00 = 3h30
    assert stats["recorde_permanencia_texto"]
    assert "hora" in stats["recorde_permanencia_texto"] or "dia" in stats["recorde_permanencia_texto"]

    pub = client.get("/xonhometro")
    assert "Recorde de permanência" in pub.text
    assert "Média de saída / mês" in pub.text
    assert stats["tempo_medio_fora_texto"] in pub.text
