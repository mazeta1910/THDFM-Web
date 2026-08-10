"""Catálogo de times (FM) e JSON do seletor no perfil."""

from __future__ import annotations

from fastapi.testclient import TestClient

from src.clubes_catalogo import carregar_clubes, emblema_fm_url, unique_id_arquivo
from src.config import EMBLEMAS_FM_DIR
from tests.conftest import login_admin


def test_unique_id_arquivo():
    assert unique_id_arquivo("301.260") == "301260"
    assert unique_id_arquivo("2.000.320.598") == "2000320598"


def test_catalogo_clubes_carrega():
    clubes = carregar_clubes()
    assert len(clubes) >= 1200
    assert all(c["uf"] and c["nome"] and c["id"] for c in clubes)
    pal = next((c for c in clubes if c["nome"] == "Palmeiras"), None)
    assert pal is not None
    assert pal["uf"] == "SP"
    assert pal["tem_emblema"] is True
    assert (EMBLEMAS_FM_DIR / f"{pal['id_arquivo']}.png").is_file()


def test_legado_times_redireciona(client: TestClient):
    r = client.get("/prototipo/times", follow_redirects=False)
    assert r.status_code == 301
    assert "/meu-perfil/editar" in (r.headers.get("location") or "")


def test_meu_perfil_editar_tem_seletor(client: TestClient):
    login_admin(client)
    r = client.get("/meu-perfil/editar")
    assert r.status_code == 200
    assert "Times do coração" in r.text
    assert "Torcedor Misto" in r.text
    assert 'id="proto-times"' in r.text
    assert "/static/prototipo-times.js?v=19" in r.text
    assert 'data-clubes-src="/meu-perfil/clubes.json"' in r.text
    assert 'id="proto-ufs-toggle"' in r.text
    assert 'class="proto-times-ufs is-collapsed"' in r.text
    assert r.text.index('id="proto-list"') < r.text.index('id="proto-times-ufs"')
    assert 'proto-times-list-wrap--suggest' in r.text


def test_meu_perfil_clubes_json_e_emblema(client: TestClient):
    login_admin(client)
    r = client.get("/meu-perfil/clubes.json")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] >= 1200
    sample = data["clubes"][0]
    assert sample["emblema"].startswith("/emblemas-fm/")
    emb = client.get(sample["emblema"])
    assert emb.status_code == 200
    assert emb.headers["content-type"].startswith("image/")


def test_emblema_fm_url():
    assert emblema_fm_url("78038748") == "/emblemas-fm/78038748.png"
