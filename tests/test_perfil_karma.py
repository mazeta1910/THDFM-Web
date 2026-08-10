"""Karma do perfil: votos no servidor e média agregada."""

from __future__ import annotations

from fastapi.testclient import TestClient

from src import db as dbmod
from tests.conftest import login_admin


def _login_part(client: TestClient, nome: str, username: str, celular: str) -> dict:
    part = dbmod.criar_participante(nome, status="liberado", celular=celular)
    dbmod.definir_credenciais(part["id"], username, "senha12345")
    client.get(f"/p/{part['token']}")
    return part


def test_karma_sem_votos_e_zero(client: TestClient):
    alvo = dbmod.criar_participante("Alvo Zero", status="liberado", celular="11990007001")
    resumo = dbmod.karma_resumo(alvo["id"])
    assert resumo["medias"] == {
        "confiavel": 0,
        "legal": 0,
        "sexy": 0,
        "burro": 0,
    }
    assert resumo["counts"] == {
        "confiavel": 0,
        "legal": 0,
        "sexy": 0,
        "burro": 0,
    }
    assert resumo["pode_votar"] is False


def test_karma_agrega_e_substitui_voto(client: TestClient):
    alvo = dbmod.criar_participante("Alvo Karma", status="liberado", celular="11990007002")
    a = dbmod.criar_participante("Votante A", status="liberado", celular="11990007003")
    b = dbmod.criar_participante("Votante B", status="liberado", celular="11990007004")

    dbmod.salvar_karma_voto(a["id"], alvo["id"], "legal", 1)
    dbmod.salvar_karma_voto(b["id"], alvo["id"], "legal", 3)
    resumo = dbmod.karma_resumo(alvo["id"], voter_id=a["id"])
    assert resumo["medias"]["legal"] == 2  # (1+3)/2
    assert resumo["counts"]["legal"] == 2
    assert resumo["meu_voto"]["legal"] == 1

    dbmod.salvar_karma_voto(a["id"], alvo["id"], "legal", 3)
    resumo = dbmod.karma_resumo(alvo["id"], voter_id=a["id"])
    assert resumo["medias"]["legal"] == 3  # (3+3)/2
    assert resumo["counts"]["legal"] == 2
    assert resumo["meu_voto"]["legal"] == 3


def test_karma_nao_vota_em_si(client: TestClient):
    part = dbmod.criar_participante("Self Karma", status="liberado", celular="11990007005")
    try:
        dbmod.salvar_karma_voto(part["id"], part["id"], "sexy", 2)
        assert False, "deveria falhar"
    except ValueError:
        pass


def test_api_karma_voto_e_perfil(client: TestClient):
    alvo = _login_part(client, "Perfil Alvo", "perfil.alvo", "11990007006")
    # troca sessão para o votante
    client.cookies.clear()
    votante = _login_part(client, "Perfil Voto", "perfil.voto", "11990007007")

    r = client.get(f"/perfil/{alvo['id']}/karma")
    assert r.status_code == 200
    data = r.json()
    assert data["medias"]["confiavel"] == 0
    assert data["pode_votar"] is True
    assert data["meu_voto"] == {}

    r = client.put(
        f"/perfil/{alvo['id']}/karma",
        json={"categoria": "confiavel", "nivel": 2},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["medias"]["confiavel"] == 2
    assert data["counts"]["confiavel"] == 1
    assert data["meu_voto"]["confiavel"] == 2

    r = client.get(f"/perfil/{alvo['id']}")
    assert r.status_code == 200
    assert 'data-pode-votar="1"' in r.text
    assert 'data-target-id="' + str(alvo["id"]) + '"' in r.text
    assert '"confiavel": 2' in r.text or '"confiavel":2' in r.text
    assert "data-karma-cycle" in r.text
    assert "/static/prototipo-perfil.js?v=28" in r.text

    # próprio perfil: não vota
    r = client.put(
        f"/perfil/{votante['id']}/karma",
        json={"categoria": "legal", "nivel": 1},
        follow_redirects=False,
    )
    # /perfil/{self} redireciona na página HTML; API PUT no próprio id deve 403
    # (PUT não passa pelo redirect do GET)
    assert r.status_code == 403


def test_meu_perfil_mostra_media_agregada(client: TestClient):
    login_admin(client)
    from src import db as dbmod

    dono = dbmod.get_participante_por_admin_login("mazeta")
    assert dono
    votante = dbmod.criar_participante("Vota Mazeta", status="liberado", celular="11990007008")
    dbmod.salvar_karma_voto(votante["id"], dono["id"], "burro", 3)
    dbmod.salvar_karma_voto(votante["id"], dono["id"], "sexy", 1)

    r = client.get("/meu-perfil")
    assert r.status_code == 200
    assert 'data-pode-votar="0"' in r.text
    assert "data-karma-cycle" not in r.text
    assert '"burro": 3' in r.text or '"burro":3' in r.text
    assert '"sexy": 1' in r.text or '"sexy":1' in r.text
    # sem default fake 2/3/1/1 quando não há votos nas outras
    assert '"confiavel": 0' in r.text or '"confiavel":0' in r.text
