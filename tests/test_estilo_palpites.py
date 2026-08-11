"""Hall da Desgraça, ficha, gate de login e inscrição fechada."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import src.db as db
from src.config import ROOT_DIR, inscricao_aberta
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

    # Benevides na tabela liga ao perfil (sem ficha modal)
    db.criar_participante("Benevides", status="liberado", celular="11990001122")

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
    # Ficha "Estilo de palpites" saiu da classificação (foi para o perfil)
    assert "data-abrir-ficha" not in r.text
    assert "ficha-estilo-card" not in r.text
    assert "Exportar ficha em PNG" not in r.text
    assert "Estilo de palpites" not in r.text
    assert "perfis-estilo-json" not in r.text
    assert "Clique no nome para ver o estilo de palpites" not in r.text
    assert "/static/style.css?v=310" in r.text
    assert 'href="/perfil/' in r.text
    assert "classificacao-player-link" in r.text
    assert "classificacao-nome-btn" not in r.text
    assert 'href="/prototipo/perfil/benevides"' not in r.text

    hall = trofeus_hall("oitavas")
    perfil = next(p for p in hall["perfis"].values() if p["nome"] == "Alpha")
    assert perfil["n_casa"] >= 1
    assert perfil["n"] >= 1
    assert all(b["id"] != "arqui_inimigos" for b in perfil.get("badges") or [])


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


def test_resumo_rodadas_helper_e_sem_ficha_na_classificacao(client):
    """Resumo Ida/Volta continua no helper; classificação não embute a ficha."""
    from src.ranking import confirmar_rodada, resumo_pontuacao_por_participante

    login_admin(client)
    a = db.criar_participante("Alpha", status="liberado")
    b = db.criar_participante("Beta", status="liberado")
    confrontos = db.list_confrontos_completos("oitavas")
    c0 = confrontos[0]
    ida = next(j for j in c0["jogos"] if j["perna"] == "ida")
    volta = next(j for j in c0["jogos"] if j["perna"] == "volta")
    db.salvar_palpite_jogo(a["id"], ida["id"], 2, 0)
    db.salvar_palpite_jogo(b["id"], ida["id"], 0, 1)
    db.set_resultado_jogo(ida["id"], 0, 1)

    hist = confirmar_rodada()
    assert hist["numero"] == 1
    assert hist["janela"] == "ida"

    # Fechamento fantasma (ninguém pontuou) — omitido no resumo
    fantasma = confirmar_rodada()
    assert fantasma["numero"] == 2

    db.salvar_palpite_jogo(a["id"], volta["id"], 1, 0)
    db.salvar_palpite_jogo(b["id"], volta["id"], 0, 0)
    db.set_resultado_jogo(volta["id"], 1, 0)
    hist2 = confirmar_rodada()
    assert hist2["numero"] == 3
    assert hist2["janela"] == "volta"

    # Segunda confirmação em Volta (duplicata) — não deve criar outra linha Oit·Volta
    fantasma_volta = confirmar_rodada()
    assert fantasma_volta["numero"] == 4

    resumo = resumo_pontuacao_por_participante()
    assert a["id"] in resumo
    entradas = resumo[a["id"]]
    assert len(entradas) == 3
    assert entradas[0]["rotulo"] == "Rodada 1"
    assert entradas[0]["rotulo_curto"] == "R1"
    assert entradas[0]["janela"] == "ida"
    assert entradas[0]["janela_label"] == "Ida"
    assert entradas[0]["fase_label"] == "Oitavas"
    assert entradas[0]["fase_label_curta"] == "Oit"
    assert entradas[0]["jogos"]
    assert any(j.get("palpite_m") is not None for j in entradas[0]["jogos"])
    assert any(j.get("casa_emblema") for j in entradas[0]["jogos"])
    assert entradas[1]["janela"] == "volta"
    assert entradas[1]["janela_label"] == "Volta"
    assert entradas[1]["jogos"]
    assert entradas[2]["rotulo"] == "Rodada 3"
    assert entradas[2]["ao_vivo"] is True
    assert entradas[2]["fase_label"] == "Oitavas"
    assert entradas[2]["rod"] == 0
    assert entradas[0]["posicao"] is not None
    # Só uma Volta das Oitavas (sem R3/R4 duplicada)
    assert sum(1 for e in entradas if e.get("janela") == "volta" and not e["ao_vivo"]) == 1

    r = client.get("/classificacao")
    assert r.status_code == 200
    assert "Estilo de palpites" not in r.text
    assert "ficha-estilo-card" not in r.text
    assert "perfis-estilo-json" not in r.text
    assert "data-abrir-ficha" not in r.text
    assert "/static/style.css?v=310" in r.text
    css = (ROOT_DIR / "static" / "style.css").read_text(encoding="utf-8")
    # Estilos compartilhados com o perfil (resumo de rodadas) permanecem
    assert ".ficha-rodada-rotulo-short" in css
    assert ".ficha-rodadas-lista" in css
    assert ".ficha-jogo-embl" in css
    assert ".ficha-jogos-cols" in css
    assert ".ficha-jogo-mark.is-ok" in css
    assert ".ficha-jogo-mark.is-miss" in css
    assert ".ficha-jogo-mark.is-na" in css
    assert ".ficha-dialog" not in css
    assert ".ficha-estilo-card" not in css

    # Perfil: rótulo curto no HTML (mobile esconde o full via CSS)
    db.definir_credenciais(a["id"], "alpha.rodadas", "senha12345")
    client.get(f"/p/{a['token']}")
    rp = client.get("/meu-perfil")
    assert rp.status_code == 200
    assert "ficha-rodada-rotulo-full" in rp.text
    assert "ficha-rodada-rotulo-short" in rp.text
    assert "R1 · Oitavas (Ida)" in rp.text
    assert "R1 · Oit (Ida)" in rp.text
    assert 'class="ficha-rodada-lab">Pts</span>' in rp.text
    assert 'class="ficha-rodada-lab">Total</span>' in rp.text
    assert 'class="ficha-rodada-lab">Col</span>' in rp.text


def test_perfil_nao_zera_ao_avancar_fase(client):
    """Perfil usa jogos de todas as fases — não some ao ir para Quartas."""
    login_admin(client)
    a = db.criar_participante("Perfil Fase", status="liberado")
    _cinfo, jogo = _jogo_oitavas()
    db.salvar_palpite_jogo(a["id"], jogo["id"], 2, 0)
    db.set_resultado_jogo(jogo["id"], 2, 0)

    hall_oit = trofeus_hall("oitavas")
    p_oit = hall_oit["perfis"][a["id"]]
    assert p_oit["n"] >= 1
    assert p_oit["acertos_placar"] >= 1

    db.set_fase_atual("quartas")
    hall_qua = trofeus_hall("quartas")
    p_qua = hall_qua["perfis"][a["id"]]
    assert p_qua["n"] == p_oit["n"]
    assert p_qua["acertos_placar"] == p_oit["acertos_placar"]
    assert p_qua["n_casa"] == p_oit["n_casa"]


def test_avancar_fase_nao_infla_pontos_nem_rod_fantasma(client):
    """Oitavas devem continuar com pesos de Oitavas após liberar Quartas."""
    from src.ranking import calcular_classificacao, confirmar_rodada, resumo_pontuacao_por_participante

    login_admin(client)
    a = db.criar_participante("Peso Fase", status="liberado")
    _cinfo, jogo = _jogo_oitavas()
    db.salvar_palpite_jogo(a["id"], jogo["id"], 2, 0)
    db.set_resultado_jogo(jogo["id"], 2, 0)

    antes = next(r for r in calcular_classificacao() if r["participante_id"] == a["id"])
    confirmar_rodada()
    db.set_fase_atual("quartas")
    db.set_janela("ida")
    depois = next(r for r in calcular_classificacao() if r["participante_id"] == a["id"])
    assert depois["soma"] == antes["soma"]
    assert depois["rod"] == 0

    resumo = resumo_pontuacao_por_participante()
    ao_vivo = resumo[a["id"]][-1]
    assert ao_vivo["ao_vivo"] is True
    assert ao_vivo["rotulo"] == "Rodada 2"
    assert ao_vivo["fase_label"] == "Quartas"
    assert ao_vivo["fase_label_curta"] == "Qua"
    assert ao_vivo["janela_label"] == "Ida"
    assert ao_vivo["rod"] == 0
    assert ao_vivo["jogos"] == []


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
