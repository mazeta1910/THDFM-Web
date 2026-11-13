"""Final = jogo único; semis/quartas/oitavas = ida+volta."""

from __future__ import annotations

import src.db as db
from src.config import FASES_JOGO_UNICO, fase_formato
from src.scoring import quem_classifica_jogo_unico
from tests.conftest import login_admin


def _classificar_fase(fase: str) -> list[str]:
    confrontos = db.list_confrontos_completos(fase)
    for c in confrontos:
        ida = next(j for j in c["jogos"] if j["perna"] == "ida")
        volta = next(j for j in c["jogos"] if j["perna"] == "volta")
        db.set_resultado_jogo(ida["id"], 1, 0, None)
        db.set_resultado_jogo(volta["id"], 0, 0, None)
    return [c["clube"] for c in db.classificados_da_fase(fase)]


def _montar_ate_semis(client) -> list[str]:
    login_admin(client)
    clubs_o = _classificar_fase("oitavas")
    data_q = {"fase": "quartas"}
    for i in range(4):
        data_q[f"chave_{i}_a"] = clubs_o[i * 2]
        data_q[f"chave_{i}_b"] = clubs_o[i * 2 + 1]
    r = client.post("/admin/arvore/montar", data=data_q, follow_redirects=False)
    assert r.status_code == 303
    clubs_q = _classificar_fase("quartas")
    data_s = {"fase": "semis"}
    for i in range(2):
        data_s[f"chave_{i}_a"] = clubs_q[i * 2]
        data_s[f"chave_{i}_b"] = clubs_q[i * 2 + 1]
    r = client.post("/admin/arvore/montar", data=data_s, follow_redirects=False)
    assert r.status_code == 303
    return clubs_q


def test_fase_formato_so_final_unico():
    assert FASES_JOGO_UNICO == frozenset({"final"})
    assert fase_formato("final") == "unico"
    assert fase_formato("semis") == "ida_volta"
    assert fase_formato("quartas") == "ida_volta"
    assert fase_formato("oitavas") == "ida_volta"


def test_quem_classifica_jogo_unico():
    assert quem_classifica_jogo_unico(2, 1) == "a"
    assert quem_classifica_jogo_unico(0, 3) == "b"
    assert quem_classifica_jogo_unico(1, 1) is None
    assert quem_classifica_jogo_unico(1, 1, penaltis_clube_id="b") == "b"


def test_criar_confronto_final_so_unico(client):
    cid = db.criar_confronto("final", "Flamengo", "Palmeiras", unico_em="2026-11-20 21:00")
    c = next(x for x in db.list_confrontos_completos("final") if x["id"] == cid)
    pernas = sorted(j["perna"] for j in c["jogos"])
    assert pernas == ["unico"]
    assert c["jogos"][0]["inicio_em"] == "2026-11-20 21:00"


def test_criar_confronto_semis_ida_volta(client):
    cid = db.criar_confronto("semis", "Flamengo", "Palmeiras")
    c = next(x for x in db.list_confrontos_completos("semis") if x["id"] == cid)
    pernas = sorted(j["perna"] for j in c["jogos"])
    assert pernas == ["ida", "volta"]


def test_montar_final_jogo_unico(client):
    clubs_q = _montar_ate_semis(client)
    clubs_s = _classificar_fase("semis")
    assert len(clubs_s) == 2
    data = {
        "fase": "final",
        "chave_0_a": clubs_s[0],
        "chave_0_b": clubs_s[1],
        "chave_0_unico": "2026-12-01T21:00",
    }
    r = client.post("/admin/arvore/montar", data=data, follow_redirects=False)
    assert r.status_code == 303
    loc = r.headers.get("location") or ""
    assert "erro" not in loc
    finais = db.list_confrontos_completos("final")
    assert len(finais) == 1
    pernas = sorted(j["perna"] for j in finais[0]["jogos"])
    assert pernas == ["unico"]
    # Semis continuam ida/volta
    semis = db.list_confrontos_completos("semis")
    assert len(semis) == 2
    for c in semis:
        assert sorted(j["perna"] for j in c["jogos"]) == ["ida", "volta"]
    assert clubs_q  # usado na montagem


def test_admin_final_sem_abas_ida_volta(client):
    _montar_ate_semis(client)
    clubs_s = _classificar_fase("semis")
    client.post(
        "/admin/arvore/montar",
        data={
            "fase": "final",
            "chave_0_a": clubs_s[0],
            "chave_0_b": clubs_s[1],
            "chave_0_unico": "2026-12-01T21:00",
        },
        follow_redirects=False,
    )
    db.set_fase_atual("final")
    db.set_janela("ida")
    r = client.get("/admin")
    assert r.status_code == 200
    # Nav da Final: jogo único em coluna cheia; Semis ainda mostram Ida/Volta
    assert 'data-tab="unico"' in r.text
    assert "transparencia-nav-pernas is-unico" in r.text
    assert "Jogo único" in r.text or 'nav-perna-short">Jogo</span>' in r.text
    assert 'data-fase="semis"' in r.text
    assert 'data-tab="ida"' in r.text
    assert 'data-tab="volta"' in r.text
    assert 'data-dash-perna="unico"' in r.text
    assert "(jogo único)" in r.text


def test_palpite_e_classificado_final_unico(client):
    _montar_ate_semis(client)
    clubs_s = _classificar_fase("semis")
    client.post(
        "/admin/arvore/montar",
        data={
            "fase": "final",
            "chave_0_a": clubs_s[0],
            "chave_0_b": clubs_s[1],
        },
        follow_redirects=False,
    )
    db.set_fase_atual("final")
    db.set_janela("ida")
    finais = db.list_confrontos_completos("final")
    unico = next(j for j in finais[0]["jogos"] if j["perna"] == "unico")
    part = db.criar_participante("Finalista", status="liberado")
    db.definir_credenciais(part["id"], "finalista.user", "senha12345")
    db.salvar_palpite_jogo(part["id"], unico["id"], 2, 2)
    db.salvar_palpite_penaltis(part["id"], finais[0]["id"], "a")
    palp = db.palpites_do_participante(part["id"])
    assert palp["jogos"][unico["id"]]["gols_mandante"] == 2
    assert palp["jogos"][unico["id"]]["gols_visitante"] == 2
    assert palp["penaltis"][finais[0]["id"]]["penaltis_clube_id"] == "a"

    # Meus Palpites na Final: painel único, sem Ida/Volta
    r = client.get(f"/p/{part['token']}")
    assert r.status_code == 200
    assert 'data-panel="unico"' in r.text
    assert 'name="unico_' in r.text
    assert 'data-tab="unico"' in r.text

    db.set_resultado_jogo(unico["id"], 1, 1, "b")
    classif = db.classificados_da_fase("final")
    assert len(classif) == 1
    assert classif[0]["clube"] == clubs_s[1]


def test_transparencia_final_perna_unico(client):
    _montar_ate_semis(client)
    clubs_s = _classificar_fase("semis")
    client.post(
        "/admin/arvore/montar",
        data={
            "fase": "final",
            "chave_0_a": clubs_s[0],
            "chave_0_b": clubs_s[1],
        },
        follow_redirects=False,
    )
    db.set_fase_atual("final")
    finais = db.list_confrontos_completos("final")
    unico = next(j for j in finais[0]["jogos"] if j["perna"] == "unico")
    db.set_resultado_jogo(unico["id"], 2, 0, None)
    r = client.get("/transparencia?fase=final&perna=unico")
    assert r.status_code == 200
    assert "transparencia-nav-pernas is-unico" in r.text
    assert "Jogo único" in r.text or 'perna=unico"' in r.text
    r2 = client.get("/transparencia?fase=final&perna=ida")
    assert r2.status_code == 200
    assert "Jogo único" in r2.text or 'perna=unico"' in r2.text
