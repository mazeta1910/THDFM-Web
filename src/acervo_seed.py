"""Importa CSVs históricos (torneios + catálogo FM) para o Acervo."""

from __future__ import annotations

import csv
import sqlite3
from pathlib import Path
from typing import Any

from src.clubes_catalogo import carregar_clubes
from src.config import ROOT_DIR
from src.grid_historico import (
    CAMPEOES_COPA_CSV,
    CLASSIF_B_CSV,
    CLASSIF_C_CSV,
    CLASSIF_CSV,
    FINAIS_C_CSV,
    resolver_clube_fm,
)

META_CHAVE = "acervo_import_csvs_v1"

_COMPETICOES: tuple[dict[str, Any], ...] = (
    {
        "slug": "serie-a",
        "nome": "Campeonato Brasileiro Série A",
        "ambito": "nacional",
        "cobertura": "completa",
        "csv": CLASSIF_CSV,
    },
    {
        "slug": "serie-b",
        "nome": "Campeonato Brasileiro Série B",
        "ambito": "nacional",
        "cobertura": "completa",
        "csv": CLASSIF_B_CSV,
    },
    {
        "slug": "serie-c",
        "nome": "Campeonato Brasileiro Série C",
        "ambito": "nacional",
        "cobertura": "parcial",
        "csv": CLASSIF_C_CSV,
    },
    {
        "slug": "copa-do-brasil",
        "nome": "Copa do Brasil",
        "ambito": "nacional",
        "cobertura": "campeao_apenas",
        "csv": None,
    },
)


def _ler_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8-sig")
    return list(csv.DictReader(text.splitlines(), delimiter=";"))


def _int_opt(raw: str | None) -> int | None:
    s = (raw or "").strip().replace("+", "")
    if not s:
        return None
    try:
        return int(float(s.replace(",", ".")))
    except ValueError:
        return None


def _ensure_clube(
    conn: sqlite3.Connection,
    *,
    por_fm: dict[str, int],
    por_nome_uf: dict[tuple[str, str], int],
    nome: str,
    uf: str = "",
    fm_id: str | None = None,
) -> int:
    nome_n = " ".join((nome or "").strip().split())
    if not nome_n:
        raise ValueError("Nome de clube vazio.")
    uf_n = (uf or "").strip().upper()
    if fm_id and fm_id in por_fm:
        return por_fm[fm_id]
    chave = (nome_n.casefold(), uf_n)
    if chave in por_nome_uf:
        return por_nome_uf[chave]
    cur = conn.execute(
        """
        INSERT INTO acervo_clubes (nome, nome_popular, uf, fm_unique_id, extinto, notas)
        VALUES (?, '', ?, ?, 0, '')
        """,
        (nome_n, uf_n, fm_id),
    )
    cid = int(cur.lastrowid)
    if fm_id:
        por_fm[fm_id] = cid
    por_nome_uf[chave] = cid
    return cid


def _resolver_ou_criar(
    conn: sqlite3.Connection,
    *,
    por_fm: dict[str, int],
    por_nome_uf: dict[tuple[str, str], int],
    nome_wiki: str,
) -> int | None:
    nome = (nome_wiki or "").strip()
    if not nome:
        return None
    hit = resolver_clube_fm(nome)
    if hit:
        return _ensure_clube(
            conn,
            por_fm=por_fm,
            por_nome_uf=por_nome_uf,
            nome=str(hit.get("nome") or nome),
            uf=str(hit.get("uf") or ""),
            fm_id=str(hit.get("id") or "") or None,
        )
    return _ensure_clube(
        conn,
        por_fm=por_fm,
        por_nome_uf=por_nome_uf,
        nome=nome,
        uf="",
        fm_id=None,
    )


def _importar_catalogo_fm(
    conn: sqlite3.Connection,
    *,
    por_fm: dict[str, int],
    por_nome_uf: dict[tuple[str, str], int],
) -> int:
    n = 0
    for c in carregar_clubes():
        fm = str(c.get("id") or "").strip() or None
        if fm and fm in por_fm:
            continue
        _ensure_clube(
            conn,
            por_fm=por_fm,
            por_nome_uf=por_nome_uf,
            nome=str(c["nome"]),
            uf=str(c.get("uf") or ""),
            fm_id=fm,
        )
        n += 1
    return n


def _ensure_competicoes(conn: sqlite3.Connection) -> dict[str, int]:
    out: dict[str, int] = {}
    for spec in _COMPETICOES:
        row = conn.execute(
            "SELECT id FROM acervo_competicoes WHERE slug = ?",
            (spec["slug"],),
        ).fetchone()
        if row:
            out[spec["slug"]] = int(row["id"])
            continue
        cur = conn.execute(
            """
            INSERT INTO acervo_competicoes
              (slug, nome, ambito, uf, cobertura, notas)
            VALUES (?, ?, ?, '', ?, ?)
            """,
            (
                spec["slug"],
                spec["nome"],
                spec["ambito"],
                spec["cobertura"],
                "Importado dos CSVs históricos",
            ),
        )
        out[spec["slug"]] = int(cur.lastrowid)
    return out


def _upsert_edicao(
    conn: sqlite3.Connection,
    *,
    competicao_id: int,
    ano: int,
    campeao_id: int | None,
    vice_id: int | None,
    tem_tabela: bool,
    fonte_url: str = "",
) -> int:
    row = conn.execute(
        """
        SELECT id FROM acervo_edicoes
        WHERE competicao_id = ? AND ano = ?
        """,
        (competicao_id, ano),
    ).fetchone()
    if row:
        eid = int(row["id"])
        conn.execute(
            """
            UPDATE acervo_edicoes
            SET campeao_clube_id = COALESCE(?, campeao_clube_id),
                vice_clube_id = COALESCE(?, vice_clube_id),
                tem_tabela = CASE WHEN ? = 1 THEN 1 ELSE tem_tabela END,
                fonte_url = CASE
                  WHEN ? != '' AND (fonte_url IS NULL OR fonte_url = '')
                  THEN ? ELSE fonte_url END,
                atualizado_em = datetime('now', 'localtime')
            WHERE id = ?
            """,
            (
                campeao_id,
                vice_id,
                1 if tem_tabela else 0,
                fonte_url,
                fonte_url,
                eid,
            ),
        )
        return eid
    cur = conn.execute(
        """
        INSERT INTO acervo_edicoes
          (competicao_id, ano, campeao_clube_id, vice_clube_id,
           tem_tabela, fonte_url, notas)
        VALUES (?, ?, ?, ?, ?, ?, '')
        """,
        (
            competicao_id,
            ano,
            campeao_id,
            vice_id,
            1 if tem_tabela else 0,
            fonte_url or "",
        ),
    )
    return int(cur.lastrowid)


def _importar_classificacao_csv(
    conn: sqlite3.Connection,
    *,
    competicao_id: int,
    path: Path,
    por_fm: dict[str, int],
    por_nome_uf: dict[tuple[str, str], int],
) -> dict[str, int]:
    rows = _ler_csv(path)
    por_ano: dict[int, list[dict[str, str]]] = {}
    for r in rows:
        try:
            ano = int(str(r.get("ano") or "").strip())
        except ValueError:
            continue
        por_ano.setdefault(ano, []).append(r)

    edicoes = 0
    linhas = 0
    for ano, itens in sorted(por_ano.items()):
        itens_ord = sorted(itens, key=lambda x: _int_opt(x.get("posicao")) or 9999)
        camp_id = vice_id = None
        fonte = ""
        # Resolve once per row name to avoid double inserts with different casing.
        cache_nome: dict[str, int | None] = {}

        def cid_of(nome: str) -> int | None:
            k = nome.strip()
            if k not in cache_nome:
                cache_nome[k] = _resolver_ou_criar(
                    conn,
                    por_fm=por_fm,
                    por_nome_uf=por_nome_uf,
                    nome_wiki=k,
                )
            return cache_nome[k]

        for r in itens_ord:
            pos = _int_opt(r.get("posicao"))
            cid = cid_of(str(r.get("nome") or ""))
            if pos == 1:
                camp_id = cid
                fonte = (r.get("fonte_url") or "").strip()
            elif pos == 2:
                vice_id = cid

        eid = _upsert_edicao(
            conn,
            competicao_id=competicao_id,
            ano=ano,
            campeao_id=camp_id,
            vice_id=vice_id,
            tem_tabela=True,
            fonte_url=fonte if fonte.startswith("http") else "",
        )
        edicoes += 1
        conn.execute(
            "DELETE FROM acervo_edicao_classificacao WHERE edicao_id = ?",
            (eid,),
        )
        for r in itens_ord:
            pos = _int_opt(r.get("posicao"))
            if not pos:
                continue
            cid = cid_of(str(r.get("nome") or ""))
            if not cid:
                continue
            gp = _int_opt(r.get("gp"))
            gc = _int_opt(r.get("gc"))
            sg = _int_opt(r.get("sg"))
            if sg is None and gp is not None and gc is not None:
                sg = gp - gc
            # Anos com torneios paralelos (ex.: 1967) repetem posições no CSV —
            # mantém a 1ª ocorrência de cada posição/clube.
            try:
                conn.execute(
                    """
                    INSERT INTO acervo_edicao_classificacao
                      (edicao_id, clube_id, posicao, pts, j, v, e, d, gp, gc, sg)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        eid,
                        cid,
                        pos,
                        _int_opt(r.get("pts")),
                        _int_opt(r.get("j")),
                        _int_opt(r.get("v")),
                        _int_opt(r.get("e")),
                        _int_opt(r.get("d")),
                        gp,
                        gc,
                        sg,
                    ),
                )
            except sqlite3.IntegrityError:
                continue
            linhas += 1
        conn.execute(
            "UPDATE acervo_edicoes SET tem_tabela = 1 WHERE id = ?",
            (eid,),
        )
    return {"edicoes": edicoes, "linhas": linhas}


def _importar_copa(
    conn: sqlite3.Connection,
    *,
    competicao_id: int,
    por_fm: dict[str, int],
    por_nome_uf: dict[tuple[str, str], int],
) -> int:
    n = 0
    for r in _ler_csv(CAMPEOES_COPA_CSV):
        try:
            ano = int(str(r.get("ano") or "").strip())
        except ValueError:
            continue
        camp = _resolver_ou_criar(
            conn,
            por_fm=por_fm,
            por_nome_uf=por_nome_uf,
            nome_wiki=str(r.get("campeao") or ""),
        )
        vice = _resolver_ou_criar(
            conn,
            por_fm=por_fm,
            por_nome_uf=por_nome_uf,
            nome_wiki=str(r.get("vice") or ""),
        )
        _upsert_edicao(
            conn,
            competicao_id=competicao_id,
            ano=ano,
            campeao_id=camp,
            vice_id=vice,
            tem_tabela=False,
        )
        n += 1
    return n


def _importar_finais_c_faltantes(
    conn: sqlite3.Connection,
    *,
    competicao_id: int,
    por_fm: dict[str, int],
    por_nome_uf: dict[tuple[str, str], int],
) -> int:
    n = 0
    for r in _ler_csv(FINAIS_C_CSV):
        try:
            ano = int(str(r.get("ano") or "").strip())
        except ValueError:
            continue
        ja = conn.execute(
            """
            SELECT id, campeao_clube_id FROM acervo_edicoes
            WHERE competicao_id = ? AND ano = ?
            """,
            (competicao_id, ano),
        ).fetchone()
        if ja and ja["campeao_clube_id"]:
            continue
        camp = _resolver_ou_criar(
            conn,
            por_fm=por_fm,
            por_nome_uf=por_nome_uf,
            nome_wiki=str(r.get("campeao") or ""),
        )
        vice = _resolver_ou_criar(
            conn,
            por_fm=por_fm,
            por_nome_uf=por_nome_uf,
            nome_wiki=str(r.get("vice") or ""),
        )
        _upsert_edicao(
            conn,
            competicao_id=competicao_id,
            ano=ano,
            campeao_id=camp,
            vice_id=vice,
            tem_tabela=False,
        )
        n += 1
    return n


def importar_acervo_csvs(*, force: bool = False) -> dict[str, Any]:
    """Idempotente: na 1ª vez (ou com force) carrega CSVs → Acervo."""
    import src.db as db

    if not force and (db.get_meta(META_CHAVE) or "").strip() == "1":
        return {"ok": True, "skipped": True, "motivo": "já importado"}

    with db.get_db() as conn:
        if force:
            conn.execute("DELETE FROM acervo_edicao_classificacao")
            conn.execute("DELETE FROM acervo_edicoes")
            conn.execute("DELETE FROM acervo_competicoes")
            conn.execute("DELETE FROM acervo_clubes")

        por_fm: dict[str, int] = {}
        por_nome_uf: dict[tuple[str, str], int] = {}
        for r in conn.execute(
            "SELECT id, nome, uf, fm_unique_id FROM acervo_clubes"
        ).fetchall():
            cid = int(r["id"])
            fm = (r["fm_unique_id"] or "").strip()
            if fm:
                por_fm[fm] = cid
            por_nome_uf[(str(r["nome"]).casefold(), str(r["uf"] or "").upper())] = cid

        n_catalogo = _importar_catalogo_fm(
            conn, por_fm=por_fm, por_nome_uf=por_nome_uf
        )
        comps = _ensure_competicoes(conn)

        stats_series: dict[str, Any] = {}
        for slug in ("serie-a", "serie-b", "serie-c"):
            spec = next(s for s in _COMPETICOES if s["slug"] == slug)
            path = Path(spec["csv"]) if spec["csv"] else None
            if not path:
                continue
            stats_series[slug] = _importar_classificacao_csv(
                conn,
                competicao_id=comps[slug],
                path=path,
                por_fm=por_fm,
                por_nome_uf=por_nome_uf,
            )

        n_copa = _importar_copa(
            conn,
            competicao_id=comps["copa-do-brasil"],
            por_fm=por_fm,
            por_nome_uf=por_nome_uf,
        )
        n_finais_c = _importar_finais_c_faltantes(
            conn,
            competicao_id=comps["serie-c"],
            por_fm=por_fm,
            por_nome_uf=por_nome_uf,
        )

        clubes = conn.execute("SELECT COUNT(*) AS n FROM acervo_clubes").fetchone()
        competicoes = conn.execute(
            "SELECT COUNT(*) AS n FROM acervo_competicoes"
        ).fetchone()
        edicoes = conn.execute("SELECT COUNT(*) AS n FROM acervo_edicoes").fetchone()
        linhas = conn.execute(
            "SELECT COUNT(*) AS n FROM acervo_edicao_classificacao"
        ).fetchone()

    db.set_meta(META_CHAVE, "1")
    return {
        "ok": True,
        "skipped": False,
        "catalogo_novos": n_catalogo,
        "series": stats_series,
        "copa_edicoes": n_copa,
        "serie_c_finais_extra": n_finais_c,
        "totais": {
            "clubes": int(clubes["n"] if clubes else 0),
            "competicoes": int(competicoes["n"] if competicoes else 0),
            "edicoes": int(edicoes["n"] if edicoes else 0),
            "linhas_tabela": int(linhas["n"] if linhas else 0),
        },
        "raiz_csvs": str(ROOT_DIR / "data" / "torneios"),
    }


def garantir_acervo_importado() -> None:
    """Boot: importa CSVs uma vez; não derruba o app se falhar."""
    import os

    if (os.environ.get("ACERVO_SKIP_IMPORT") or "").strip() in ("1", "true", "yes"):
        return
    try:
        importar_acervo_csvs(force=False)
    except Exception:
        pass
