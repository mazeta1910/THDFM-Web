"""Admin Resultados: layout, salvar por perna, confirmar/desfazer jogo."""

from src import db
from tests.conftest import login_admin


def _primeiro_confronto_oitavas():
    confrontos = db.list_confrontos_completos("oitavas")
    assert confrontos
    c = confrontos[0]
    ida = next(j for j in c["jogos"] if j["perna"] == "ida")
    volta = next(j for j in c["jogos"] if j["perna"] == "volta")
    return c, ida, volta


def test_admin_resultados_sem_janela_fase_cards(client):
    login_admin(client)
    r = client.get("/admin?sec=resultados")
    assert r.status_code == 200
    assert "Placares oficiais" in r.text
    assert "Janela de palpites" not in r.text
    assert "Fase liberada" not in r.text
    assert "Atualizar janela" not in r.text
    assert "match-cell" in r.text
    assert "admin-sticky-save" in r.text
    assert 'data-confirmar-jogo' in r.text or "Confirmado" in r.text


def test_perna_default_volta_quando_ida_completa(client):
    login_admin(client)
    confrontos = db.list_confrontos_completos("oitavas")
    for c in confrontos:
        ida = next(j for j in c["jogos"] if j["perna"] == "ida")
        db.set_resultado_jogo(ida["id"], 1, 0, None)
    r = client.get("/admin?sec=resultados")
    assert r.status_code == 200
    # Painel Volta da fase ativa visível; Ida oculto
    assert 'data-panel="volta"' in r.text
    assert 'class="match-panel hidden" data-panel="ida"' in r.text or (
        'data-panel="ida"' in r.text and 'match-panel hidden' in r.text
    )
    # Botão Volta marcado como ativo na fase ativa
    assert 'aria-current="true"' in r.text
    assert "perna_default" not in r.text  # só no JS template se vazasse; sanity
    body = " ".join(r.text.split())
    assert 'data-tab="volta" class="active"' in body or 'data-tab="volta" class=" active"' in body


def test_salvar_apenas_perna_visivel(client):
    login_admin(client)
    _, ida, volta = _primeiro_confronto_oitavas()
    r = client.post(
        "/admin/resultados",
        data={
            "fase": "oitavas",
            "perna": "ida",
            f"jogo_{ida['id']}_m": "2",
            f"jogo_{ida['id']}_v": "1",
            f"jogo_{volta['id']}_m": "9",
            f"jogo_{volta['id']}_v": "9",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "erro" not in (r.headers.get("location") or "")
    ida2 = db.get_jogo(ida["id"])
    volta2 = db.get_jogo(volta["id"])
    assert ida2["gols_mandante"] == 2
    assert ida2["gols_visitante"] == 1
    assert volta2["gols_mandante"] is None
    assert volta2["gols_visitante"] is None


def test_confirmar_e_desfazer_jogo(client):
    login_admin(client)
    _, ida, _ = _primeiro_confronto_oitavas()
    db.set_resultado_jogo(ida["id"], 1, 0, None)
    r = client.post(f"/admin/jogo/{ida['id']}/confirmar?format=json")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    jogo = db.get_jogo(ida["id"])
    assert db.jogo_confirmado(jogo)

    # Bloqueia alteração
    bad = client.post(
        "/admin/resultados?format=json",
        data={
            "fase": "oitavas",
            "perna": "ida",
            f"jogo_{ida['id']}_m": "5",
            f"jogo_{ida['id']}_v": "5",
        },
    )
    assert bad.status_code == 400 or (bad.status_code == 200 and bad.json().get("ok") is False) or (
        bad.status_code == 200 and bad.json().get("salvos", 1) == 0
    )
    jogo = db.get_jogo(ida["id"])
    assert jogo["gols_mandante"] == 1

    undo = client.post(f"/admin/jogo/{ida['id']}/desfazer-confirmacao?format=json")
    assert undo.status_code == 200
    assert undo.json()["ok"] is True
    assert not db.jogo_confirmado(db.get_jogo(ida["id"]))

    ok = client.post(
        "/admin/resultados?format=json",
        data={
            "fase": "oitavas",
            "perna": "ida",
            f"jogo_{ida['id']}_m": "3",
            f"jogo_{ida['id']}_v": "0",
        },
    )
    assert ok.status_code == 200
    assert ok.json()["ok"] is True
    assert db.get_jogo(ida["id"])["gols_mandante"] == 3


def test_montar_quartas_libera_fase(client):
    login_admin(client)
    confrontos = db.list_confrontos_completos("oitavas")
    for c in confrontos:
        ida = next(j for j in c["jogos"] if j["perna"] == "ida")
        volta = next(j for j in c["jogos"] if j["perna"] == "volta")
        db.set_resultado_jogo(ida["id"], 1, 0, None)
        db.set_resultado_jogo(volta["id"], 0, 0, None)
    classificados = db.classificados_da_fase("oitavas")
    clubs = [c["clube"] for c in classificados]
    data = {"fase": "quartas"}
    for i in range(4):
        data[f"chave_{i}_a"] = clubs[i * 2]
        data[f"chave_{i}_b"] = clubs[i * 2 + 1]
    r = client.post("/admin/arvore/montar", data=data, follow_redirects=False)
    assert r.status_code == 303
    assert db.get_fase_atual() == "quartas"


def test_palpites_usa_partial_match_cell(client):
    part = db.criar_participante("Partial User", status="liberado")
    db.definir_credenciais(part["id"], "partialuser", "senha12345")
    client.get(f"/p/{part['token']}")
    r = client.get("/bolao/meus-palpites")
    assert r.status_code == 200
    assert "match-cell" in r.text
    assert "JOGO (" in r.text
    assert 'aria-label="Gols' in r.text
