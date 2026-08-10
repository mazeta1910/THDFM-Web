"""Recados do perfil: mural por participante no servidor."""

from __future__ import annotations

from fastapi.testclient import TestClient

from src import db as dbmod
from src.config import ROOT_DIR
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
    assert r.json()["total"] == 0
    assert r.json()["pagina"] == 1
    assert r.json()["por_pagina"] == 5
    assert r.json()["paginas"] == 1

    r = client.post(f"/perfil/{alvo['id']}/recados", json={"texto": "e aí xonha"})
    assert r.status_code == 200
    data = r.json()
    assert len(data["recados"]) == 1
    assert data["total"] == 1
    assert data["pagina"] == 1
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
    assert "/static/prototipo-perfil.js?v=33" in r.text

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


def test_recado_com_imagem_e_gif(client: TestClient, tmp_path, monkeypatch):
    from src import app as app_mod

    midia_dir = tmp_path / "recados"
    midia_dir.mkdir()
    monkeypatch.setattr(app_mod, "RECADOS_DIR", midia_dir)
    monkeypatch.setattr("src.config.RECADOS_DIR", midia_dir)

    alvo = dbmod.criar_participante("Alvo Midia", status="liberado", celular="11990009120")
    _login_part(client, "Autor Midia", "autor.midia", "11990009121")

    # só imagem
    r = client.post(
        f"/perfil/{alvo['id']}/recados",
        data={"texto": ""},
        files={"midia": ("meme.gif", b"GIF89a-fake", "image/gif")},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["recado"]["texto"] == ""
    assert data["recado"]["midia"].startswith("/recados-midia/")
    assert data["recados"][0]["midia"].startswith("/recados-midia/")
    rel = data["recado"]["midia"].rsplit("/", 1)[-1]
    assert (midia_dir / rel).is_file()

    # texto + png
    r = client.post(
        f"/perfil/{alvo['id']}/recados",
        data={"texto": "olha o print"},
        files={"midia": ("print.png", b"\x89PNG\r\n\x1a\n-fake", "image/png")},
    )
    assert r.status_code == 200
    assert r.json()["recado"]["texto"] == "olha o print"
    assert r.json()["recado"]["midia"].startswith("/recados-midia/")

    # extensão inválida
    r = client.post(
        f"/perfil/{alvo['id']}/recados",
        data={"texto": "x"},
        files={"midia": ("doc.pdf", b"%PDF", "application/pdf")},
    )
    assert r.status_code == 400

    r = client.get(f"/perfil/{alvo['id']}")
    assert r.status_code == 200
    assert "/recados-midia/" in r.text
    assert "data-recado-midia" in r.text
    assert "/static/prototipo-perfil.js?v=33" in r.text
    js = (ROOT_DIR / "static" / "prototipo-perfil.js").read_text(encoding="utf-8")
    assert "proto-steam-feed-midia" in js
    assert "FormData" in js


def test_reacoes_toggle_e_agregam(client: TestClient):
    alvo = dbmod.criar_participante("Alvo Reacao", status="liberado", celular="11990009110")
    a = _login_part(client, "Reage A", "reage.a", "11990009111")
    recado = dbmod.criar_recado(alvo["id"], a["id"], "reage aí")
    rid = int(recado["id"])

    r = client.put(
        f"/perfil/{alvo['id']}/recados/{rid}/reacoes",
        json={"emoji": "👍"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["recado_id"] == str(rid)
    assert data["reacoes"][0]["emoji"] == "👍"
    assert data["reacoes"][0]["count"] == 1
    assert data["reacoes"][0]["mine"] is True
    assert data["reacoes"][0]["autores"] == [{"id": a["id"], "nome": "Reage A"}]
    assert data["recados"][0]["reacoes"][0]["autores"][0]["nome"] == "Reage A"

    client.cookies.clear()
    b = _login_part(client, "Reage B", "reage.b", "11990009112")
    r = client.put(
        f"/perfil/{alvo['id']}/recados/{rid}/reacoes",
        json={"emoji": "👍"},
    )
    assert r.status_code == 200
    reacs = r.json()["reacoes"]
    assert reacs[0]["count"] == 2
    assert reacs[0]["mine"] is True
    nomes = {x["nome"] for x in reacs[0]["autores"]}
    assert nomes == {"Reage A", "Reage B"}
    assert {x["id"] for x in reacs[0]["autores"]} == {a["id"], b["id"]}

    # toggle remove o próprio voto
    r = client.put(
        f"/perfil/{alvo['id']}/recados/{rid}/reacoes",
        json={"emoji": "👍"},
    )
    assert r.status_code == 200
    reacs = r.json()["reacoes"]
    assert reacs[0]["count"] == 1
    assert reacs[0]["mine"] is False
    assert reacs[0]["autores"] == [{"id": a["id"], "nome": "Reage A"}]

    r = client.put(
        f"/perfil/{alvo['id']}/recados/{rid}/reacoes",
        json={"emoji": "🔥"},
    )
    assert r.status_code == 200
    emojis = {x["emoji"]: x for x in r.json()["reacoes"]}
    assert emojis["👍"]["count"] == 1
    assert emojis["🔥"]["count"] == 1
    assert emojis["🔥"]["mine"] is True
    assert emojis["🔥"]["autores"][0]["nome"] == "Reage B"

    r = client.put(
        f"/perfil/{alvo['id']}/recados/{rid}/reacoes",
        json={"emoji": "💩"},
    )
    assert r.status_code == 400

    r = client.get(f"/perfil/{alvo['id']}")
    assert r.status_code == 200
    js = (ROOT_DIR / "static" / "prototipo-perfil.js").read_text(encoding="utf-8")
    css = (ROOT_DIR / "static" / "style.css").read_text(encoding="utf-8")
    assert "proto-steam-reacao-wrap" in js
    assert "proto-steam-reacao-tip" in js
    assert "button.proto-steam-reacao" in css
    assert "width: auto" in css
    assert "data-reacao-add" in js
    assert "/static/prototipo-perfil.js?v=33" in r.text
    assert "👍" in r.text
    assert "Reage A" in r.text


def test_responder_recado_dono_e_visitante(client: TestClient):
    """Dono do mural e visitantes podem responder; só 1 nível de thread."""
    alvo = _login_part(client, "Alvo Thread", "alvo.thread", "11990009130")
    client.cookies.clear()
    autor = _login_part(client, "Autor Thread", "autor.thread", "11990009131")

    r = client.post(f"/perfil/{alvo['id']}/recados", json={"texto": "e aí chefia"})
    assert r.status_code == 200
    root = r.json()["recado"]
    rid = int(root["id"])
    assert root.get("parent_id") is None
    assert root.get("respostas") == []

    # visitante responde
    r = client.post(
        f"/perfil/{alvo['id']}/recados",
        json={"texto": "tô de olho", "parent_id": rid},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["recado"]["texto"] == "tô de olho"
    assert data["recado"]["parent_id"] == str(rid)
    assert len(data["recados"]) == 1
    assert len(data["recados"][0]["respostas"]) == 1
    assert data["recados"][0]["respostas"][0]["autor_id"] == autor["id"]

    # não aninha resposta em resposta
    reply_id = int(data["recado"]["id"])
    r = client.post(
        f"/perfil/{alvo['id']}/recados",
        json={"texto": "nível 2", "parent_id": reply_id},
    )
    assert r.status_code == 400

    # dono do mural responde no próprio perfil
    client.cookies.clear()
    client.get(f"/p/{alvo['token']}")
    r = client.post(
        f"/perfil/{alvo['id']}/recados",
        json={"texto": "valeu irmão", "parent_id": rid},
    )
    assert r.status_code == 200
    assert r.json()["recado"]["autor_id"] == alvo["id"]
    assert len(r.json()["recados"][0]["respostas"]) == 2

    # raiz no próprio perfil continua bloqueada
    r = client.post(f"/perfil/{alvo['id']}/recados", json={"texto": "auto raiz"})
    assert r.status_code == 403

    # apagar raiz remove respostas
    r = client.delete(f"/perfil/{alvo['id']}/recados/{rid}")
    assert r.status_code == 200
    assert r.json()["recados"] == []
    assert dbmod.listar_recados(alvo["id"]) == []

    r = client.get(f"/perfil/{alvo['id']}")
    assert r.status_code == 200
    assert "/static/prototipo-perfil.js?v=33" in r.text
    js = (ROOT_DIR / "static" / "prototipo-perfil.js").read_text(encoding="utf-8")
    css = (ROOT_DIR / "static" / "style.css").read_text(encoding="utf-8")
    assert "data-reply-toggle" in js
    assert "proto-steam-respostas" in js
    assert "parent_id" in js
    assert ".proto-steam-respostas" in css
    assert ".proto-steam-reply-form" in css


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


def test_recados_paginados_5_por_pagina(client: TestClient):
    alvo = _login_part(client, "Alvo Page", "alvo.page", "11990009120")
    client.cookies.clear()
    autor = _login_part(client, "Autor Page", "autor.page", "11990009121")

    for i in range(6):
        r = client.post(f"/perfil/{alvo['id']}/recados", json={"texto": f"msg {i}"})
        assert r.status_code == 200

    r = client.get(f"/perfil/{alvo['id']}/recados")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 6
    assert data["por_pagina"] == 5
    assert data["paginas"] == 2
    assert data["pagina"] == 1
    assert len(data["recados"]) == 5

    r = client.get(f"/perfil/{alvo['id']}/recados?pagina=2")
    assert r.status_code == 200
    data = r.json()
    assert data["pagina"] == 2
    assert len(data["recados"]) == 1

    # dono vê o mural com pager no HTML
    client.cookies.clear()
    part = dbmod.criar_participante("Dono Page", status="liberado", celular="11990009122")
    dbmod.definir_credenciais(part["id"], "dono.page", "senha12345")
    for i in range(6):
        dbmod.criar_recado(part["id"], autor["id"], f"mural {i}")
    client.get(f"/p/{part['token']}")
    r = client.get("/meu-perfil")
    assert r.status_code == 200
    assert 'id="public-recados-pager"' in r.text
    assert "data-recados-prev" in r.text
    assert "data-recados-next" in r.text

