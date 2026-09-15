"""Acervo — validadores e CRUD SQLite (MVP)."""

from __future__ import annotations

from pathlib import Path

import pytest

import src.db as db
from src import acervo


@pytest.fixture()
def acervo_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(Path(__file__).resolve().parents[1])
    db.DB_PATH = tmp_path / "acervo.db"
    db.init_db()
    return db


def test_slugify_e_ufs():
    assert acervo.slugify("Série A") == "serie-a"
    assert acervo.slugify("  Campeonato  Roraimense  ") == "campeonato-roraimense"
    assert acervo.normalizar_uf("sp") == "SP"
    assert acervo.normalizar_uf("") == ""
    with pytest.raises(ValueError):
        acervo.normalizar_uf("XX")
    with pytest.raises(ValueError):
        acervo.normalizar_uf("", obrigatorio=True)


def test_migrate_cria_tabelas(acervo_db):
    with acervo_db.get_db() as conn:
        nomes = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert "acervo_clubes" in nomes
    assert "acervo_competicoes" in nomes
    assert "acervo_edicoes" in nomes


def test_crud_clube(acervo_db):
    c = acervo_db.criar_acervo_clube(
        "Baré Esporte Clube",
        nome_popular="Baré",
        uf="RR",
        fm_unique_id="123.456",
    )
    assert c["id"] > 0
    assert c["nome"] == "Baré Esporte Clube"
    assert c["uf"] == "RR"
    assert c["extinto"] is False

    lista = acervo_db.list_acervo_clubes(q="baré")
    assert len(lista) == 1

    upd = acervo_db.atualizar_acervo_clube(
        c["id"],
        nome="Baré EC",
        nome_popular="Baré",
        uf="RR",
        fm_unique_id="123.456",
        extinto=True,
        notas="Extinto em teste",
    )
    assert upd["nome"] == "Baré EC"
    assert upd["extinto"] is True

    with pytest.raises(ValueError, match="Unique ID"):
        acervo_db.criar_acervo_clube("Outro", fm_unique_id="123.456")

    assert acervo_db.apagar_acervo_clube(c["id"]) is True
    assert acervo_db.get_acervo_clube(c["id"]) is None


def test_crud_competicao_e_edicao(acervo_db):
    camp = acervo_db.criar_acervo_clube("São Raimundo-RR", uf="RR")
    vice = acervo_db.criar_acervo_clube("Atlético Roraima", uf="RR")

    comp = acervo_db.criar_acervo_competicao(
        "Campeonato Roraimense",
        ambito="estadual",
        uf="RR",
        cobertura="campeao_apenas",
    )
    assert comp["slug"] == "campeonato-roraimense"
    assert comp["ambito"] == "estadual"
    assert comp["uf"] == "RR"

    with pytest.raises(ValueError, match="UF"):
        acervo_db.criar_acervo_competicao("Paulista", ambito="estadual", uf="")

    ed = acervo_db.criar_acervo_edicao(
        comp["id"],
        2024,
        campeao_clube_id=camp["id"],
        vice_clube_id=vice["id"],
        fonte_url="https://example.com/roraimense-2024",
    )
    assert ed["ano"] == 2024
    assert ed["campeao_nome"] == "São Raimundo-RR"
    assert ed["vice_nome"] == "Atlético Roraima"

    with pytest.raises(ValueError, match="Já existe"):
        acervo_db.criar_acervo_edicao(comp["id"], 2024)

    eds = acervo_db.list_acervo_edicoes(competicao_id=comp["id"])
    assert len(eds) == 1

    resumo = acervo_db.resumo_acervo()
    assert resumo["clubes"] == 2
    assert resumo["competicoes"] == 1
    assert resumo["edicoes"] == 1

    assert acervo_db.apagar_acervo_edicao(ed["id"]) is True
    # Apagar competição em cascata não quebra clubes
    assert acervo_db.apagar_acervo_competicao(comp["id"]) is True
    assert acervo_db.get_acervo_clube(camp["id"]) is not None


def test_crud_classificacao(acervo_db):
    a = acervo_db.criar_acervo_clube("Alpha", uf="RR")
    b = acervo_db.criar_acervo_clube("Beta", uf="RR")
    comp = acervo_db.criar_acervo_competicao(
        "Roraimense", ambito="estadual", uf="RR"
    )
    ed = acervo_db.criar_acervo_edicao(comp["id"], 2024, campeao_clube_id=a["id"])
    assert ed["tem_tabela"] is False

    r1 = acervo_db.upsert_acervo_classificacao(
        ed["id"],
        clube_id=a["id"],
        posicao=1,
        pts=9,
        j=3,
        v=3,
        e=0,
        d=0,
        gp=5,
        gc=1,
    )
    assert r1["posicao"] == 1
    assert r1["sg"] == 4
    assert acervo_db.get_acervo_edicao(ed["id"])["tem_tabela"] is True

    acervo_db.upsert_acervo_classificacao(
        ed["id"], clube_id=b["id"], posicao=2, pts=3, j=3, v=1, e=0, d=2, gp=2, gc=4
    )
    rows = acervo_db.list_acervo_classificacao(ed["id"])
    assert [r["clube_nome"] for r in rows] == ["Alpha", "Beta"]

    with pytest.raises(ValueError, match="posição"):
        acervo_db.upsert_acervo_classificacao(
            ed["id"], clube_id=a["id"], posicao=2  # conflito com Beta
        )

    # Atualiza mesma linha (mesmo clube)
    upd = acervo_db.upsert_acervo_classificacao(
        ed["id"], clube_id=a["id"], posicao=1, pts=10, j=4, v=3, e=1, d=0, gp=6, gc=2
    )
    assert upd["pts"] == 10

    assert acervo_db.apagar_acervo_classificacao(rows[1]["id"]) is True
    assert len(acervo_db.list_acervo_classificacao(ed["id"])) == 1

    assert acervo_db.limpar_acervo_classificacao(ed["id"]) == 1
    assert acervo_db.list_acervo_classificacao(ed["id"]) == []
    assert acervo_db.get_acervo_edicao(ed["id"])["tem_tabela"] is False
