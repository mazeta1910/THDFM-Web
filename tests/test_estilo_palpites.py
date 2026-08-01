"""Hall da Desgraça, ficha, gate de login e inscrição fechada."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import src.db as db
from src.config import inscricao_aberta
from src.estilo_palpites import consenso_por_jogo, trofeus_hall
from tests.conftest import login_admin


def _jogo_oitavas():
    confrontos = db.list_confrontos_completos("oitavas")
    c = confrontos[0]
    return c, c["jogos"][0]


def test_inscricao_aberta_helper():
    tz = ZoneInfo("America/Sao_Paulo")
    assert inscricao_aberta(agora=datetime(2026, 8, 1, 13, 29, tzinfo=tz)) is True
    assert inscricao_aberta(agora=datetime(2026, 8, 1, 13, 30, tzinfo=tz)) is False
    assert inscricao_aberta(agora=datetime(2026, 8, 1, 16, 12, tzinfo=tz)) is False


def test_gate_bloqueia_anonimo(client):
    for path in ("/classificacao", "/regras", "/transparencia", "/xonhometro", "/grupo/listra"):
        r = client.get(path, follow_redirects=False)
        assert r.status_code == 303, path
        assert r.headers["location"].startswith("/?acesso=entrar")


def test_home_continua_publica(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Entrar" in r.text
    assert "Fazer inscrição" not in r.text


def test_inscricao_encerrada_hoje(client):
    r = client.get("/inscricao")
    assert r.status_code == 200
    assert "Inscrições encerradas" in r.text
    r2 = client.post(
        "/inscricao",
        data={"nome": "Fulano", "celular": "11999999999"},
        files={"comprovante": ("x.png", b"fake", "image/png")},
        follow_redirects=False,
    )
    assert r2.status_code == 303


def test_boquinha_e_donelli_e_casalzinho(client):
    login_admin(client)
    a = db.criar_participante("Alpha", status="liberado")
    b = db.criar_participante("Beta", status="liberado")
    c = db.criar_participante("Gama", status="liberado")
    cinfo, jogo = _jogo_oitavas()
    # Consenso: casa (2x0) com Alpha e Beta; Gama vai de fora
    db.salvar_palpite_jogo(a["id"], jogo["id"], 2, 0)
    db.salvar_palpite_jogo(b["id"], jogo["id"], 2, 0)
    db.salvar_palpite_jogo(c["id"], jogo["id"], 0, 3)
    # Resultado: fora ganha → Alpha/Beta são Boquinha; Gama acertou underdog
    db.set_resultado_jogo(jogo["id"], 0, 1)

    cons = consenso_por_jogo()
    assert cons[jogo["id"]]["lado"] == "casa"

    hall = trofeus_hall("oitavas")
    ids = {card["id"]: card for card in hall["cards"]}
    assert "boquinha" in ids
    assert set(ids["boquinha"]["nomes"]) == {"Alpha", "Beta"}
    assert "cacador_zica" in ids
    assert ids["cacador_zica"]["nomes"] == ["Gama"]
    assert "donelli" in ids
    # Gama 0×3 = 3 gols; Alpha/Beta 2 — Donelli é Gama
    assert "Gama" in ids["donelli"]["nomes"]
    assert "casalzinho" in ids
    assert set(ids["casalzinho"]["nomes"]) == {"Alpha", "Beta"}

    # Classificação renderiza Hall da Desgraça em cards exportáveis
    r = client.get("/classificacao")
    assert r.status_code == 200
    assert "Hall da Desgraça" in r.text
    assert "classificacao-hall-card" in r.text
    assert "classificacao-hall-grid" in r.text
    assert "planilha-metrica-card" in r.text
    assert 'data-export-slug="hall"' in r.text
    assert "data-classificacao-export" in r.text
    assert "Exportar Hall da Desgraça em PNG" in r.text
    assert "Boquinha de Cemitério" in r.text
    assert "Acha que todo goleiro é o Matheus Donelli" in r.text
    assert "Triângulo Amoroso" in r.text or "Casalzinho" in r.text
    assert "data-abrir-ficha" in r.text
    assert "ficha-estilo-card" in r.text
    assert "Exportar ficha em PNG" in r.text


def test_triangulo_e_quarteto(client):
    p1 = db.criar_participante("T1", status="liberado")
    p2 = db.criar_participante("T2", status="liberado")
    p3 = db.criar_participante("T3", status="liberado")
    p4 = db.criar_participante("T4", status="liberado")
    p5 = db.criar_participante("Solo", status="liberado")
    confrontos = db.list_confrontos_completos("oitavas")
    jogos = [j for c in confrontos for j in c["jogos"]][:3]
    for j in jogos:
        for p in (p1, p2, p3, p4):
            db.salvar_palpite_jogo(p["id"], j["id"], 1, 0)
        db.salvar_palpite_jogo(p5["id"], j["id"], 4, 4)

    hall = trofeus_hall("oitavas")
    ids = {card["id"]: card for card in hall["cards"]}
    assert "triangulo" in ids
    assert "quarteto" in ids
    assert len(ids["quarteto"]["nomes"]) == 4
    assert "arqui_inimigos" in ids
    assert ids["arqui_inimigos"]["multi"] is True
