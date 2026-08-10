"""Recados do perfil: mural por participante no servidor."""

from __future__ import annotations

from fastapi.testclient import TestClient

from src import db as dbmod
from tests.conftest import login_admin


def _login_part(client: TestClient, nome: str, username: str, celular: str) -> dict:
    part = dbmod.criar_participante(nome, status="liberado", celular=celular)
    dbmod.definir_credenciais(part["id"], username, "senha12345")
    client.get(f"/p/{part['token']}")
    return part


def test_recados_ficam_no_perfil_alvo(client: TestClient):
    lucas = dbmod.criar_participante("Lucas Doido", status="liberado", celular="11990009101")
    outro = dbmod.criar_participante("Outro Perfil", status="liberado", celular="11990009102")
    autor = dbmod.criar_participante("Mazeta Recado", status="liberado", celular="11990009103")

    dbmod.criar_recado(lucas["id"], autor["id"], "só no Lucas")
    assert len(dbmod.listar_recados(lucas["id"])) == 1
    assert dbmod.listar_recados(lucas["id"])[0]["texto"] == "só no Lucas"
    assert dbmod.listar_recados(outro["id"]) == []


def test_api_recados_por_perfil(client: TestClient):
    alvo = _login_part(client, "Alvo Recado", "alvo.recado", "11990009104")
    client.cookies.clear()
    votante = _login_part(client, "Autor Recado", "autor.recado", "11990009105")

    r = client.get(f"/perfil/{alvo['id']}/recados")
    assert r.status_code == 200
    assert r.json()["recados"] == []

    r = client.post(f"/perfil/{alvo['id']}/recados", json={"texto": "e aí xonha"})
    assert r.status_code == 200
    data = r.json()
    assert len(data["recados"]) == 1
    assert data["recados"][0]["texto"] == "e aí xonha"
    assert data["recados"][0]["autor_id"] == votante["id"]
    assert data["recados"][0]["target_id"] == alvo["id"]

    # outro perfil continua vazio
    outro = dbmod.criar_participante("Perfil Limpo", status="liberado", celular="11990009106")
    r = client.get(f"/perfil/{outro['id']}/recados")
    assert r.status_code == 200
    assert r.json()["recados"] == []

    # página do alvo embute só os dele
    r = client.get(f"/perfil/{alvo['id']}")
    assert r.status_code == 200
    assert 'id="proto-recados"' in r.text
    assert "e aí xonha" in r.text
    assert "/static/prototipo-perfil.js?v=28" in r.text

    # não posta no próprio
    r = client.post(f"/perfil/{votante['id']}/recados", json={"texto": "auto"})
    assert r.status_code == 403


def test_apagar_recado_dono_do_mural(client: TestClient):
    login_admin(client)
    dono = dbmod.get_participante_por_admin_login("mazeta")
    assert dono
    autor = dbmod.criar_participante("Apaga Autor", status="liberado", celular="11990009107")
    criado = dbmod.criar_recado(dono["id"], autor["id"], "vai sumir")
    rid = int(criado["id"])

    r = client.delete(f"/perfil/{dono['id']}/recados/{rid}")
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert dbmod.listar_recados(dono["id"]) == []


def test_meu_perfil_embute_recados(client: TestClient):
    login_admin(client)
    dono = dbmod.get_participante_por_admin_login("mazeta")
    assert dono
    autor = dbmod.criar_participante("Visit Recado", status="liberado", celular="11990009108")
    dbmod.criar_recado(dono["id"], autor["id"], "no meu mural")

    r = client.get("/meu-perfil")
    assert r.status_code == 200
    assert 'id="proto-recados"' in r.text
    assert "no meu mural" in r.text


def test_notificacao_recados_envelope(client: TestClient):
    login_admin(client)
    dono = dbmod.get_participante_por_admin_login("mazeta")
    assert dono
    autor = dbmod.criar_participante("Notif Autor", status="liberado", celular="11990009109")

    r = client.get("/classificacao")
    assert r.status_code == 200
    assert 'id="recados-toggle"' not in r.text

    dbmod.criar_recado(dono["id"], autor["id"], "novo aviso")
    assert dbmod.contar_recados_novos(dono["id"]) == 1

    r = client.get("/classificacao")
    assert r.status_code == 200
    assert 'id="recados-toggle"' in r.text
    assert 'href="/meu-perfil#recados"' in r.text
    assert "recados-toggle-badge" in r.text
    assert ">1<" in r.text or "1 recado" in r.text

    # abrir o próprio perfil limpa a notificação
    r = client.get("/meu-perfil")
    assert r.status_code == 200
    assert dbmod.contar_recados_novos(dono["id"]) == 0
    r = client.get("/classificacao")
    assert 'id="recados-toggle"' not in r.text
