"""Classificação: colocação, nomes e ordenação."""

from __future__ import annotations

from fastapi.testclient import TestClient

import src.db as db
from tests.conftest import login_admin as _login_admin


def test_classificacao_tem_coluna_pos_e_ordenacao(client: TestClient):
    db.criar_participante("Alesson Evangelista Longo", status="liberado", celular="11990000101")
    db.criar_participante("Beta Curto", status="liberado", celular="11990000102")
    _login_admin(client)

    r = client.get("/classificacao")
    assert r.status_code == 200
    assert "col-pos" in r.text
    assert "1º" in r.text
    assert "2º" in r.text
    assert "data-classificacao-sort" in r.text
    assert 'data-sort-key="pos"' in r.text
    assert 'data-sort-key="nome"' in r.text
    assert 'data-sort-key="soma"' in r.text
    assert "Alesson Evangelista Longo" in r.text
    assert "th-sort" in r.text
    assert "is-sortable" in r.text
    assert "/static/style.css?v=216" in r.text
    assert "th-sort-up" in r.text
    assert "th-sort-down" in r.text
    assert 'viewBox="0 0 12 16"' in r.text
    assert "zona-meio" in r.text or "zona-" in r.text
    assert "data-classificacao-export" in r.text
    assert "data-classificacao-export-target" in r.text
    assert "data-classificacao-export-ignore" in r.text
    assert "/static/classificacao-export.js" in r.text
    assert "Exportar classificação em PNG" in r.text
    assert "classificacao-card-head" in r.text
    assert 'data-export-slug="ao-vivo"' in r.text
    # Rodada é a última coluna (depois de Bônus / fidelidade).
    assert r.text.find('data-sort-key="fidelidade"') < r.text.find('data-sort-key="rod"')
    assert r.text.find('data-sort-key="soma"') < r.text.find('data-sort-key="placar"')
    assert r.text.find('data-sort-key="placar"') < r.text.find('data-sort-key="rod"')
