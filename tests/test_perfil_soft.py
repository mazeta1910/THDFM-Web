"""Perfil soft: times, banner e frase persistidos no servidor."""

from __future__ import annotations

from fastapi.testclient import TestClient

from src import db as dbmod
from tests.conftest import login_admin


def test_perfil_soft_vazio(client: TestClient):
    part = dbmod.criar_participante("Soft Vazio", status="liberado", celular="11990009001")
    soft = dbmod.perfil_soft_do_participante(part)
    assert soft["frase"] == ""
    assert soft["times"] == []
    assert soft["times_ids"] == []
    assert soft["times_locked"] == []
    assert soft["banner"]["kind"] == "preset"
    assert soft["banner"]["id"] == "padrao"


def test_salvar_perfil_soft_times_e_frase(client: TestClient):
    from src.clubes_catalogo import carregar_clubes

    clubes = [c for c in carregar_clubes() if c.get("tem_emblema")][:3]
    assert len(clubes) >= 2
    ids = [c["id"] for c in clubes]

    part = dbmod.criar_participante("Soft Times", status="liberado", celular="11990009002")
    dbmod.salvar_perfil_soft(
        part["id"],
        frase="Xonha raiz",
        relacionamento="solteiro",
        aniversario="1990-05-12",
        times_ids=ids,
        banner_preset="noite",
        clear_banner_custom=True,
    )
    fresh = dbmod.get_participante(part["id"])
    soft = dbmod.perfil_soft_do_participante(fresh)
    assert soft["frase"] == "Xonha raiz"
    assert soft["relacionamento"] == "solteiro"
    assert soft["aniversario"] == "1990-05-12"
    assert soft["times_ids"] == ids
    assert len(soft["times"]) == len(ids)
    assert soft["banner"]["kind"] == "preset"
    assert soft["banner"]["id"] == "noite"


def test_api_meu_perfil_soft_e_pagina(client: TestClient):
    from src.clubes_catalogo import carregar_clubes

    login_admin(client)
    dono = dbmod.get_participante_por_admin_login("mazeta")
    assert dono
    clubes = [c for c in carregar_clubes() if c.get("tem_emblema")][:2]
    ids = [c["id"] for c in clubes]

    r = client.put(
        "/meu-perfil/soft",
        json={
            "frase": "Salve o bolão",
            "times": ids,
            "banner_preset": "laranja",
            "clear_banner_custom": True,
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["frase"] == "Salve o bolão"
    assert data["times_ids"] == ids
    assert data["banner"]["id"] == "laranja"

    r = client.get("/meu-perfil")
    assert r.status_code == 200
    assert 'id="proto-perfil-soft"' in r.text
    assert "Salve o bolão" in r.text
    assert '"laranja"' in r.text
    assert ids[0] in r.text
    assert 'data-banner="laranja"' in r.text
    assert "/static/prototipo-perfil.js?v=31" in r.text

    r = client.get("/meu-perfil/editar")
    assert r.status_code == 200
    assert 'id="proto-perfil-soft"' in r.text
    assert "Salve o bolão" in r.text
    assert "/static/prototipo-times.js?v=18" in r.text


def test_perfil_publico_mostra_times_e_banner(client: TestClient):
    from src.clubes_catalogo import carregar_clubes

    alvo = dbmod.criar_participante("Soft Publico", status="liberado", celular="11990009003")
    clubes = [c for c in carregar_clubes() if c.get("tem_emblema")][:2]
    ids = [c["id"] for c in clubes]
    dbmod.salvar_perfil_soft(
        alvo["id"],
        frase="Frase pública",
        times_ids=ids,
        banner_preset="carbono",
        clear_banner_custom=True,
    )

    votante = dbmod.criar_participante("Soft Viewer", status="liberado", celular="11990009004")
    dbmod.definir_credenciais(votante["id"], "soft.viewer", "senha12345")
    client.get(f"/p/{votante['token']}")

    r = client.get(f"/perfil/{alvo['id']}")
    assert r.status_code == 200
    assert "Frase pública" in r.text
    assert 'data-banner="carbono"' in r.text
    assert ids[0] in r.text
    assert 'data-banner="carbono"' in r.text
    assert 'data-banner="gramado"' not in r.text


def test_benevides_palmeiras_fixo(client: TestClient):
    from src.clubes_catalogo import carregar_clubes
    from src.db import PALMEIRAS_CLUBE_ID

    pal = next(c for c in carregar_clubes() if c["id"] == PALMEIRAS_CLUBE_ID)
    assert pal["nome"] == "Palmeiras"

    bene = dbmod.criar_participante("Benevides", status="liberado", celular="11990009005")
    soft = dbmod.perfil_soft_do_participante(bene)
    assert soft["times_locked"] == [PALMEIRAS_CLUBE_ID]
    assert soft["times_ids"][0] == PALMEIRAS_CLUBE_ID
    assert soft["times"][0]["nome"] == "Palmeiras"
    assert soft["times"][0]["locked"] is True

    # tenta salvar sem Palmeiras — servidor reinsere
    outros = [c["id"] for c in carregar_clubes() if c.get("tem_emblema") and c["id"] != PALMEIRAS_CLUBE_ID][:2]
    dbmod.salvar_perfil_soft(bene["id"], times_ids=outros)
    fresh = dbmod.get_participante(bene["id"])
    soft = dbmod.perfil_soft_do_participante(fresh)
    assert soft["times_ids"][0] == PALMEIRAS_CLUBE_ID
    assert set(soft["times_ids"]) >= {PALMEIRAS_CLUBE_ID, *outros}

    dbmod.definir_credenciais(bene["id"], "bene.palmeiras", "senha12345")
    client.get(f"/p/{bene['token']}")
    r = client.put("/meu-perfil/soft", json={"times": outros})
    assert r.status_code == 200
    assert r.json()["times_ids"][0] == PALMEIRAS_CLUBE_ID
    assert r.json()["times_locked"] == [PALMEIRAS_CLUBE_ID]

    r = client.get("/meu-perfil")
    assert r.status_code == 200
    assert "Palmeiras" in r.text
    assert PALMEIRAS_CLUBE_ID in r.text
    assert '"times_locked"' in r.text

    js = (__import__("src.config", fromlist=["ROOT_DIR"]).ROOT_DIR / "static" / "prototipo-times.js").read_text(
        encoding="utf-8"
    )
    assert "times_locked" in js
    assert "isLocked" in js
    assert "is-locked" in js


def test_api_banner_upload(client: TestClient):
    login_admin(client)
    r = client.post(
        "/meu-perfil/banner",
        files={"banner": ("capa.jpg", b"fake-jpeg-bytes", "image/jpeg")},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["banner"]["kind"] == "custom"
    assert data["banner"]["url"]
    assert data["banner"]["url"].startswith("/banners/")

