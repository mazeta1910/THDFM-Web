"""Acervo — resolução de confrontos de mata-mata (Bloco B)."""

from __future__ import annotations

from pathlib import Path

import pytest

import src.db as db
from src.acervo import normalizar_confronto_formato, resolver_confronto

A, B = 10, 20  # ids fictícios de clubes


@pytest.fixture()
def acervo_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(Path(__file__).resolve().parents[1])
    monkeypatch.setenv("ACERVO_SKIP_IMPORT", "1")
    db.DB_PATH = tmp_path / "acervo.db"
    db.init_db()
    return db


def _mata_mata(acervo_db):
    """Cria clubes, competição, edição e uma fase mata-mata; devolve ids."""
    a = acervo_db.criar_acervo_clube("Alpha", uf="SP")
    b = acervo_db.criar_acervo_clube("Beta", uf="RJ")
    comp = acervo_db.criar_acervo_competicao("Copa", ambito="nacional")
    ed = acervo_db.criar_acervo_edicao(comp["id"], 2024)
    fase = acervo_db.criar_acervo_fase(ed["id"], nome="Final", tipo="mata_mata")
    return a, b, ed, fase


def _r(**kw):
    base = dict(clube_a_id=A, clube_b_id=B)
    base.update(kw)
    return resolver_confronto(**base)


def test_formato_normaliza_e_valida():
    assert normalizar_confronto_formato("IDA_VOLTA") == "ida_volta"
    assert normalizar_confronto_formato(None) == "jogo_unico"
    with pytest.raises(ValueError):
        normalizar_confronto_formato("melhor_de_3")


def test_jogo_unico_vitoria_direta():
    assert _r(formato="jogo_unico", gols_a_ida=2, gols_b_ida=1) == (A, "agregado")
    assert _r(formato="jogo_unico", gols_a_ida=0, gols_b_ida=3) == (B, "agregado")


def test_jogo_unico_empate_sem_penaltis_indefinido():
    assert _r(formato="jogo_unico", gols_a_ida=1, gols_b_ida=1) == (None, None)


def test_jogo_unico_empate_penaltis():
    r = _r(
        formato="jogo_unico",
        gols_a_ida=1,
        gols_b_ida=1,
        tem_penaltis=True,
        penaltis_a=4,
        penaltis_b=2,
    )
    assert r == (A, "penaltis")


def test_dados_insuficientes():
    assert _r(formato="jogo_unico", gols_a_ida=None, gols_b_ida=2) == (None, None)
    assert _r(
        formato="ida_volta",
        gols_a_ida=1,
        gols_b_ida=1,
        gols_a_volta=2,
        gols_b_volta=None,
    ) == (None, None)


def test_ida_volta_agregado():
    # A: 2+1=3 | B: 0+2=2 -> A vence no agregado
    assert _r(
        formato="ida_volta",
        gols_a_ida=2,
        gols_b_ida=0,
        gols_a_volta=1,
        gols_b_volta=2,
    ) == (A, "agregado")


def test_ida_volta_gol_fora_desempata():
    # Agregado 2x2. Fora de A (volta)=1, fora de B (ida)=2 -> B pelo gol fora.
    r = _r(
        formato="ida_volta",
        gols_a_ida=1,
        gols_b_ida=2,
        gols_a_volta=1,
        gols_b_volta=0,
        gol_fora_de_casa=True,
    )
    assert r == (B, "gol_fora")


def test_ida_volta_gol_fora_desligado_vai_para_penaltis():
    # Mesmo agregado 2x2, mas sem regra de gol fora -> pênaltis decide.
    r = _r(
        formato="ida_volta",
        gols_a_ida=1,
        gols_b_ida=2,
        gols_a_volta=1,
        gols_b_volta=0,
        gol_fora_de_casa=False,
        tem_penaltis=True,
        penaltis_a=5,
        penaltis_b=4,
    )
    assert r == (A, "penaltis")


def test_ida_volta_empate_total_e_gol_fora_iguais_penaltis():
    # Agregado 2x2, gols fora iguais (1 e 1) -> pênaltis.
    r = _r(
        formato="ida_volta",
        gols_a_ida=1,
        gols_b_ida=1,
        gols_a_volta=1,
        gols_b_volta=1,
        gol_fora_de_casa=True,
        tem_penaltis=True,
        penaltis_a=2,
        penaltis_b=4,
    )
    assert r == (B, "penaltis")


# --- Integração com o banco (CRUD + derivação ao salvar) -----------------


def test_criar_confronto_adiciona_participantes(acervo_db):
    a, b, ed, fase = _mata_mata(acervo_db)
    cf = acervo_db.criar_acervo_confronto(
        fase["id"], clube_a_id=a["id"], clube_b_id=b["id"], formato="ida_volta"
    )
    assert cf["ordem"] == 1
    assert cf["clube_a_nome"] == "Alpha"
    assert cf["clube_b_nome"] == "Beta"
    # Selecionar os clubes no confronto já os coloca no pool de participantes.
    parts = {p["clube_nome"] for p in acervo_db.list_acervo_participantes(ed["id"])}
    assert parts == {"Alpha", "Beta"}


def test_confronto_clubes_iguais_erro(acervo_db):
    a, _b, _ed, fase = _mata_mata(acervo_db)
    with pytest.raises(ValueError, match="diferentes"):
        acervo_db.criar_acervo_confronto(
            fase["id"], clube_a_id=a["id"], clube_b_id=a["id"]
        )


def test_atualizar_confronto_deriva_vencedor(acervo_db):
    a, b, _ed, fase = _mata_mata(acervo_db)
    cf = acervo_db.criar_acervo_confronto(
        fase["id"], clube_a_id=a["id"], clube_b_id=b["id"], formato="jogo_unico"
    )
    upd = acervo_db.atualizar_acervo_confronto(
        cf["id"],
        clube_a_id=a["id"],
        clube_b_id=b["id"],
        formato="jogo_unico",
        gols_a_ida=3,
        gols_b_ida=1,
    )
    assert upd["vencedor_clube_id"] == a["id"]
    assert upd["vencedor_criterio"] == "agregado"


def test_atualizar_confronto_penaltis_e_gol_fora(acervo_db):
    a, b, _ed, fase = _mata_mata(acervo_db)
    cf = acervo_db.criar_acervo_confronto(
        fase["id"], clube_a_id=a["id"], clube_b_id=b["id"], formato="ida_volta"
    )
    upd = acervo_db.atualizar_acervo_confronto(
        cf["id"],
        clube_a_id=a["id"],
        clube_b_id=b["id"],
        formato="ida_volta",
        gol_fora_de_casa=True,
        gols_a_ida=1,
        gols_b_ida=2,
        gols_a_volta=1,
        gols_b_volta=0,
    )
    # Agregado 2x2, B fez 2 fora contra 1 de A -> B pelo gol fora.
    assert upd["vencedor_clube_id"] == b["id"]
    assert upd["vencedor_criterio"] == "gol_fora"


def test_vencedor_manual_override(acervo_db):
    a, b, _ed, fase = _mata_mata(acervo_db)
    cf = acervo_db.criar_acervo_confronto(
        fase["id"], clube_a_id=a["id"], clube_b_id=b["id"], formato="jogo_unico"
    )
    # Placar diz A, mas admin força B (ex.: punição/WO histórico).
    upd = acervo_db.atualizar_acervo_confronto(
        cf["id"],
        clube_a_id=a["id"],
        clube_b_id=b["id"],
        formato="jogo_unico",
        gols_a_ida=3,
        gols_b_ida=1,
        vencedor_manual=True,
        vencedor_clube_id=b["id"],
    )
    assert upd["vencedor_clube_id"] == b["id"]
    assert upd["vencedor_criterio"] == "manual"

    with pytest.raises(ValueError, match="um dos clubes"):
        acervo_db.atualizar_acervo_confronto(
            cf["id"],
            clube_a_id=a["id"],
            clube_b_id=b["id"],
            formato="jogo_unico",
            vencedor_manual=True,
            vencedor_clube_id=999999,
        )


def test_apagar_confronto_e_cascata_fase(acervo_db):
    a, b, _ed, fase = _mata_mata(acervo_db)
    cf = acervo_db.criar_acervo_confronto(
        fase["id"], clube_a_id=a["id"], clube_b_id=b["id"]
    )
    assert len(acervo_db.list_acervo_confrontos(fase["id"])) == 1
    assert acervo_db.apagar_acervo_confronto(cf["id"]) is True
    assert acervo_db.list_acervo_confrontos(fase["id"]) == []

    # Apagar a fase remove seus confrontos em cascata.
    cf2 = acervo_db.criar_acervo_confronto(
        fase["id"], clube_a_id=a["id"], clube_b_id=b["id"]
    )
    acervo_db.apagar_acervo_fase(fase["id"])
    assert acervo_db.get_acervo_confronto(cf2["id"]) is None
