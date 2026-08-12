"""Testes do extrator de participantes da Copa do Brasil."""

from __future__ import annotations

from pathlib import Path

from scripts.extract_copa_participantes import (
    CSV_SRC,
    EXPECTED,
    OUT,
    extract_from_csv,
    is_club_name,
    merge_prefer_tables,
    extract_table_columns,
    extract_block_lists,
    _read_csv_rows,
)


def test_is_club_name_filtra_ruido():
    assert is_club_name("Flamengo")
    assert is_club_name("Atlético Mineiro")
    assert not is_club_name("Bahia (BA)")
    assert not is_club_name("Região Sul")
    assert not is_club_name("Oséas (Cruzeiro) – 10 gols")
    assert not is_club_name("Interporto 0 – 8 Bahia")
    assert not is_club_name("3º colocado do Campeonato Brasileiro 2016")
    assert not is_club_name("André Lima (Botafogo)")


def test_extract_copa_csv_cobertura_anos():
    assert CSV_SRC.is_file()
    bucket = extract_from_csv(CSV_SRC)
    assert len(bucket) >= 30
    # Quase todos os anos com cobertura utilizável (≥70% ou ≥ esperado-12)
    baixos = []
    for ano, exp in EXPECTED.items():
        got = len(bucket.get(ano, ()))
        bom = got >= max(20, int(exp * 0.70)) or got >= exp - 12
        if not bom:
            baixos.append((ano, got, exp))
    # 2000 vem truncado no dump wiki — no máximo esse ano fica BAIXO
    assert len(baixos) <= 1, baixos
    if baixos:
        assert baixos[0][0] == 2000


def test_extract_copa_nao_explode_com_ranking():
    rows = _read_csv_rows(CSV_SRC)
    tables = extract_table_columns(rows)
    blocks = extract_block_lists(rows)
    merged = merge_prefer_tables(tables, blocks)
    # Anos com ranking CBF no dump não devem estourar 2× o esperado
    for ano in (2011, 2012, 2013, 2018, 2022):
        exp = EXPECTED[ano]
        assert len(merged.get(ano, ())) <= int(exp * 1.35) + 5, (
            ano,
            len(merged.get(ano, ())),
            exp,
        )


def test_participacoes_csv_existe_e_consistente():
    assert OUT.is_file(), "rode scripts/extract_copa_participantes.py"
    text = OUT.read_text(encoding="utf-8-sig")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    assert lines[0].startswith("competicao;ano;nome")
    assert len(lines) > 1500
