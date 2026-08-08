"""Meus Palpites: fases encerradas e avatar no cumprimento."""

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
