"""Planilha de palpites: emblemas, fotos e agrupamento por time."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import src.db as db
from src.config import ROOT_DIR
from src.transparencia import montar_portal


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(ROOT_DIR)
    monkeypatch.setenv(
        "ADMIN_USERS",
        "mazeta=senha-dono=Mazeta:dono",
    )
    db.DB_PATH = tmp_path / "test.db"
    (tmp_path / "avatars").mkdir(exist_ok=True)
    (tmp_path / "comprovantes").mkdir(exist_ok=True)
    db.init_db()

    from src.app import app

    with TestClient(app) as c:
        yield c


def _login_admin(client: TestClient):
    r = client.post(
        "/admin/login",
        data={"login": "mazeta", "password": "senha-dono"},
        follow_redirects=False,
    )
    assert r.status_code == 303


def test_montar_portal_agrupa_por_time_e_inclui_avatar(client: TestClient):
    casa = db.criar_participante("Casa Fan", status="liberado", celular="11990000001")
    fora = db.criar_participante("Fora Fan", status="liberado", celular="11990000002")
    emp = db.criar_participante("Empate Fan", status="liberado", celular="11990000003")
    db.salvar_avatar(casa["id"], "casa.jpg")

    confrontos = db.list_confrontos_completos("oitavas")
    assert confrontos
    c = confrontos[0]
    jogo = next(j for j in c["jogos"] if j.get("perna") == "ida")
    mandante = jogo["mandante_clube_id"]
    visitante = "b" if mandante == "a" else "a"

    db.salvar_palpite_jogo(casa["id"], jogo["id"], 2, 0)
    db.salvar_palpite_jogo(fora["id"], jogo["id"], 0, 3)
    db.salvar_palpite_jogo(emp["id"], jogo["id"], 1, 1)

    tabelas = [
        t
        for t in montar_portal("oitavas", exigir_resultado=False)
        if t["jogo_id"] == jogo["id"]
    ]
    assert len(tabelas) == 1
    linhas = tabelas[0]["linhas"]
    grupos = [r for r in linhas if r["tipo"] == "grupo"]
    assert [g["grupo"] for g in grupos] == ["casa", "empate", "fora"]

    casa_row = next(r for r in linhas if r.get("nome") == "Casa Fan")
    assert casa_row["grupo"] == "casa"
    assert casa_row["avatar_path"] == "casa.jpg"
    fora_row = next(r for r in linhas if r.get("nome") == "Fora Fan")
    assert fora_row["grupo"] == "fora"
    emp_row = next(r for r in linhas if r.get("nome") == "Empate Fan")
    assert emp_row["grupo"] == "empate"

    # Empate com pênaltis conta como vitória do time escolhido
    db.salvar_palpite_penaltis(emp["id"], c["id"], visitante)
    tabelas2 = [
        t
        for t in montar_portal("oitavas", exigir_resultado=False)
        if t["jogo_id"] == jogo["id"]
    ]
    emp2 = next(r for r in tabelas2[0]["linhas"] if r.get("nome") == "Empate Fan")
    assert emp2["grupo"] == "fora"


def test_admin_palpites_mostra_emblemas_e_fotos(client: TestClient):
    part = db.criar_participante("Foto User", status="liberado", celular="11990000009")
    db.salvar_avatar(part["id"], "foto.jpg")
    confrontos = db.list_confrontos_completos("oitavas")
    jogo = next(j for j in confrontos[0]["jogos"] if j.get("perna") == "ida")
    db.salvar_palpite_jogo(part["id"], jogo["id"], 1, 0)

    _login_admin(client)
    r = client.get("/admin/palpites?fase=oitavas&perna=ida")
    assert r.status_code == 200
    assert "planilha-th-emblema" in r.text
    assert "planilha-grupo" in r.text
    assert "planilha-avatar" in r.text
    assert "Foto User" in r.text
    assert "/avatars/foto.jpg" in r.text
    assert "planilha-zebra" in r.text
