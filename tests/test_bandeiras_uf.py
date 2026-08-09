"""Bandeiras das UFs (Wikimedia Commons) para o seletor de times."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from src.config import BANDEIRAS_UF_DIR, ROOT_DIR


def test_bandeiras_uf_completas():
    meta_path = BANDEIRAS_UF_DIR / "ufs.json"
    assert meta_path.is_file()
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    ufs = meta["ufs"]
    assert len(ufs) == 27
    codes = {u["uf"] for u in ufs}
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
    assert len(meta.json()["ufs"]) == 27


def test_script_baixar_existe():
    assert (ROOT_DIR / "scripts" / "baixar_bandeiras_uf.py").is_file()
