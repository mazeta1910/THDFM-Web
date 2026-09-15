"""Importação CSV → Acervo."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import src.db as db
from src.acervo_seed import META_CHAVE, importar_acervo_csvs
from tests.conftest import login_admin


@pytest.fixture()
def acervo_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(Path(__file__).resolve().parents[1])
    monkeypatch.setenv("ACERVO_SKIP_IMPORT", "1")
    db.DB_PATH = tmp_path / "acervo_import.db"
    db.init_db()
    return db


def test_importar_acervo_csvs_popula_tabelas(acervo_db):
    stats = importar_acervo_csvs(force=True)
    assert stats["ok"] is True
    assert stats["skipped"] is False
    tot = stats["totais"]
    assert tot["clubes"] >= 1000
    assert tot["competicoes"] == 4
    assert tot["edicoes"] >= 150
    assert tot["linhas_tabela"] >= 3000

    comps = {c["slug"]: c for c in acervo_db.list_acervo_competicoes(limite=50)}
    assert "serie-a" in comps
    assert "copa-do-brasil" in comps

    eds_a = acervo_db.list_acervo_edicoes(
        competicao_id=comps["serie-a"]["id"], limite=500
    )
    assert len(eds_a) >= 60
    assert any(e.get("tem_tabela") for e in eds_a)

    again = importar_acervo_csvs(force=False)
    assert again.get("skipped") is True


def test_admin_mostra_dados_apos_import(client: TestClient):
    importar_acervo_csvs(force=True)
    login_admin(client, "mazeta", "senha-dono")
    r = client.get("/admin/acervo")
    assert r.status_code == 200
    assert "Reimportar CSVs" in r.text
    assert (
        "Flamengo" in r.text
        or "Palmeiras" in r.text
        or "São Paulo" in r.text
        or "Santos" in r.text
    )

    r2 = client.post("/admin/acervo/importar-csvs", follow_redirects=False)
    assert r2.status_code == 303
    assert "msg=" in (r2.headers.get("location") or "")
