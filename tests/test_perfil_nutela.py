"""Nutela↔raíz do perfil: votos no servidor e média agregada."""

from __future__ import annotations

from fastapi.testclient import TestClient

from src import db as dbmod
from tests.conftest import login_admin


def _login_part(client: TestClient, nome: str, username: str, celular: str) -> dict:
    part = dbmod.criar_participante(nome, status="liberado", celular=celular)
    dbmod.definir_credenciais(part["id"], username, "senha12345")
    client.get(f"/p/{part['token']}")
    return part


def test_nutela_sem_votos_e_cinquenta(client: TestClient):
    alvo = dbmod.criar_participante("Alvo Nutela Zero", status="liberado", celular="11990008001")
    resumo = dbmod.nutela_resumo(alvo["id"])
    assert resumo["media"] == 50
    assert resumo["count"] == 0
    assert resumo["pode_votar"] is False
    assert resumo["meu_voto"] is None


def test_nutela_agrega_e_substitui_voto(client: TestClient):
    alvo = dbmod.criar_participante("Alvo Nutela", status="liberado", celular="11990008002")
    a = dbmod.criar_participante("Votante Nut A", status="liberado", celular="11990008003")
    b = dbmod.criar_participante("Votante Nut B", status="liberado", celular="11990008004")

    dbmod.salvar_nutela_voto(a["id"], alvo["id"], 20)
    dbmod.salvar_nutela_voto(b["id"], alvo["id"], 80)
    resumo = dbmod.nutela_resumo(alvo["id"], voter_id=a["id"])
    assert resumo["media"] == 50  # (20+80)/2
    assert resumo["count"] == 2
    assert resumo["meu_voto"] == 20

    dbmod.salvar_nutela_voto(a["id"], alvo["id"], 100)
    resumo = dbmod.nutela_resumo(alvo["id"], voter_id=a["id"])
    assert resumo["media"] == 90  # (100+80)/2
    assert resumo["count"] == 2
    assert resumo["meu_voto"] == 100


def test_nutela_nao_vota_em_si(client: TestClient):
    part = dbmod.criar_participante("Self Nutela", status="liberado", celular="11990008005")
    try:
        dbmod.salvar_nutela_voto(part["id"], part["id"], 40)
        assert False, "deveria falhar"
    except ValueError:
        pass


def test_api_nutela_voto_e_perfil(client: TestClient):
    alvo = _login_part(client, "Perfil Nutela Alvo", "perfil.nutela.alvo", "11990008006")
    client.cookies.clear()
    votante = _login_part(client, "Perfil Nutela Voto", "perfil.nutela.voto", "11990008007")

    r = client.get(f"/perfil/{alvo['id']}/nutela")
    assert r.status_code == 200
    data = r.json()
    assert data["media"] == 50
    assert data["count"] == 0
    assert data["pode_votar"] is True
    assert data["meu_voto"] is None

    r = client.put(f"/perfil/{alvo['id']}/nutela", json={"valor": 75})
    assert r.status_code == 200
    data = r.json()
    assert data["media"] == 75
    assert data["count"] == 1
    assert data["meu_voto"] == 75

    r = client.get(f"/perfil/{alvo['id']}")
    assert r.status_code == 200
    assert 'data-pode-votar="1"' in r.text
    assert 'id="proto-nutela-resumo"' in r.text
    assert '"media": 75' in r.text or '"media":75' in r.text
    assert "data-proto-nutela" in r.text
    assert ">nutella</span>" in r.text
    assert "medidor nutella" in r.text
    assert "/static/prototipo-perfil.js?v=31" in r.text

    r = client.put(
        f"/perfil/{votante['id']}/nutela",
        json={"valor": 10},
        follow_redirects=False,
    )
    assert r.status_code == 403
    assert r.json()["erro"] == "Não pode votar no próprio nutella"


def test_meu_perfil_mostra_media_nutela(client: TestClient):
    login_admin(client)
    dono = dbmod.get_participante_por_admin_login("mazeta")
    assert dono
    votante = dbmod.criar_participante("Vota Nutela Mazeta", status="liberado", celular="11990008008")
    dbmod.salvar_nutela_voto(votante["id"], dono["id"], 10)

    r = client.get("/meu-perfil")
    assert r.status_code == 200
    assert 'data-pode-votar="0"' in r.text
    assert "data-proto-nutela" not in r.text
    assert 'id="proto-nutela-resumo"' in r.text
    assert ">nutella</span>" in r.text
    assert '"media": 10' in r.text or '"media":10' in r.text
    assert '"count": 1' in r.text or '"count":1' in r.text
