from __future__ import annotations

import json
import re
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
    avatar_path TEXT,
    celular TEXT
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

CREATE TABLE IF NOT EXISTS rodadas_historico (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    numero INTEGER NOT NULL UNIQUE,
    rotulo TEXT NOT NULL,
    fase TEXT NOT NULL,
    janela TEXT NOT NULL,
    criado_em TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    payload TEXT NOT NULL
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
    if "celular" not in cols:
        conn.execute("ALTER TABLE participantes ADD COLUMN celular TEXT")


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


def get_fase_atual() -> str:
    return get_meta("fase_atual", "oitavas") or "oitavas"


def set_fase_atual(fase: str) -> None:
    from src.config import FASE_IDS

    if fase not in FASE_IDS:
        raise ValueError("fase inválida")
    set_meta("fase_atual", fase)


def list_participantes() -> list[dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, nome, token, status, comprovante_path, comprovante_em, liberado_em, avatar_path, celular "
            "FROM participantes ORDER BY "
            "CASE status WHEN 'comprovante' THEN 0 WHEN 'pendente' THEN 1 ELSE 2 END, "
            "nome COLLATE NOCASE"
        ).fetchall()
        return [dict(r) for r in rows]


def criar_participante(
    nome: str, *, status: str = "pendente", celular: str | None = None
) -> dict[str, Any]:
    nome = nome.strip()
    if not nome:
        raise ValueError("Nome vazio")
    if status not in ("pendente", "comprovante", "liberado"):
        raise ValueError("status inválido")
    celular_limpo = normalizar_celular(celular) if celular else None
    token = secrets.token_urlsafe(16)
    with get_db() as conn:
        liberado_sql = None
        if status == "liberado":
            cur = conn.execute(
                "INSERT INTO participantes (nome, token, status, liberado_em, celular) "
                "VALUES (?, ?, 'liberado', datetime('now', 'localtime'), ?)",
                (nome, token, celular_limpo),
            )
            liberado_sql = True
        else:
            cur = conn.execute(
                "INSERT INTO participantes (nome, token, status, celular) VALUES (?, ?, ?, ?)",
                (nome, token, status, celular_limpo),
            )
        return {
            "id": cur.lastrowid,
            "nome": nome,
            "token": token,
            "status": status,
            "comprovante_path": None,
            "comprovante_em": None,
            "liberado_em": liberado_sql,
            "celular": celular_limpo,
        }


def normalizar_celular(celular: str) -> str:
    digits = re.sub(r"\D+", "", celular or "")
    if len(digits) < 10 or len(digits) > 13:
        raise ValueError("Celular inválido")
    return digits


def get_participante_por_token(token: str) -> dict[str, Any] | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT id, nome, token, status, comprovante_path, comprovante_em, liberado_em, avatar_path, celular "
            "FROM participantes WHERE token = ?",
            (token,),
        ).fetchone()
        return dict(row) if row else None


def get_participante(participante_id: int) -> dict[str, Any] | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT id, nome, token, status, comprovante_path, comprovante_em, liberado_em, avatar_path, celular "
            "FROM participantes WHERE id = ?",
            (participante_id,),
        ).fetchone()
        return dict(row) if row else None


def get_participante_por_nome(nome: str) -> dict[str, Any] | None:
    nome = (nome or "").strip()
    if not nome:
        return None
    with get_db() as conn:
        row = conn.execute(
            "SELECT id, nome, token, status, comprovante_path, comprovante_em, liberado_em, avatar_path, celular "
            "FROM participantes WHERE nome = ? COLLATE NOCASE",
            (nome,),
        ).fetchone()
        return dict(row) if row else None


def garantir_participante_liberado(nome: str) -> dict[str, Any]:
    """Garante um participante liberado com esse nome (ex.: admin que também palpita)."""
    part = get_participante_por_nome(nome)
    if part:
        if part.get("status") != "liberado":
            liberar_participante(part["id"])
            part = get_participante(part["id"]) or part
            part["status"] = "liberado"
        return part
    return criar_participante(nome, status="liberado")


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


def apagar_participante(participante_id: int) -> dict[str, Any] | None:
    """Remove participante, palpites e devolve paths de arquivos para limpeza."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT id, nome, comprovante_path, avatar_path FROM participantes WHERE id = ?",
            (participante_id,),
        ).fetchone()
        if not row:
            return None
        part = dict(row)
        conn.execute(
            "DELETE FROM palpites_jogo WHERE participante_id = ?", (participante_id,)
        )
        conn.execute(
            "DELETE FROM palpites_penaltis WHERE participante_id = ?",
            (participante_id,),
        )
        conn.execute("DELETE FROM participantes WHERE id = ?", (participante_id,))
        return part


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


def list_confrontos_completos(fase: str | None = None) -> list[dict[str, Any]]:
    with get_db() as conn:
        if fase:
            confrontos = conn.execute(
                "SELECT * FROM confrontos WHERE fase = ? ORDER BY id", (fase,)
            ).fetchall()
        else:
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


def limpar_resultados_oficiais(*, fase: str, perna: str) -> int:
    """Zera placares oficiais da fase+perna. Retorna quantos jogos foram afetados."""
    if perna not in ("ida", "volta", "unico"):
        raise ValueError("perna inválida")
    with get_db() as conn:
        rows = conn.execute(
            "SELECT j.id FROM jogos j "
            "JOIN confrontos c ON c.id = j.confronto_id "
            "WHERE c.fase = ? AND j.perna = ? "
            "AND (j.gols_mandante IS NOT NULL OR j.gols_visitante IS NOT NULL "
            "OR j.penaltis_clube_id IS NOT NULL)",
            (fase, perna),
        ).fetchall()
        n = len(rows)
        conn.execute(
            "UPDATE jogos SET gols_mandante = NULL, gols_visitante = NULL, "
            "penaltis_clube_id = NULL "
            "WHERE id IN ("
            "  SELECT j.id FROM jogos j "
            "  JOIN confrontos c ON c.id = j.confronto_id "
            "  WHERE c.fase = ? AND j.perna = ?"
            ")",
            (fase, perna),
        )
        return n


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


def append_rodada_historico(
    *,
    linhas: list[dict[str, Any]],
    fase: str,
    janela: str,
) -> dict[str, Any]:
    with get_db() as conn:
        row = conn.execute(
            "SELECT COALESCE(MAX(numero), 0) AS n FROM rodadas_historico"
        ).fetchone()
        numero = int(row["n"]) + 1
        rotulo = f"Rodada {numero}"
        payload = json.dumps({"linhas": linhas}, ensure_ascii=False)
        cur = conn.execute(
            "INSERT INTO rodadas_historico (numero, rotulo, fase, janela, payload) "
            "VALUES (?, ?, ?, ?, ?)",
            (numero, rotulo, fase, janela, payload),
        )
        rid = int(cur.lastrowid)
        criado = conn.execute(
            "SELECT criado_em FROM rodadas_historico WHERE id = ?", (rid,)
        ).fetchone()["criado_em"]
        return {
            "id": rid,
            "numero": numero,
            "rotulo": rotulo,
            "fase": fase,
            "janela": janela,
            "criado_em": criado,
        }


def list_rodadas_historico() -> list[dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, numero, rotulo, fase, janela, criado_em "
            "FROM rodadas_historico ORDER BY numero ASC"
        ).fetchall()
        return [dict(r) for r in rows]


def get_rodada_historico(rodada_id: int) -> dict[str, Any] | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT id, numero, rotulo, fase, janela, criado_em, payload "
            "FROM rodadas_historico WHERE id = ?",
            (rodada_id,),
        ).fetchone()
        if not row:
            return None
        data = dict(row)
        payload = json.loads(data.pop("payload"))
        data["linhas"] = payload.get("linhas") or []
        return data


def db_path() -> Path:
    return DB_PATH
