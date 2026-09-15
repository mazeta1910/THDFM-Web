"""Acervo — fases da edição e participantes (Bloco A: fundação mata-mata)."""

from __future__ import annotations

from pathlib import Path

import pytest

import src.db as db


@pytest.fixture()
def acervo_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(Path(__file__).resolve().parents[1])
    monkeypatch.setenv("ACERVO_SKIP_IMPORT", "1")
    db.DB_PATH = tmp_path / "acervo.db"
    db.init_db()
    return db


def test_migracao_cria_tabelas_e_coluna(acervo_db):
    with acervo_db.get_db() as conn:
        nomes = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        cols = {
            r["name"]
            for r in conn.execute(
                "PRAGMA table_info(acervo_edicao_classificacao)"
            ).fetchall()
        }
    assert "acervo_edicao_fases" in nomes
    assert "acervo_edicao_participantes" in nomes
    assert "fase_id" in cols


def test_backfill_converte_edicao_legada(acervo_db):
    a = acervo_db.criar_acervo_clube("Alpha", uf="RR")
    b = acervo_db.criar_acervo_clube("Beta", uf="RR")
    acervo_db.criar_acervo_clube("Gama", uf="RR")  # não participa
    comp = acervo_db.criar_acervo_competicao(
        "Roraimense", ambito="estadual", uf="RR"
    )
    ed = acervo_db.criar_acervo_edicao(
        comp["id"], 2024, campeao_clube_id=a["id"], vice_clube_id=b["id"]
    )
    acervo_db.upsert_acervo_classificacao(
        ed["id"], clube_id=a["id"], posicao=1, v=3, e=0, d=0, gp=5, gc=1, auto=True
    )
    acervo_db.upsert_acervo_classificacao(
        ed["id"], clube_id=b["id"], posicao=2, v=1, e=0, d=2, gp=2, gc=4, auto=True
    )

    # Antes do backfill: dados "legados" sem fase.
    assert acervo_db.list_acervo_fases(ed["id"]) == []

    # Re-executa a migração — dispara o backfill idempotente.
    acervo_db.init_db()

    fases = acervo_db.list_acervo_fases(ed["id"])
    assert len(fases) == 1
    assert fases[0]["tipo"] == "pontos_corridos"
    assert fases[0]["n_linhas"] == 2

    with acervo_db.get_db() as conn:
        fids = {
            r["fase_id"]
            for r in conn.execute(
                "SELECT fase_id FROM acervo_edicao_classificacao WHERE edicao_id = ?",
                (ed["id"],),
            ).fetchall()
        }
    assert fids == {fases[0]["id"]}

    # Participantes = clubes da classificação + campeão/vice (Gama fica fora).
    parts = {p["clube_nome"] for p in acervo_db.list_acervo_participantes(ed["id"])}
    assert parts == {"Alpha", "Beta"}

    # Rodar o backfill de novo não duplica nada.
    acervo_db.init_db()
    assert len(acervo_db.list_acervo_fases(ed["id"])) == 1
    assert len(acervo_db.list_acervo_participantes(ed["id"])) == 2


def test_backfill_campeao_sem_tabela(acervo_db):
    camp = acervo_db.criar_acervo_clube("Campeão FC", uf="SP")
    comp = acervo_db.criar_acervo_competicao("Copa Teste", ambito="nacional")
    ed = acervo_db.criar_acervo_edicao(
        comp["id"], 2023, campeao_clube_id=camp["id"]
    )
    acervo_db.init_db()

    # Sem classificação => nenhuma fase implícita é criada.
    assert acervo_db.list_acervo_fases(ed["id"]) == []
    # Mas o campeão vira participante.
    parts = {p["clube_nome"] for p in acervo_db.list_acervo_participantes(ed["id"])}
    assert parts == {"Campeão FC"}


def test_crud_fases(acervo_db):
    comp = acervo_db.criar_acervo_competicao("Copa", ambito="nacional")
    ed = acervo_db.criar_acervo_edicao(comp["id"], 2024)

    f1 = acervo_db.criar_acervo_fase(ed["id"], nome="Oitavas", tipo="mata_mata")
    assert f1["ordem"] == 1
    f2 = acervo_db.criar_acervo_fase(ed["id"], nome="Quartas", tipo="mata_mata")
    assert f2["ordem"] == 2

    with pytest.raises(ValueError, match="ordem"):
        acervo_db.criar_acervo_fase(ed["id"], nome="X", tipo="mata_mata", ordem=1)
    with pytest.raises(ValueError, match="Tipo de fase"):
        acervo_db.criar_acervo_fase(ed["id"], tipo="invalido")

    upd = acervo_db.atualizar_acervo_fase(
        f1["id"], nome="Oitavas de final", tipo="mata_mata", ordem=1
    )
    assert upd["nome"] == "Oitavas de final"

    fases = acervo_db.list_acervo_fases(ed["id"])
    assert [f["nome"] for f in fases] == ["Oitavas de final", "Quartas"]

    assert acervo_db.apagar_acervo_fase(f2["id"]) is True
    assert len(acervo_db.list_acervo_fases(ed["id"])) == 1


def test_participantes_crud(acervo_db):
    comp = acervo_db.criar_acervo_competicao("Copa", ambito="nacional")
    ed = acervo_db.criar_acervo_edicao(comp["id"], 2024)
    a = acervo_db.criar_acervo_clube("Alpha")
    b = acervo_db.criar_acervo_clube("Beta")

    assert acervo_db.adicionar_acervo_participante(ed["id"], a["id"]) is True
    # Duplicado é ignorado (INSERT OR IGNORE).
    assert acervo_db.adicionar_acervo_participante(ed["id"], a["id"]) is False
    acervo_db.adicionar_acervo_participante(ed["id"], b["id"])

    parts = {p["clube_nome"] for p in acervo_db.list_acervo_participantes(ed["id"])}
    assert parts == {"Alpha", "Beta"}

    with pytest.raises(ValueError, match="Clube inválido"):
        acervo_db.adicionar_acervo_participante(ed["id"], 999999)

    assert acervo_db.remover_acervo_participante(ed["id"], a["id"]) is True
    parts = {p["clube_nome"] for p in acervo_db.list_acervo_participantes(ed["id"])}
    assert parts == {"Beta"}


def test_apagar_edicao_cascata_fases_participantes(acervo_db):
    comp = acervo_db.criar_acervo_competicao("Copa", ambito="nacional")
    ed = acervo_db.criar_acervo_edicao(comp["id"], 2024)
    a = acervo_db.criar_acervo_clube("Alpha")
    acervo_db.criar_acervo_fase(ed["id"], nome="Final", tipo="mata_mata")
    acervo_db.adicionar_acervo_participante(ed["id"], a["id"])

    assert acervo_db.apagar_acervo_edicao(ed["id"]) is True
    assert acervo_db.list_acervo_fases(ed["id"]) == []
    assert acervo_db.list_acervo_participantes(ed["id"]) == []
