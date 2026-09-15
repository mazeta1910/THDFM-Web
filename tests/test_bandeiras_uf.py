"""Bandeiras das UFs (Wikimedia Commons) para o seletor de times."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from src.config import BANDEIRAS_UF_DIR, ROOT_DIR

# 26 estados + DF. Além destas, o seletor aceita entradas custom (ex.: "EX"
# / Exterior, para clubes de fora do Brasil), então não travamos a contagem.
UFS_OFICIAIS = {
    "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG",
    "MS", "MT", "PA", "PB", "PE", "PI", "PR", "RJ", "RN", "RO", "RR",
    "RS", "SC", "SE", "SP", "TO",
}


def test_bandeiras_uf_completas():
    meta_path = BANDEIRAS_UF_DIR / "ufs.json"
    assert meta_path.is_file()
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    ufs = meta["ufs"]
    codes = {u["uf"] for u in ufs}
    assert UFS_OFICIAIS <= codes
    assert "SP" in codes and "RJ" in codes and "DF" in codes
    for u in ufs:
        svg = BANDEIRAS_UF_DIR / u["arquivo"]
        assert svg.is_file(), u["uf"]
        assert svg.stat().st_size > 200


def test_bandeiras_uf_servidas(client: TestClient):
    r = client.get("/bandeiras-uf/SP.svg")
    assert r.status_code == 200
    assert b"<svg" in r.content.lower() or b"<?xml" in r.content.lower()
    meta = client.get("/bandeiras-uf/ufs.json")
    assert meta.status_code == 200
    codes = {u["uf"] for u in meta.json()["ufs"]}
    assert UFS_OFICIAIS <= codes


def test_script_baixar_existe():
    assert (ROOT_DIR / "scripts" / "baixar_bandeiras_uf.py").is_file()
