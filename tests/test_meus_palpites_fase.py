"""Meus Palpites: fases encerradas, avatar e Volta liberada na Ida."""

from src import db
from tests.conftest import login_admin


def _login_participante(client, nome="Palpiteiro", username="palpiteiro1"):
    part = db.criar_participante(nome, status="liberado")
    db.definir_credenciais(part["id"], username, "senha12345")
    # Limpa sessão admin se houver e entra pelo link mágico
    client.cookies.clear()
    r = client.get(f"/p/{part['token']}", follow_redirects=False)
    assert r.status_code in (200, 303)
    if r.status_code == 303:
        assert "/credenciais" not in (r.headers.get("location") or "")
    return part


def test_meus_palpites_mostra_avatar_no_ola(client):
    part = _login_participante(client, "Mazeta Avatar", "mazetaavatar1")
    r = client.get("/bolao/meus-palpites")
    assert r.status_code == 200
    assert "palpites-hello-row" in r.text
    assert "palpites-hello-avatar" in r.text
    assert "Olá, Mazeta Avatar!" in r.text


def test_ida_oitavas_bloqueada_apos_avancar_fase(client):
    login_admin(client)
    confrontos = db.list_confrontos_completos("oitavas")
    for c in confrontos:
        ida = next(j for j in c["jogos"] if j["perna"] == "ida")
        volta = next(j for j in c["jogos"] if j["perna"] == "volta")
        db.set_resultado_jogo(ida["id"], 1, 0, None)
        db.set_resultado_jogo(volta["id"], 0, 0, None)
    client.post("/admin/avancar-fase")
    assert db.get_fase_atual() == "quartas"

    part = _login_participante(client, "User Fase", "userfase1")
    r = client.get("/bolao/meus-palpites")
    assert r.status_code == 200
    assert "fechada" in r.text
    assert "Fase encerrada" in r.text
    assert 'data-fase="oitavas"' in r.text
    assert 'data-fase-col="quartas"' in r.text
    assert "is-encerrada" in r.text


def test_volta_liberada_quando_janela_ida(client):
    """Com janela Ida, a aba Volta fica disponível (confrontos já definidos)."""
    db.set_janela("ida")
    db.set_fase_atual("oitavas")
    for c in db.list_confrontos_completos("oitavas"):
        for j in c["jogos"]:
            db.set_inicio_jogo(j["id"], "2099-08-10 20:00")

    part = _login_participante(client, "Volta Ida", "voltaida1")
    r = client.get("/bolao/meus-palpites")
    assert r.status_code == 200
    assert "Volta ainda não liberada" not in r.text
    assert f'name="volta_{db.list_confrontos_completos("oitavas")[0]["id"]}_m"' in r.text
    assert "/static/palpites.js" in r.text

    # Transparência / cobrança também liberam a aba Volta
    login_admin(client)
    tr = client.get("/transparencia?fase=oitavas&perna=volta", follow_redirects=False)
    assert tr.status_code == 200
    cob = client.get("/admin/cobranca?fase=oitavas&perna=volta", follow_redirects=False)
    assert cob.status_code == 200


def test_salvar_volta_com_janela_ida(client):
    db.set_janela("ida")
    db.set_fase_atual("oitavas")
    confrontos = db.list_confrontos_completos("oitavas")
    c = confrontos[0]
    ida = next(j for j in c["jogos"] if j["perna"] == "ida")
    volta = next(j for j in c["jogos"] if j["perna"] == "volta")
    db.set_inicio_jogo(ida["id"], "2099-08-10 20:00")
    db.set_inicio_jogo(volta["id"], "2099-08-17 20:00")

    part = _login_participante(client, "Salva Volta", "salvavolta1")
    r = client.post(
        f"/p/{part['token']}/salvar",
        data={
            f"ida_{c['id']}_m": "2",
            f"ida_{c['id']}_v": "1",
            f"volta_{c['id']}_m": "0",
            f"volta_{c['id']}_v": "3",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "erro" not in (r.headers.get("location") or "")
    palp = db.palpites_do_participante(part["id"])["jogos"]
    assert palp[ida["id"]]["gols_mandante"] == 2
    assert palp[ida["id"]]["gols_visitante"] == 1
    assert palp[volta["id"]]["gols_mandante"] == 0
    assert palp[volta["id"]]["gols_visitante"] == 3
