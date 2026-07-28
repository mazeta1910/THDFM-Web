from __future__ import annotations

import json
import secrets
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from src.config import COMPROVANTES_DIR, DATA_DIR, DB_PATH
from src.seed_data import OITAVAS


def _connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    COMPROVANTES_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def get_db() -> Iterator[sqlite3.Connection]:
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    chave TEXT PRIMARY KEY,
    valor TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS participantes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL UNIQUE,
    token TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'pendente'
        CHECK (status IN ('pendente', 'comprovante', 'liberado')),
    comprovante_path TEXT,
    comprovante_em TEXT,
    liberado_em TEXT,
    avatar_path TEXT
);

CREATE TABLE IF NOT EXISTS confrontos (
    id INTEGER PRIMARY KEY,
    fase TEXT NOT NULL,
    clube_a TEXT NOT NULL,
    clube_b TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jogos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    confronto_id INTEGER NOT NULL REFERENCES confrontos(id),
    perna TEXT NOT NULL CHECK (perna IN ('ida', 'volta', 'unico')),
    mandante_clube_id TEXT NOT NULL CHECK (mandante_clube_id IN ('a', 'b')),
    gols_mandante INTEGER,
    gols_visitante INTEGER,
    penaltis_clube_id TEXT CHECK (penaltis_clube_id IN ('a', 'b') OR penaltis_clube_id IS NULL),
    UNIQUE (confronto_id, perna)
);

CREATE TABLE IF NOT EXISTS palpites_jogo (
    participante_id INTEGER NOT NULL REFERENCES participantes(id),
    jogo_id INTEGER NOT NULL REFERENCES jogos(id),
    gols_mandante INTEGER NOT NULL,
    gols_visitante INTEGER NOT NULL,
    atualizado_em TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    PRIMARY KEY (participante_id, jogo_id)
);

CREATE TABLE IF NOT EXISTS palpites_penaltis (
    participante_id INTEGER NOT NULL REFERENCES participantes(id),
    confronto_id INTEGER NOT NULL REFERENCES confrontos(id),
    penaltis_clube_id TEXT NOT NULL CHECK (penaltis_clube_id IN ('a', 'b')),
    atualizado_em TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    PRIMARY KEY (participante_id, confronto_id)
);

CREATE TABLE IF NOT EXISTS snapshot (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    payload TEXT NOT NULL,
    atualizado_em TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
"""


def _migrate_participantes(conn: sqlite3.Connection) -> None:
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(participantes)").fetchall()}
    if "status" not in cols:
        conn.execute(
            "ALTER TABLE participantes ADD COLUMN status TEXT NOT NULL DEFAULT 'liberado'"
        )
    if "comprovante_path" not in cols:
        conn.execute("ALTER TABLE participantes ADD COLUMN comprovante_path TEXT")
    if "comprovante_em" not in cols:
        conn.execute("ALTER TABLE participantes ADD COLUMN comprovante_em TEXT")
    if "liberado_em" not in cols:
        conn.execute("ALTER TABLE participantes ADD COLUMN liberado_em TEXT")
    if "avatar_path" not in cols:
        conn.execute("ALTER TABLE participantes ADD COLUMN avatar_path TEXT")


def init_db() -> None:
    with get_db() as conn:
        conn.executescript(SCHEMA)
        _migrate_participantes(conn)
        row = conn.execute("SELECT valor FROM meta WHERE chave = 'janela'").fetchone()
        if not row:
            conn.execute(
                "INSERT INTO meta (chave, valor) VALUES ('janela', 'ida'), ('fase_atual', 'oitavas')"
            )
        if not conn.execute("SELECT 1 FROM confrontos LIMIT 1").fetchone():
            _seed_oitavas(conn)


def _seed_oitavas(conn: sqlite3.Connection) -> None:
    for item in OITAVAS:
        conn.execute(
            "INSERT INTO confrontos (id, fase, clube_a, clube_b) VALUES (?, 'oitavas', ?, ?)",
            (item["id"], item["clube_a"], item["clube_b"]),
        )
        conn.execute(
            "INSERT INTO jogos (confronto_id, perna, mandante_clube_id) VALUES (?, 'ida', 'a')",
            (item["id"],),
        )
        conn.execute(
            "INSERT INTO jogos (confronto_id, perna, mandante_clube_id) VALUES (?, 'volta', 'b')",
            (item["id"],),
        )


def get_meta(chave: str, default: str | None = None) -> str | None:
    with get_db() as conn:
        row = conn.execute("SELECT valor FROM meta WHERE chave = ?", (chave,)).fetchone()
        return row["valor"] if row else default


def set_meta(chave: str, valor: str) -> None:
    with get_db() as conn:
        conn.execute(
            "INSERT INTO meta (chave, valor) VALUES (?, ?) "
            "ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor",
            (chave, valor),
        )


def get_janela() -> str:
    return get_meta("janela", "ida") or "ida"


def set_janela(janela: str) -> None:
    if janela not in ("ida", "volta", "fechado"):
        raise ValueError("janela inválida")
    set_meta("janela", janela)


def list_participantes() -> list[dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, nome, token, status, comprovante_path, comprovante_em, liberado_em, avatar_path "
            "FROM participantes ORDER BY "
            "CASE status WHEN 'comprovante' THEN 0 WHEN 'pendente' THEN 1 ELSE 2 END, "
            "nome COLLATE NOCASE"
        ).fetchall()
        return [dict(r) for r in rows]


def criar_participante(nome: str, *, status: str = "pendente") -> dict[str, Any]:
    nome = nome.strip()
    if not nome:
        raise ValueError("Nome vazio")
    if status not in ("pendente", "comprovante", "liberado"):
        raise ValueError("status inválido")
    token = secrets.token_urlsafe(16)
    with get_db() as conn:
        liberado_em = "datetime('now', 'localtime')" if status == "liberado" else "NULL"
        # use parameter for liberado only via Python
        liberado_sql = None
        if status == "liberado":
            cur = conn.execute(
                "INSERT INTO participantes (nome, token, status, liberado_em) "
                "VALUES (?, ?, 'liberado', datetime('now', 'localtime'))",
                (nome, token),
            )
        else:
            cur = conn.execute(
                "INSERT INTO participantes (nome, token, status) VALUES (?, ?, ?)",
                (nome, token, status),
            )
        return {
            "id": cur.lastrowid,
            "nome": nome,
            "token": token,
            "status": status,
            "comprovante_path": None,
            "comprovante_em": None,
            "liberado_em": liberado_sql,
        }


def get_participante_por_token(token: str) -> dict[str, Any] | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT id, nome, token, status, comprovante_path, comprovante_em, liberado_em, avatar_path "
            "FROM participantes WHERE token = ?",
            (token,),
        ).fetchone()
        return dict(row) if row else None


def get_participante(participante_id: int) -> dict[str, Any] | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT id, nome, token, status, comprovante_path, comprovante_em, liberado_em, avatar_path "
            "FROM participantes WHERE id = ?",
            (participante_id,),
        ).fetchone()
        return dict(row) if row else None


def salvar_comprovante(participante_id: int, relative_path: str) -> None:
    with get_db() as conn:
        conn.execute(
            "UPDATE participantes SET status = 'comprovante', comprovante_path = ?, "
            "comprovante_em = datetime('now', 'localtime') WHERE id = ?",
            (relative_path, participante_id),
        )


def liberar_participante(participante_id: int) -> None:
    with get_db() as conn:
        conn.execute(
            "UPDATE participantes SET status = 'liberado', "
            "liberado_em = datetime('now', 'localtime') WHERE id = ?",
            (participante_id,),
        )


def atualizar_nome_participante(participante_id: int, nome: str) -> None:
    nome = nome.strip()
    if not nome:
        raise ValueError("Nome vazio")
    with get_db() as conn:
        conn.execute(
            "UPDATE participantes SET nome = ? WHERE id = ?",
            (nome, participante_id),
        )


def salvar_avatar(participante_id: int, relative_path: str | None) -> None:
    with get_db() as conn:
        conn.execute(
            "UPDATE participantes SET avatar_path = ? WHERE id = ?",
            (relative_path, participante_id),
        )


def recusar_comprovante(participante_id: int) -> str | None:
    """Volta a pendente e devolve path antigo para apagar arquivo."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT comprovante_path FROM participantes WHERE id = ?",
            (participante_id,),
        ).fetchone()
        path = row["comprovante_path"] if row else None
        conn.execute(
            "UPDATE participantes SET status = 'pendente', comprovante_path = NULL, "
            "comprovante_em = NULL WHERE id = ?",
            (participante_id,),
        )
        return path


def regenerar_token(participante_id: int) -> str:
    token = secrets.token_urlsafe(16)
    with get_db() as conn:
        conn.execute(
            "UPDATE participantes SET token = ? WHERE id = ?",
            (token, participante_id),
        )
    return token


def list_confrontos_completos() -> list[dict[str, Any]]:
    with get_db() as conn:
        confrontos = conn.execute(
            "SELECT * FROM confrontos ORDER BY id"
        ).fetchall()
        out: list[dict[str, Any]] = []
        for c in confrontos:
            jogos = conn.execute(
                "SELECT * FROM jogos WHERE confronto_id = ? ORDER BY CASE perna "
                "WHEN 'ida' THEN 1 WHEN 'volta' THEN 2 ELSE 3 END",
                (c["id"],),
            ).fetchall()
            item = dict(c)
            item["jogos"] = [dict(j) for j in jogos]
            out.append(item)
        return out


def get_jogo(jogo_id: int) -> dict[str, Any] | None:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM jogos WHERE id = ?", (jogo_id,)).fetchone()
        return dict(row) if row else None


def set_resultado_jogo(
    jogo_id: int,
    gols_mandante: int,
    gols_visitante: int,
    penaltis_clube_id: str | None = None,
) -> None:
    with get_db() as conn:
        conn.execute(
            "UPDATE jogos SET gols_mandante = ?, gols_visitante = ?, penaltis_clube_id = ? "
            "WHERE id = ?",
            (gols_mandante, gols_visitante, penaltis_clube_id, jogo_id),
        )


def set_penaltis_oficiais_confronto(confronto_id: int, penaltis_clube_id: str | None) -> None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT id FROM jogos WHERE confronto_id = ? AND perna IN ('volta', 'unico')",
            (confronto_id,),
        ).fetchone()
        if not row:
            raise ValueError("jogo de volta/unico não encontrado")
        conn.execute(
            "UPDATE jogos SET penaltis_clube_id = ? WHERE id = ?",
            (penaltis_clube_id, row["id"]),
        )


def salvar_palpite_jogo(
    participante_id: int,
    jogo_id: int,
    gols_mandante: int,
    gols_visitante: int,
) -> None:
    with get_db() as conn:
        conn.execute(
            "INSERT INTO palpites_jogo (participante_id, jogo_id, gols_mandante, gols_visitante) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(participante_id, jogo_id) DO UPDATE SET "
            "gols_mandante = excluded.gols_mandante, "
            "gols_visitante = excluded.gols_visitante, "
            "atualizado_em = datetime('now', 'localtime')",
            (participante_id, jogo_id, gols_mandante, gols_visitante),
        )


def salvar_palpite_penaltis(
    participante_id: int,
    confronto_id: int,
    penaltis_clube_id: str,
) -> None:
    if penaltis_clube_id not in ("a", "b"):
        raise ValueError("penaltis_clube_id inválido")
    with get_db() as conn:
        conn.execute(
            "INSERT INTO palpites_penaltis (participante_id, confronto_id, penaltis_clube_id) "
            "VALUES (?, ?, ?) "
            "ON CONFLICT(participante_id, confronto_id) DO UPDATE SET "
            "penaltis_clube_id = excluded.penaltis_clube_id, "
            "atualizado_em = datetime('now', 'localtime')",
            (participante_id, confronto_id, penaltis_clube_id),
        )


def limpar_palpite_penaltis(participante_id: int, confronto_id: int) -> None:
    with get_db() as conn:
        conn.execute(
            "DELETE FROM palpites_penaltis WHERE participante_id = ? AND confronto_id = ?",
            (participante_id, confronto_id),
        )


def palpites_do_participante(participante_id: int) -> dict[str, Any]:
    with get_db() as conn:
        jogos = conn.execute(
            "SELECT * FROM palpites_jogo WHERE participante_id = ?",
            (participante_id,),
        ).fetchall()
        pens = conn.execute(
            "SELECT * FROM palpites_penaltis WHERE participante_id = ?",
            (participante_id,),
        ).fetchall()
        return {
            "jogos": {r["jogo_id"]: dict(r) for r in jogos},
            "penaltis": {r["confronto_id"]: dict(r) for r in pens},
        }


def save_snapshot(payload: dict[str, Any]) -> None:
    with get_db() as conn:
        conn.execute(
            "INSERT INTO snapshot (id, payload, atualizado_em) VALUES (1, ?, datetime('now', 'localtime')) "
            "ON CONFLICT(id) DO UPDATE SET payload = excluded.payload, "
            "atualizado_em = datetime('now', 'localtime')",
            (json.dumps(payload, ensure_ascii=False),),
        )


def load_snapshot() -> dict[str, Any] | None:
    with get_db() as conn:
        row = conn.execute("SELECT payload FROM snapshot WHERE id = 1").fetchone()
        if not row:
            return None
        return json.loads(row["payload"])


def db_path() -> Path:
    return DB_PATH
