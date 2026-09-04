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
    assert "/static/style.css?v=337" in r.text
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


def test_renomear_nao_infla_rod_ao_vivo(client: TestClient, tmp_path, monkeypatch):
    """Baseline do snapshot é por id — trocar o nome não zera a base."""
    from src.ranking import calcular_classificacao, confirmar_rodada

    av_dir = tmp_path / "avatars"
    monkeypatch.setattr("src.config.AVATARES_DIR", av_dir)
    monkeypatch.setattr("src.app.AVATARES_DIR", av_dir)

    _login_admin(client)
    a = db.criar_participante("Nome Antigo Ottoni", status="liberado", celular="11990000201")
    b = db.criar_participante("Outro Estavel", status="liberado", celular="11990000202")
    confrontos = db.list_confrontos_completos("oitavas")
    jogo = confrontos[0]["jogos"][0]
    db.salvar_palpite_jogo(a["id"], jogo["id"], 2, 0)
    db.salvar_palpite_jogo(b["id"], jogo["id"], 0, 1)
    db.set_resultado_jogo(jogo["id"], 2, 0)

    antes = next(r for r in calcular_classificacao() if r["participante_id"] == a["id"])
    assert antes["soma"] > 0
    confirmar_rodada()

    # Snapshot legado ainda com chave=nome (como em produção antes do fix)
    db.save_snapshot(
        {
            "somas": {"Nome Antigo Ottoni": antes["soma"], "Outro Estavel": 0},
            "posicoes": {"Nome Antigo Ottoni": 1, "Outro Estavel": 2},
        }
    )

    db.atualizar_nome_participante(a["id"], "Alisson Ottoni")
    depois = next(r for r in calcular_classificacao() if r["participante_id"] == a["id"])
    assert depois["participante"] == "Alisson Ottoni"
    assert depois["soma"] == antes["soma"]
    assert depois["rod"] == 0
    assert depois["movimento"] == 0

    snap = db.load_snapshot()
    assert snap and snap.get("por_id")
    assert str(a["id"]) in snap["somas"]
    assert "Nome Antigo Ottoni" not in snap["somas"]


def test_historico_rehidrata_avatar_apos_troca(client: TestClient, tmp_path, monkeypatch):
    """Rodada confirmada não fica com 404 se o arquivo antigo foi apagado."""
    from src.ranking import confirmar_rodada, enriquecer_avatares_historico

    av_dir = tmp_path / "avatars"
    monkeypatch.setattr("src.config.AVATARES_DIR", av_dir)
    monkeypatch.setattr("src.app.AVATARES_DIR", av_dir)

    _login_admin(client)
    a = db.criar_participante("Mazeta Foto", status="liberado", celular="11990000203")
    antigo = f"{a['id']}_old.jpg"
    (av_dir / antigo).write_bytes(b"old-img")
    db.salvar_avatar(a["id"], antigo)

    confrontos = db.list_confrontos_completos("oitavas")
    jogo = confrontos[0]["jogos"][0]
    db.salvar_palpite_jogo(a["id"], jogo["id"], 1, 0)
    db.set_resultado_jogo(jogo["id"], 1, 0)
    hist = confirmar_rodada()

    # Troca foto: apaga o arquivo antigo (como a rota de conta faz)
    (av_dir / antigo).unlink()
    novo = f"{a['id']}_new.jpg"
    (av_dir / novo).write_bytes(b"new-img")
    db.salvar_avatar(a["id"], novo)

    full = db.get_rodada_historico(hist["id"])
    assert full
    linha_raw = next(r for r in full["linhas"] if r["participante_id"] == a["id"])
    assert linha_raw["avatar_path"] == antigo

    linhas = enriquecer_avatares_historico(full["linhas"])
    linha = next(r for r in linhas if r["participante_id"] == a["id"])
    assert linha["avatar_path"] == novo

    r = client.get(f"/classificacao?rodada={hist['id']}")
    assert r.status_code == 200
    assert f"/avatars/{novo}" in r.text
    assert f"/avatars/{antigo}" not in r.text
    from src.app import avatar_url

    assert avatar_url(antigo) != f"/avatars/{antigo}"
    assert avatar_url(novo) == f"/avatars/{novo}"
