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
    assert "palpites iguais" in ids["casalzinho"]["valor_label"]
    assert "iguais/par" not in ids["casalzinho"]["valor_label"]
    assert ids["donelli"]["mostrar_fotos"] is True
    assert ids["donelli"]["pessoas"][0]["nome"] == "Gama"
    assert ids["casalzinho"]["mostrar_fotos"] is True
    assert "placar_visto" in ids
    assert ids["placar_visto"]["quem_label"] == "Qual"
    assert ids["placar_visto"]["nomes_label"] in {"2×0", "0×3"} or "×" in ids["placar_visto"]["nomes_label"]
    assert "×" in ids["placar_visto"]["valor_label"]
    assert "(" not in ids["placar_visto"]["valor_label"]
    # Arqui (se houver) fica por último e em linha cheia
    if "arqui_inimigos" in ids:
        assert hall["cards"][-1]["id"] == "arqui_inimigos"
        assert ids["arqui_inimigos"]["linha_cheia"] is True

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
    assert "palpites iguais" in r.text
    assert "iguais/par" not in r.text
    assert ">Qual<" in r.text or "planilha-metrica-label\">Qual<" in r.text
    assert "Quantidade" in r.text
    assert "planilha-metrica-label\">Marca<" not in r.text
    assert "hall-avatar" in r.text
    assert "data-abrir-ficha" in r.text
    assert "ficha-estilo-card" in r.text
    assert "Exportar ficha em PNG" in r.text


def test_empate_muitos_nomes_resume_lista(client):
    login_admin(client)
    nomes = [f"P{i}" for i in range(5)]
    parts = [db.criar_participante(n, status="liberado") for n in nomes]
    _cinfo, jogo = _jogo_oitavas()
    for p in parts:
        db.salvar_palpite_jogo(p["id"], jogo["id"], 2, 0)
    db.set_resultado_jogo(jogo["id"], 0, 1)

    hall = trofeus_hall("oitavas")
    ids = {card["id"]: card for card in hall["cards"]}
    assert "boquinha" in ids
    assert len(ids["boquinha"]["nomes"]) == 5
    assert "e mais 1" in ids["boquinha"]["nomes_label"]
    assert ids["boquinha"]["mostrar_fotos"] is True
    assert len(ids["boquinha"]["pessoas_foto"]) == 4
    assert ids["boquinha"]["fotos_extra"] == 1

    r = client.get("/classificacao")
    assert r.status_code == 200
    assert "hall-avatar-more" in r.text
    assert ">+1<" in r.text or "+1" in r.text
    assert "hall-card-fullrow" in r.text or "arqui_inimigos" not in ids


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
