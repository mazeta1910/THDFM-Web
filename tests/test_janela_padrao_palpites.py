"""Janela padrão de Meus Palpites / perfil após fechar a Ida."""

import re
from urllib.parse import unquote

from src import db
from src.ranking import confirmar_rodada, desfazer_ultima_rodada, resumo_pontuacao_por_participante
from tests.conftest import login_admin


def _login_participante(client, part, username):
    db.definir_credenciais(part["id"], username, "senha12345")
    client.cookies.clear()
    r = client.get(f"/p/{part['token']}", follow_redirects=False)
    assert r.status_code in (200, 303)


def _jogo(confronto: dict, perna: str) -> dict:
    return next(j for j in confronto["jogos"] if j["perna"] == perna)


def _fechar_perna(fase: str, perna: str, *, gm: int = 1, gv: int = 0) -> None:
    for c in db.list_confrontos_completos(fase):
        db.set_resultado_jogo(_jogo(c, perna)["id"], gm, gv, None)


def _palpite_exato(pid: int, fase: str, perna: str, *, gm: int = 1, gv: int = 0) -> None:
    c0 = db.list_confrontos_completos(fase)[0]
    db.salvar_palpite_jogo(pid, _jogo(c0, perna)["id"], gm, gv)


def _montar_quartas(client) -> None:
    login_admin(client)
    _fechar_perna("oitavas", "ida", gm=1, gv=0)
    _fechar_perna("oitavas", "volta", gm=0, gv=0)
    clubs = [c["clube"] for c in db.classificados_da_fase("oitavas")]
    data = {"fase": "quartas"}
    for i in range(4):
        data[f"chave_{i}_a"] = clubs[i * 2]
        data[f"chave_{i}_b"] = clubs[i * 2 + 1]
    r = client.post("/admin/arvore/montar", data=data, follow_redirects=False)
    assert r.status_code == 303
    assert db.get_fase_atual() == "quartas"
    assert db.get_janela() == "ida"


def test_fechar_ida_avanca_janela_para_volta(client):
    login_admin(client)
    a = db.criar_participante("Fecha Ida", status="liberado")
    _palpite_exato(a["id"], "oitavas", "ida")
    _fechar_perna("oitavas", "ida")
    assert db.get_janela() == "ida"

    hist = confirmar_rodada()
    assert hist["janela"] == "ida"
    assert db.get_janela() == "volta"

    desfazer_ultima_rodada()
    assert db.get_janela() == "ida"


def test_fechamento_fantasma_nao_avanca_janela(client):
    login_admin(client)
    db.criar_participante("Fantasma", status="liberado")
    assert db.get_janela() == "ida"
    hist = confirmar_rodada()
    assert hist["janela"] == "ida"
    assert db.get_janela() == "ida"


def test_admin_define_card_padrao_meus_palpites(client):
    login_admin(client)
    r = client.post(
        "/admin/janela",
        data={"janela": "volta"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    loc = unquote((r.headers.get("location") or "").replace("+", " "))
    assert "sec=resultados" in loc
    assert "Meus Palpites abre em Volta" in loc
    assert db.get_janela() == "volta"

    bad = client.post(
        "/admin/janela",
        data={"janela": "invalida"},
        follow_redirects=False,
    )
    assert bad.status_code == 303
    assert "erro=" in (bad.headers.get("location") or "")
    assert db.get_janela() == "volta"


def test_quartas_ida_fechada_abre_volta_no_perfil_e_palpites(client):
    """R3 Quartas Ida fechada → R4 ao vivo é Quartas (Volta); Meus Palpites abre na Volta."""
    a = db.criar_participante("Quartas Volta", status="liberado")
    login_admin(client)

    _palpite_exato(a["id"], "oitavas", "ida")
    _fechar_perna("oitavas", "ida")
    confirmar_rodada()

    _palpite_exato(a["id"], "oitavas", "volta", gm=0, gv=0)
    _fechar_perna("oitavas", "volta", gm=0, gv=0)
    confirmar_rodada()

    _montar_quartas(client)
    assert db.get_janela() == "ida"

    _palpite_exato(a["id"], "quartas", "ida")
    _fechar_perna("quartas", "ida")
    hist = confirmar_rodada()
    assert hist["janela"] == "ida"
    assert db.get_janela() == "volta"
    assert db.get_fase_atual() == "quartas"

    resumo = resumo_pontuacao_por_participante()
    entradas = resumo[a["id"]]
    assert len(entradas) == 4
    assert entradas[0]["fase_label"] == "Oitavas" and entradas[0]["janela_label"] == "Ida"
    assert entradas[1]["fase_label"] == "Oitavas" and entradas[1]["janela_label"] == "Volta"
    assert entradas[2]["fase_label"] == "Quartas" and entradas[2]["janela_label"] == "Ida"
    assert entradas[2]["ao_vivo"] is False
    ao_vivo = entradas[3]
    assert ao_vivo["ao_vivo"] is True
    assert ao_vivo["rotulo_curto"] == "R4"
    assert ao_vivo["fase_label"] == "Quartas"
    assert ao_vivo["janela"] == "volta"
    assert ao_vivo["janela_label"] == "Volta"

    _login_participante(client, a, "quartasvolta1")
    rp = client.get("/meu-perfil")
    assert rp.status_code == 200
    assert "R3 · Quartas (Ida)" in rp.text
    assert "R4 · Quartas (Volta)" in rp.text
    assert "R4 · Quartas (Ida)" not in rp.text

    mp = client.get("/bolao/meus-palpites")
    assert mp.status_code == 200
    assert 'data-fase-col="quartas"' in mp.text
    body = " ".join(mp.text.split())
    assert 'data-tab="volta" class="active"' in body or 'data-tab="volta" class=" active"' in body
    assert 'data-panel="ida"' in mp.text and 'data-panel="volta"' in mp.text
    assert re.search(r'class="match-panel\s+hidden"\s*data-panel="ida"', mp.text)
    assert re.search(r'class="match-panel\s*"\s*data-panel="volta"', mp.text)
    assert "Ida encerrada — palpites só na Volta" in mp.text


def test_r4_ao_vivo_nao_pula_quartas_volta_se_fase_avancou(client):
    """Se admin avançar para Semis cedo, R4 ao vivo continua Quartas (Volta)."""
    a = db.criar_participante("R4 Quartas", status="liberado")
    login_admin(client)

    _palpite_exato(a["id"], "oitavas", "ida")
    _fechar_perna("oitavas", "ida")
    confirmar_rodada()

    _palpite_exato(a["id"], "oitavas", "volta", gm=0, gv=0)
    _fechar_perna("oitavas", "volta", gm=0, gv=0)
    confirmar_rodada()

    _montar_quartas(client)
    _palpite_exato(a["id"], "quartas", "ida")
    _fechar_perna("quartas", "ida")
    confirmar_rodada()
    assert db.get_janela() == "volta"
    assert db.get_fase_atual() == "quartas"

    # Avanço precoce: fase vira Semis/Ida, mas a próxima rodada lógica é Quartas Volta.
    db.set_fase_atual("semis")
    db.set_janela("ida")

    entradas = resumo_pontuacao_por_participante()[a["id"]]
    ao_vivo = entradas[-1]
    assert ao_vivo["ao_vivo"] is True
    assert ao_vivo["rotulo_curto"] == "R4"
    assert ao_vivo["fase"] == "quartas"
    assert ao_vivo["fase_label"] == "Quartas"
    assert ao_vivo["janela"] == "volta"
    assert ao_vivo["janela_label"] == "Volta"

    _login_participante(client, a, "r4quartas1")
    rp = client.get("/meu-perfil")
    assert rp.status_code == 200
    assert "R4 · Quartas (Volta)" in rp.text
    assert "R4 · Semis (Ida)" not in rp.text
