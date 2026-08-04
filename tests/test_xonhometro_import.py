"""Importação WhatsApp → Xonhômetro."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import src.db as db
from src.xonhometro_seed import carregar_eventos_import
from tests.conftest import login_admin as _login_admin


@pytest.fixture()
def admin_users():
    return "mazeta=senha-dono=Mazeta:dono"


@pytest.fixture()
def fixture_import(tmp_path: Path) -> Path:
    data = {
        "gerado_em": "2026-08-04T20:00:00Z",
        "fonte": "teste",
        "versao": 3,
        "totais": {"saida": 2, "volta": 1, "banimento": 1},
        "eventos": [
            {
                "origem": "t1",
                "tipo": "saida",
                "data": "2026-07-01",
                "hora": "10:15",
                "motivo": "Grupo citou a Rithiely (Mazeta, 2 min antes)",
            },
            {
                "origem": "t2",
                "tipo": "volta",
                "data": "2026-07-01",
                "hora": "18:00",
                "motivo": "Adicionado por Mazeta",
            },
            {
                "origem": "t3",
                "tipo": "banimento",
                "data": "2026-07-02",
                "hora": "21:30",
                "motivo": "Banido por Tutui — xingou alguém no grupo",
            },
            {
                "origem": "t4",
                "tipo": "saida",
                "data": "2026-07-03",
                "hora": "09:00",
                "motivo": "Saiu de novo logo após voltar (4 min)",
            },
        ],
    }
    path = tmp_path / "eventos_import.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def test_carregar_eventos_import(fixture_import: Path):
    eventos, meta = carregar_eventos_import(fixture_import)
    assert len(eventos) == 4
    assert meta["quantidade"] == 4
    assert eventos[0]["tipo"] == "saida"
    assert "Rithiely" in (eventos[0]["motivo"] or "")


def test_importar_substitui_historico(client: TestClient, fixture_import: Path):
    db.criar_xonha_evento("saida", "2026-01-01", "manual antigo", hora="12:00")
    assert db.contar_xonha_eventos() == 1

    resultado = db.importar_xonha_eventos_whatsapp(
        substituir=True, path=fixture_import
    )
    assert resultado["inseridos"] == 4
    assert resultado["total_atual"] == 4
    assert db.contar_xonha_eventos() == 4

    stats = db.xonha_stats()
    assert stats["total_saidas"] == 2
    assert stats["total_voltas"] == 1
    assert stats["total_banimentos"] == 1
    assert stats["total_placar"] == 3

    eventos = db.list_xonha_eventos()
    motivos = " ".join(e.get("motivo") or "" for e in eventos)
    assert "Rithiely" in motivos


def test_importar_sem_substituir_ignora_duplicados(
    client: TestClient, fixture_import: Path
):
    db.importar_xonha_eventos_whatsapp(substituir=True, path=fixture_import)
    resultado = db.importar_xonha_eventos_whatsapp(
        substituir=False, path=fixture_import
    )
    assert resultado["inseridos"] == 0
    assert resultado["ignorados"] == 4
    assert db.contar_xonha_eventos() == 4


def test_admin_importar_whatsapp_rota(
    client: TestClient, fixture_import: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(
        "src.xonhometro_seed.caminho_import_padrao",
        lambda: fixture_import,
    )
    _login_admin(client)
    r = client.post("/admin/xonhometro/importar-whatsapp", follow_redirects=False)
    assert r.status_code == 303
    assert "msg=" in r.headers["location"]
    assert db.contar_xonha_eventos() == 4

    admin = client.get("/admin/xonhometro")
    assert admin.status_code == 200
    assert "Importar histórico WhatsApp" in admin.text
    assert "Importados" in admin.text or "saídas" in admin.text
