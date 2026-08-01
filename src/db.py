from __future__ import annotations

import json
import re
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

import bcrypt

from src.config import COMPROVANTES_DIR, DATA_DIR, DB_PATH, NOME_MAX_LEN
from src.seed_data import OITAVAS

USERNAME_RE = re.compile(r"^[a-zA-Z0-9._-]{3,24}$")
SENHA_MIN_LEN = 8


def normalizar_nome_exibido(nome: str) -> str:
    """Valida e normaliza o nome exibido (máx. NOME_MAX_LEN caracteres)."""
    nome = re.sub(r"\s+", " ", (nome or "").strip())
    if not nome:
        raise ValueError("Nome vazio")
    if len(nome) > NOME_MAX_LEN:
        raise ValueError(f"Nome com no máximo {NOME_MAX_LEN} caracteres")
    return nome


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
    celular TEXT,
    criado_em TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    link_enviado_em TEXT,
    recusado_em TEXT
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
    inicio_em TEXT,
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
    if "criado_em" not in cols:
        conn.execute("ALTER TABLE participantes ADD COLUMN criado_em TEXT")
        conn.execute(
            "UPDATE participantes SET criado_em = COALESCE(comprovante_em, liberado_em, "
            "datetime('now', 'localtime')) WHERE criado_em IS NULL"
        )
    if "link_enviado_em" not in cols:
        conn.execute("ALTER TABLE participantes ADD COLUMN link_enviado_em TEXT")
        # Liberados existentes já tinham recebido o link na prática.
        conn.execute(
            "UPDATE participantes SET link_enviado_em = COALESCE("
            "liberado_em, datetime('now', 'localtime')) "
            "WHERE status = 'liberado'"
        )
    else:
        # Uma vez: se todos os liberados ainda estão sem marca, preenche (setup atual).
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM participantes WHERE status = 'liberado'"
        ).fetchone()
        sem = conn.execute(
            "SELECT COUNT(*) AS n FROM participantes WHERE status = 'liberado' "
            "AND (link_enviado_em IS NULL OR link_enviado_em = '')"
        ).fetchone()
        total = int(row["n"] or 0) if row else 0
        sem_n = int(sem["n"] or 0) if sem else 0
        if total > 0 and sem_n == total:
            conn.execute(
                "UPDATE participantes SET link_enviado_em = COALESCE("
                "liberado_em, datetime('now', 'localtime')) "
                "WHERE status = 'liberado'"
            )
    if "recusado_em" not in cols:
        conn.execute("ALTER TABLE participantes ADD COLUMN recusado_em TEXT")
    if "admin_login" not in cols:
        conn.execute("ALTER TABLE participantes ADD COLUMN admin_login TEXT")
    if "username" not in cols:
        conn.execute("ALTER TABLE participantes ADD COLUMN username TEXT")
    if "password_hash" not in cols:
        conn.execute("ALTER TABLE participantes ADD COLUMN password_hash TEXT")
    if "credenciais_em" not in cols:
        conn.execute("ALTER TABLE participantes ADD COLUMN credenciais_em TEXT")
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_participantes_admin_login "
        "ON participantes(admin_login) WHERE admin_login IS NOT NULL AND admin_login != ''"
    )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_participantes_username_lower "
        "ON participantes(lower(username)) "
        "WHERE username IS NOT NULL AND username != ''"
    )


def _migrate_jogos(conn: sqlite3.Connection) -> None:
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(jogos)").fetchall()}
    if "inicio_em" not in cols:
        conn.execute("ALTER TABLE jogos ADD COLUMN inicio_em TEXT")
    for item in OITAVAS:
        inicio = item.get("ida_em")
        if not inicio:
            continue
        conn.execute(
            "UPDATE jogos SET inicio_em = ? "
            "WHERE confronto_id = ? AND perna = 'ida' "
            "AND (inicio_em IS NULL OR inicio_em = '')",
            (inicio, item["id"]),
        )


def _migrate_recuperacao(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS recuperacao_pedidos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            participante_id INTEGER NOT NULL REFERENCES participantes(id) ON DELETE CASCADE,
            celular TEXT NOT NULL,
            criado_em TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
            atendido_em TEXT,
            ip TEXT
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_recuperacao_pendentes "
        "ON recuperacao_pedidos(atendido_em, criado_em)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_recuperacao_celular_criado "
        "ON recuperacao_pedidos(celular, criado_em)"
    )


def _migrate_xonhometro(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS xonha_eventos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo TEXT NOT NULL CHECK (tipo IN ('saida', 'volta', 'banimento')),
            data TEXT NOT NULL,
            hora TEXT,
            motivo TEXT,
            criado_em TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        )
        """
    )
    cols = {
        row[1] for row in conn.execute("PRAGMA table_info(xonha_eventos)").fetchall()
    }
    if "hora" not in cols:
        conn.execute("ALTER TABLE xonha_eventos ADD COLUMN hora TEXT")

    # Bancos antigos: CHECK só tinha saida/volta — reconstrói a tabela.
    ddl = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='xonha_eventos'"
    ).fetchone()
    ddl_sql = (ddl[0] if ddl else "") or ""
    if "banimento" not in ddl_sql:
        conn.executescript(
            """
            CREATE TABLE xonha_eventos__new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tipo TEXT NOT NULL CHECK (tipo IN ('saida', 'volta', 'banimento')),
                data TEXT NOT NULL,
                hora TEXT,
                motivo TEXT,
                criado_em TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            );
            INSERT INTO xonha_eventos__new (id, tipo, data, hora, motivo, criado_em)
            SELECT id, tipo, data, hora, motivo, criado_em FROM xonha_eventos;
            DROP TABLE xonha_eventos;
            ALTER TABLE xonha_eventos__new RENAME TO xonha_eventos;
            """
        )

    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_xonha_eventos_data "
        "ON xonha_eventos(data DESC, id DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_xonha_eventos_tipo_data "
        "ON xonha_eventos(tipo, data)"
    )


def init_db() -> None:
    with get_db() as conn:
        conn.executescript(SCHEMA)
        _migrate_participantes(conn)
        _migrate_jogos(conn)
        _migrar_celulares_br(conn)
        _migrate_recuperacao(conn)
        _migrate_xonhometro(conn)
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
            "INSERT INTO jogos (confronto_id, perna, mandante_clube_id, inicio_em) "
            "VALUES (?, 'ida', 'a', ?)",
            (item["id"], item.get("ida_em")),
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


_PARTICIPANTE_COLS = (
    "id, nome, token, status, comprovante_path, comprovante_em, liberado_em, "
    "avatar_path, celular, criado_em, link_enviado_em, recusado_em, admin_login, "
    "username, password_hash, credenciais_em"
)


def list_participantes() -> list[dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute(
            f"SELECT {_PARTICIPANTE_COLS} FROM participantes ORDER BY "
            "CASE "
            "WHEN admin_login IS NOT NULL AND admin_login != '' THEN 0 "
            "ELSE 1 END, "
            "CASE "
            "WHEN status = 'liberado' THEN 3 "
            "WHEN recusado_em IS NOT NULL AND recusado_em != '' THEN 2 "
            "WHEN status = 'comprovante' THEN 0 "
            "ELSE 1 END, "
            "nome COLLATE NOCASE"
        ).fetchall()
        return [dict(r) for r in rows]


def criar_participante(
    nome: str,
    *,
    status: str = "pendente",
    celular: str | None = None,
    admin_login: str | None = None,
) -> dict[str, Any]:
    nome = normalizar_nome_exibido(nome)
    if status not in ("pendente", "comprovante", "liberado"):
        raise ValueError("status inválido")
    celular_limpo = normalizar_celular(celular) if celular else None
    login = (admin_login or "").strip().lower() or None
    token = secrets.token_urlsafe(16)
    with get_db() as conn:
        if status == "liberado":
            cur = conn.execute(
                "INSERT INTO participantes "
                "(nome, token, status, liberado_em, celular, criado_em, admin_login) "
                "VALUES (?, ?, 'liberado', datetime('now', 'localtime'), ?, "
                "datetime('now', 'localtime'), ?)",
                (nome, token, celular_limpo, login),
            )
        else:
            cur = conn.execute(
                "INSERT INTO participantes "
                "(nome, token, status, celular, criado_em, admin_login) "
                "VALUES (?, ?, ?, ?, datetime('now', 'localtime'), ?)",
                (nome, token, status, celular_limpo, login),
            )
        return {
            "id": cur.lastrowid,
            "nome": nome,
            "token": token,
            "status": status,
            "comprovante_path": None,
            "comprovante_em": None,
            "liberado_em": status == "liberado",
            "celular": celular_limpo,
            "criado_em": None,
            "admin_login": login,
        }


def normalizar_celular(celular: str) -> str:
    """Retorna só dígitos no formato internacional BR (55 + DDD + número).

    Números com 10/11 dígitos (DDD local) ganham o 55.
    Não confundir DDD 55 (RS) com código do país: só trata como
    internacional se já tiver 12 ou 13 dígitos começando com 55.
    """
    digits = re.sub(r"\D+", "", celular or "")
    if digits.startswith("55") and len(digits) in (12, 13):
        return digits
    if len(digits) in (10, 11):
        return "55" + digits
    raise ValueError("Celular inválido")


def celular_whatsapp(celular: str | None) -> str | None:
    """Dígitos para wa.me (com 55). Aceita dados antigos sem país."""
    if not celular:
        return None
    try:
        return normalizar_celular(celular)
    except ValueError:
        digits = re.sub(r"\D+", "", celular)
        return digits or None


def formatar_celular(celular: str | None) -> str:
    """Exibição: +55 (11) 99999-9999."""
    digits = celular_whatsapp(celular)
    if not digits:
        return ""
    local = digits[2:] if digits.startswith("55") and len(digits) >= 12 else digits
    if len(local) == 11:
        return f"+55 ({local[:2]}) {local[2:7]}-{local[7:]}"
    if len(local) == 10:
        return f"+55 ({local[:2]}) {local[2:6]}-{local[6:]}"
    return f"+{digits}" if not digits.startswith("+") else digits


def mensagem_whatsapp_link(nome: str, base_url: str, token: str) -> str:
    link = f"{base_url.rstrip('/')}/p/{token}"
    primeiro = (nome or "").strip().split()[0] if (nome or "").strip() else ""
    oi = f"Oi, {primeiro}!" if primeiro else "Oi!"
    return (
        f"{oi} Esse é o seu link único do Bolão THDFM (Copa do Brasil):\n\n"
        f"{link}\n\n"
        "Guarda esse link — é pessoal e intransferível. "
        "Por ele você faz os palpites e acompanha sua conta."
    )


def _migrar_celulares_br(conn: sqlite3.Connection) -> None:
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(participantes)").fetchall()}
    if "celular" not in cols:
        return
    rows = conn.execute(
        "SELECT id, celular FROM participantes WHERE celular IS NOT NULL AND celular != ''"
    ).fetchall()
    for row in rows:
        try:
            novo = normalizar_celular(row["celular"])
        except ValueError:
            continue
        if novo != row["celular"]:
            conn.execute(
                "UPDATE participantes SET celular = ? WHERE id = ?",
                (novo, row["id"]),
            )


def get_participante_por_token(token: str) -> dict[str, Any] | None:
    with get_db() as conn:
        row = conn.execute(
            f"SELECT {_PARTICIPANTE_COLS} FROM participantes WHERE token = ?",
            (token,),
        ).fetchone()
        return dict(row) if row else None


def get_participante(participante_id: int) -> dict[str, Any] | None:
    with get_db() as conn:
        row = conn.execute(
            f"SELECT {_PARTICIPANTE_COLS} FROM participantes WHERE id = ?",
            (participante_id,),
        ).fetchone()
        return dict(row) if row else None


def get_participante_por_nome(nome: str) -> dict[str, Any] | None:
    nome = (nome or "").strip()
    if not nome:
        return None
    with get_db() as conn:
        row = conn.execute(
            f"SELECT {_PARTICIPANTE_COLS} FROM participantes WHERE nome = ? COLLATE NOCASE",
            (nome,),
        ).fetchone()
        return dict(row) if row else None


def get_participante_por_admin_login(login: str) -> dict[str, Any] | None:
    login = (login or "").strip().lower()
    if not login:
        return None
    with get_db() as conn:
        row = conn.execute(
            f"SELECT {_PARTICIPANTE_COLS} FROM participantes WHERE admin_login = ?",
            (login,),
        ).fetchone()
        return dict(row) if row else None


def normalizar_username(username: str) -> str:
    u = (username or "").strip()
    if not USERNAME_RE.fullmatch(u):
        raise ValueError(
            "Username inválido: use 3–24 caracteres (letras, números, . _ -)"
        )
    return u


def hash_senha(senha: str) -> str:
    return bcrypt.hashpw(senha.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verificar_senha(senha: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(
            senha.encode("utf-8"),
            password_hash.encode("ascii"),
        )
    except (ValueError, TypeError):
        return False


def validar_senha_nova(senha: str) -> str:
    senha = senha or ""
    if len(senha) < SENHA_MIN_LEN:
        raise ValueError(f"Senha deve ter no mínimo {SENHA_MIN_LEN} caracteres")
    if len(senha.encode("utf-8")) > 72:
        raise ValueError("Senha muito longa")
    return senha


def precisa_credenciais(part: dict[str, Any] | None) -> bool:
    if not part:
        return False
    if part.get("status") != "liberado":
        return False
    return not bool(part.get("password_hash"))


def get_participante_por_username(username: str) -> dict[str, Any] | None:
    try:
        u = normalizar_username(username)
    except ValueError:
        u = (username or "").strip()
        if not u:
            return None
    with get_db() as conn:
        row = conn.execute(
            f"SELECT {_PARTICIPANTE_COLS} FROM participantes "
            "WHERE lower(username) = lower(?)",
            (u,),
        ).fetchone()
        return dict(row) if row else None


def username_disponivel(username: str, *, exceto_id: int | None = None) -> bool:
    u = normalizar_username(username)
    with get_db() as conn:
        if exceto_id is not None:
            row = conn.execute(
                "SELECT id FROM participantes "
                "WHERE lower(username) = lower(?) AND id != ?",
                (u, exceto_id),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT id FROM participantes WHERE lower(username) = lower(?)",
                (u,),
            ).fetchone()
        return row is None


def definir_credenciais(
    participante_id: int, username: str, senha: str
) -> dict[str, Any]:
    """Primeiro cadastro de username+senha (só se ainda não houver hash)."""
    part = get_participante(participante_id)
    if not part:
        raise ValueError("Participante não encontrado")
    if part.get("status") != "liberado":
        raise ValueError("Inscrição ainda não liberada")
    if part.get("password_hash"):
        raise ValueError("Credenciais já definidas")

    u = normalizar_username(username)
    senha_ok = validar_senha_nova(senha)
    if not username_disponivel(u, exceto_id=participante_id):
        raise ValueError("Username já está em uso")

    ph = hash_senha(senha_ok)
    with get_db() as conn:
        conn.execute(
            "UPDATE participantes SET username = ?, password_hash = ?, "
            "credenciais_em = datetime('now', 'localtime') WHERE id = ?",
            (u, ph, participante_id),
        )
    updated = get_participante(participante_id)
    if not updated:
        raise ValueError("Falha ao gravar credenciais")
    return updated


def autenticar_por_username(username: str, senha: str) -> dict[str, Any] | None:
    part = get_participante_por_username(username)
    if not part or part.get("status") != "liberado":
        return None
    if not verificar_senha(senha, part.get("password_hash")):
        return None
    return part


def alterar_senha(
    participante_id: int, senha_atual: str, senha_nova: str
) -> None:
    part = get_participante(participante_id)
    if not part or not part.get("password_hash"):
        raise ValueError("Credenciais ainda não definidas")
    if not verificar_senha(senha_atual, part.get("password_hash")):
        raise ValueError("Senha atual incorreta")
    senha_ok = validar_senha_nova(senha_nova)
    ph = hash_senha(senha_ok)
    with get_db() as conn:
        conn.execute(
            "UPDATE participantes SET password_hash = ?, "
            "credenciais_em = datetime('now', 'localtime') WHERE id = ?",
            (ph, participante_id),
        )


def admin_redefinir_credenciais(
    participante_id: int,
    *,
    senha_nova: str,
    username: str | None = None,
) -> dict[str, Any]:
    """Dono redefine senha (e opcionalmente username). Não devolve a senha em claro."""
    part = get_participante(participante_id)
    if not part:
        raise ValueError("Participante não encontrado")
    if part.get("status") != "liberado":
        raise ValueError("Só dá para redefinir conta liberada")

    senha_ok = validar_senha_nova(senha_nova)
    ph = hash_senha(senha_ok)

    u = None
    if username is not None and str(username).strip():
        u = normalizar_username(username)
        if not username_disponivel(u, exceto_id=participante_id):
            raise ValueError("Username já está em uso")

    with get_db() as conn:
        if u is not None:
            conn.execute(
                "UPDATE participantes SET username = ?, password_hash = ?, "
                "credenciais_em = datetime('now', 'localtime') WHERE id = ?",
                (u, ph, participante_id),
            )
        else:
            conn.execute(
                "UPDATE participantes SET password_hash = ?, "
                "credenciais_em = datetime('now', 'localtime') WHERE id = ?",
                (ph, participante_id),
            )
    updated = get_participante(participante_id)
    if not updated:
        raise ValueError("Falha ao redefinir credenciais")
    return updated


def vincular_admin_login(participante_id: int, login: str) -> None:
    login = (login or "").strip().lower()
    if not login:
        raise ValueError("login vazio")
    with get_db() as conn:
        outro = conn.execute(
            "SELECT id FROM participantes WHERE admin_login = ? AND id != ?",
            (login, participante_id),
        ).fetchone()
        if outro:
            conn.execute(
                "UPDATE participantes SET admin_login = NULL WHERE id = ?",
                (outro["id"],),
            )
        conn.execute(
            "UPDATE participantes SET admin_login = ? WHERE id = ?",
            (login, participante_id),
        )


def _garantir_liberado(part: dict[str, Any]) -> dict[str, Any]:
    if part.get("status") != "liberado":
        liberar_participante(part["id"])
        part = get_participante(part["id"]) or part
        part["status"] = "liberado"
    return part


def garantir_participante_liberado(nome: str) -> dict[str, Any]:
    """Compat: garante participante liberado só pelo nome (sem vínculo de admin)."""
    part = get_participante_por_nome(nome)
    if part:
        return _garantir_liberado(part)
    return criar_participante(nome, status="liberado")


def garantir_participante_admin(
    login: str,
    nome: str,
    *,
    token_preferido: str | None = None,
) -> dict[str, Any]:
    """Garante o participante do admin pelo login (estável), não pelo nick.

    Assim renomear Mazeta → Mazetinha não cria outro usuário.
    """
    login = (login or "").strip().lower()
    nome = (nome or "").strip() or login
    if not login:
        raise ValueError("login de admin vazio")

    part = get_participante_por_admin_login(login)
    if part:
        return _garantir_liberado(part)

    if token_preferido:
        part = get_participante_por_token(token_preferido)
        if part:
            atual = (part.get("admin_login") or "").strip().lower()
            # Só reutiliza a sessão atual se ela JÁ for deste admin.
            # Não "assalta" o participante de outro usuário logado no mesmo browser.
            if atual == login:
                return _garantir_liberado(part)

    part = get_participante_por_nome(nome)
    if part:
        atual = (part.get("admin_login") or "").strip().lower()
        if not atual or atual == login:
            vincular_admin_login(part["id"], login)
            part = get_participante(part["id"]) or part
            return _garantir_liberado(part)

    return criar_participante(nome, status="liberado", admin_login=login)


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
            "liberado_em = datetime('now', 'localtime'), recusado_em = NULL "
            "WHERE id = ?",
            (participante_id,),
        )


def marcar_link_enviado(participante_id: int, *, enviado: bool = True) -> None:
    with get_db() as conn:
        if enviado:
            conn.execute(
                "UPDATE participantes SET link_enviado_em = datetime('now', 'localtime') "
                "WHERE id = ? AND status = 'liberado'",
                (participante_id,),
            )
        else:
            conn.execute(
                "UPDATE participantes SET link_enviado_em = NULL WHERE id = ?",
                (participante_id,),
            )


def recusar_participante(participante_id: int) -> bool:
    """Marca inscrição como recusada (não apaga). Retorna False se liberado/inexistente."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT status FROM participantes WHERE id = ?", (participante_id,)
        ).fetchone()
        if not row or row["status"] == "liberado":
            return False
        conn.execute(
            "UPDATE participantes SET recusado_em = datetime('now', 'localtime') "
            "WHERE id = ?",
            (participante_id,),
        )
        return True


def reabrir_participante(participante_id: int) -> bool:
    """Tira da lista de recusados (volta para liberação pendente)."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT status FROM participantes WHERE id = ?", (participante_id,)
        ).fetchone()
        if not row or row["status"] == "liberado":
            return False
        conn.execute(
            "UPDATE participantes SET recusado_em = NULL WHERE id = ?",
            (participante_id,),
        )
        return True


def recusar_todos_pendentes() -> int:
    """Marca todos os não liberados ainda não recusados. Retorna quantos."""
    with get_db() as conn:
        cur = conn.execute(
            "UPDATE participantes SET recusado_em = datetime('now', 'localtime') "
            "WHERE status != 'liberado' "
            "AND (recusado_em IS NULL OR recusado_em = '')"
        )
        return cur.rowcount


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
    nome = normalizar_nome_exibido(nome)
    with get_db() as conn:
        conn.execute(
            "UPDATE participantes SET nome = ? WHERE id = ?",
            (nome, participante_id),
        )


def atualizar_celular_participante(
    participante_id: int, celular: str | None
) -> None:
    celular_limpo = None
    if celular and str(celular).strip():
        celular_limpo = normalizar_celular(celular)
    with get_db() as conn:
        conn.execute(
            "UPDATE participantes SET celular = ? WHERE id = ?",
            (celular_limpo, participante_id),
        )


def salvar_avatar(participante_id: int, relative_path: str | None) -> None:
    with get_db() as conn:
        conn.execute(
            "UPDATE participantes SET avatar_path = ? WHERE id = ?",
            (relative_path, participante_id),
        )


def apagar_pendentes() -> list[dict[str, Any]]:
    """Remove todos os não liberados. Devolve paths para limpeza de arquivos."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, nome, comprovante_path, avatar_path FROM participantes "
            "WHERE status != 'liberado'"
        ).fetchall()
        out = [dict(r) for r in rows]
        for part in out:
            pid = part["id"]
            conn.execute("DELETE FROM palpites_jogo WHERE participante_id = ?", (pid,))
            conn.execute(
                "DELETE FROM palpites_penaltis WHERE participante_id = ?", (pid,)
            )
            conn.execute("DELETE FROM participantes WHERE id = ?", (pid,))
        return out


def recusar_comprovante(participante_id: int) -> str | None:
    """Compat: remove comprovante e volta a pendente (preferir apagar inscrição)."""
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


def get_participante_liberado_por_celular(celular: str) -> dict[str, Any] | None:
    """Busca participante liberado pelo celular normalizado."""
    try:
        celular_ok = normalizar_celular(celular)
    except ValueError:
        return None
    with get_db() as conn:
        row = conn.execute(
            f"SELECT {_PARTICIPANTE_COLS} FROM participantes "
            "WHERE status = 'liberado' AND celular = ? "
            "ORDER BY id LIMIT 1",
            (celular_ok,),
        ).fetchone()
        return dict(row) if row else None


RECUPERACAO_RATE_LIMIT = 3
RECUPERACAO_RATE_WINDOW_MIN = 15


def contar_pedidos_recuperacao_recentes(
    *, celular: str | None = None, ip: str | None = None
) -> int:
    """Conta pedidos na janela de rate limit (por celular e/ou IP)."""
    mins = RECUPERACAO_RATE_WINDOW_MIN
    with get_db() as conn:
        if celular and ip:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM recuperacao_pedidos "
                "WHERE (celular = ? OR ip = ?) "
                "AND criado_em >= datetime('now', 'localtime', ?)",
                (celular, ip, f"-{mins} minutes"),
            ).fetchone()
        elif celular:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM recuperacao_pedidos "
                "WHERE celular = ? "
                "AND criado_em >= datetime('now', 'localtime', ?)",
                (celular, f"-{mins} minutes"),
            ).fetchone()
        elif ip:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM recuperacao_pedidos "
                "WHERE ip = ? "
                "AND criado_em >= datetime('now', 'localtime', ?)",
                (ip, f"-{mins} minutes"),
            ).fetchone()
        else:
            return 0
        return int(row["n"] or 0) if row else 0


def recuperacao_rate_limit_ok(*, celular: str | None, ip: str | None) -> bool:
    return (
        contar_pedidos_recuperacao_recentes(celular=celular, ip=ip)
        < RECUPERACAO_RATE_LIMIT
    )


def criar_pedido_recuperacao(
    participante_id: int, celular: str, *, ip: str | None = None
) -> int:
    celular_ok = normalizar_celular(celular)
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO recuperacao_pedidos (participante_id, celular, ip) "
            "VALUES (?, ?, ?)",
            (participante_id, celular_ok, (ip or "").strip() or None),
        )
        return int(cur.lastrowid)


def list_pedidos_recuperacao_pendentes() -> list[dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT r.id, r.participante_id, r.celular, r.criado_em, r.ip, "
            "p.nome, p.token, p.status "
            "FROM recuperacao_pedidos r "
            "JOIN participantes p ON p.id = r.participante_id "
            "WHERE r.atendido_em IS NULL OR r.atendido_em = '' "
            "ORDER BY r.criado_em ASC"
        ).fetchall()
        return [dict(r) for r in rows]


def contar_pedidos_recuperacao_pendentes() -> int:
    with get_db() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM recuperacao_pedidos "
            "WHERE atendido_em IS NULL OR atendido_em = ''"
        ).fetchone()
        return int(row["n"] or 0) if row else 0


def get_pedido_recuperacao(pedido_id: int) -> dict[str, Any] | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT r.id, r.participante_id, r.celular, r.criado_em, r.atendido_em, r.ip, "
            "p.nome, p.token, p.status "
            "FROM recuperacao_pedidos r "
            "JOIN participantes p ON p.id = r.participante_id "
            "WHERE r.id = ?",
            (pedido_id,),
        ).fetchone()
        return dict(row) if row else None


def marcar_pedido_recuperacao_atendido(pedido_id: int) -> None:
    with get_db() as conn:
        conn.execute(
            "UPDATE recuperacao_pedidos SET atendido_em = datetime('now', 'localtime') "
            "WHERE id = ?",
            (pedido_id,),
        )


def marcar_pedidos_recuperacao_atendidos_participante(participante_id: int) -> int:
    """Fecha todos os pedidos pendentes daquele participante. Retorna quantos."""
    with get_db() as conn:
        cur = conn.execute(
            "UPDATE recuperacao_pedidos SET atendido_em = datetime('now', 'localtime') "
            "WHERE participante_id = ? AND (atendido_em IS NULL OR atendido_em = '')",
            (participante_id,),
        )
        return cur.rowcount


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


def get_ultima_rodada_historico() -> dict[str, Any] | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT id, numero, rotulo, fase, janela, criado_em, payload "
            "FROM rodadas_historico ORDER BY numero DESC LIMIT 1"
        ).fetchone()
        if not row:
            return None
        data = dict(row)
        payload = json.loads(data.pop("payload"))
        data["linhas"] = payload.get("linhas") or []
        return data


def delete_rodada_historico(rodada_id: int) -> bool:
    with get_db() as conn:
        cur = conn.execute("DELETE FROM rodadas_historico WHERE id = ?", (rodada_id,))
        return cur.rowcount > 0


def clear_snapshot() -> None:
    with get_db() as conn:
        conn.execute("DELETE FROM snapshot WHERE id = 1")


def db_path() -> Path:
    return DB_PATH


# ——— Xonhômetro (saídas/voltas do Xonha no WhatsApp) ———

_XONHA_TIPOS = frozenset({"saida", "volta", "banimento"})
_XONHA_TIPOS_FORA = frozenset({"saida", "banimento"})
_XONHA_DIAS_SEMANA = (
    "segunda",
    "terça",
    "quarta",
    "quinta",
    "sexta",
    "sábado",
    "domingo",
)
_XONHA_MESES = (
    "",
    "janeiro",
    "fevereiro",
    "março",
    "abril",
    "maio",
    "junho",
    "julho",
    "agosto",
    "setembro",
    "outubro",
    "novembro",
    "dezembro",
)


def _validar_data_xonha(data: str) -> str:
    raw = (data or "").strip()
    if not raw:
        raise ValueError("Informe a data.")
    try:
        datetime.strptime(raw[:10], "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError("Data inválida. Use AAAA-MM-DD.") from exc
    return raw[:10]


def _validar_hora_xonha(hora: str | None) -> str | None:
    raw = (hora or "").strip()
    if not raw:
        return None
    # Aceita HH:MM ou HH:MM:SS
    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            t = datetime.strptime(raw[:8] if fmt == "%H:%M:%S" else raw[:5], fmt)
            return t.strftime("%H:%M")
        except ValueError:
            continue
    raise ValueError("Horário inválido. Use HH:MM.")


def _xonha_sort_key(e: dict[str, Any]) -> tuple:
    return (e.get("data") or "", e.get("hora") or "", e.get("id") or 0)


def list_xonha_eventos() -> list[dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, tipo, data, hora, motivo, criado_em "
            "FROM xonha_eventos "
            "ORDER BY data DESC, COALESCE(hora, '') DESC, id DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def get_xonha_evento(evento_id: int) -> dict[str, Any] | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT id, tipo, data, hora, motivo, criado_em "
            "FROM xonha_eventos WHERE id = ?",
            (evento_id,),
        ).fetchone()
        return dict(row) if row else None


def criar_xonha_evento(
    tipo: str,
    data: str,
    motivo: str | None = None,
    hora: str | None = None,
) -> dict[str, Any]:
    tipo_n = (tipo or "").strip().lower()
    if tipo_n not in _XONHA_TIPOS:
        raise ValueError("Tipo inválido. Use saída, volta ou banimento.")
    data_n = _validar_data_xonha(data)
    hora_n = _validar_hora_xonha(hora)
    motivo_n = (motivo or "").strip() or None
    if motivo_n and len(motivo_n) > 500:
        raise ValueError("Motivo muito longo (máx. 500).")
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO xonha_eventos (tipo, data, hora, motivo) VALUES (?, ?, ?, ?)",
            (tipo_n, data_n, hora_n, motivo_n),
        )
        eid = int(cur.lastrowid)
    out = get_xonha_evento(eid)
    assert out is not None
    return out


def atualizar_xonha_evento(
    evento_id: int,
    *,
    tipo: str,
    data: str,
    motivo: str | None = None,
    hora: str | None = None,
) -> dict[str, Any]:
    if not get_xonha_evento(evento_id):
        raise ValueError("Evento não encontrado.")
    tipo_n = (tipo or "").strip().lower()
    if tipo_n not in _XONHA_TIPOS:
        raise ValueError("Tipo inválido. Use saída, volta ou banimento.")
    data_n = _validar_data_xonha(data)
    hora_n = _validar_hora_xonha(hora)
    motivo_n = (motivo or "").strip() or None
    if motivo_n and len(motivo_n) > 500:
        raise ValueError("Motivo muito longo (máx. 500).")
    with get_db() as conn:
        conn.execute(
            "UPDATE xonha_eventos SET tipo = ?, data = ?, hora = ?, motivo = ? WHERE id = ?",
            (tipo_n, data_n, hora_n, motivo_n, evento_id),
        )
    out = get_xonha_evento(evento_id)
    assert out is not None
    return out


def apagar_xonha_evento(evento_id: int) -> bool:
    with get_db() as conn:
        cur = conn.execute("DELETE FROM xonha_eventos WHERE id = ?", (evento_id,))
        return cur.rowcount > 0


def xonha_stats() -> dict[str, Any]:
    """Totais, médias, recorde do dia/mês e dias da semana mais frequentes."""
    from datetime import date as date_cls

    eventos = list_xonha_eventos()
    saidas = [e for e in eventos if e.get("tipo") == "saida"]
    voltas = [e for e in eventos if e.get("tipo") == "volta"]
    banimentos = [e for e in eventos if e.get("tipo") == "banimento"]
    total_saidas = len(saidas)
    total_voltas = len(voltas)
    total_banimentos = len(banimentos)
    # Placar: saídas + banimentos (o que "tira" o Xonha do grupo)
    total_placar = total_saidas + total_banimentos

    saidas_asc = sorted(saidas, key=_xonha_sort_key)
    fora_asc = sorted(saidas + banimentos, key=_xonha_sort_key)
    media_dias_entre_saidas: float | None = None
    if len(saidas_asc) >= 2:
        gaps: list[int] = []
        for prev, cur in zip(saidas_asc, saidas_asc[1:]):
            d0 = datetime.strptime(prev["data"][:10], "%Y-%m-%d").date()
            d1 = datetime.strptime(cur["data"][:10], "%Y-%m-%d").date()
            gaps.append(abs((d1 - d0).days))
        media_dias_entre_saidas = round(sum(gaps) / len(gaps), 1)

    media_saidas_por_mes: float | None = None
    media_saidas_por_dia: float | None = None
    if saidas_asc:
        d_first = datetime.strptime(saidas_asc[0]["data"][:10], "%Y-%m-%d").date()
        d_last = datetime.strptime(saidas_asc[-1]["data"][:10], "%Y-%m-%d").date()
        months = (d_last.year - d_first.year) * 12 + (d_last.month - d_first.month) + 1
        months = max(months, 1)
        media_saidas_por_mes = round(total_saidas / months, 2)

        # Desde a primeira saída até hoje (dias corridos)
        hoje = date_cls.today()
        dias = max((hoje - d_first).days + 1, 1)
        media_saidas_por_dia = round(total_saidas / dias, 3)

    # Recordes / ranking: saídas + banimentos (mesmo critério do placar)
    by_day: dict[str, int] = {}
    by_month: dict[str, int] = {}
    by_weekday: dict[int, int] = {}
    for e in fora_asc:
        day = (e.get("data") or "")[:10]
        if not day:
            continue
        by_day[day] = by_day.get(day, 0) + 1
        ym = day[:7]
        by_month[ym] = by_month.get(ym, 0) + 1
        wd = datetime.strptime(day, "%Y-%m-%d").weekday()  # seg=0
        by_weekday[wd] = by_weekday.get(wd, 0) + 1

    recorde_dia: dict[str, Any] | None = None
    if by_day:
        best_day = max(by_day.items(), key=lambda kv: (kv[1], kv[0]))
        recorde_dia = {"data": best_day[0], "quantidade": best_day[1]}

    recorde_mes: dict[str, Any] | None = None
    if by_month:
        best_m = max(by_month.items(), key=lambda kv: (kv[1], kv[0]))
        y, m = best_m[0].split("-")
        recorde_mes = {
            "ano_mes": best_m[0],
            "label": f"{_XONHA_MESES[int(m)]}/{y}",
            "quantidade": best_m[1],
        }

    dias_semana = [
        {"dia": _XONHA_DIAS_SEMANA[wd], "quantidade": qtd, "weekday": wd}
        for wd, qtd in sorted(by_weekday.items(), key=lambda kv: (-kv[1], kv[0]))
    ]

    inicio_contagem: str | None = None
    if fora_asc:
        inicio_contagem = (fora_asc[0].get("data") or "")[:10] or None

    ultimo = max(eventos, key=_xonha_sort_key) if eventos else None
    status = "desconhecido"
    if ultimo:
        tipo_u = ultimo.get("tipo")
        if tipo_u == "banimento":
            status = "banido"
        elif tipo_u == "saida":
            status = "fora"
        elif tipo_u == "volta":
            status = "dentro"

    hoje = date_cls.today()
    saidas_mes_atual = sum(
        1 for e in saidas if (e.get("data") or "")[:7] == hoje.strftime("%Y-%m")
    )
    corte_30 = hoje.toordinal() - 29
    saidas_ultimos_30_dias = 0
    for e in saidas:
        day = (e.get("data") or "")[:10]
        if not day:
            continue
        try:
            if datetime.strptime(day, "%Y-%m-%d").date().toordinal() >= corte_30:
                saidas_ultimos_30_dias += 1
        except ValueError:
            continue

    dias_desde_ultima_saida: int | None = None
    if saidas_asc:
        d_ult = datetime.strptime(saidas_asc[-1]["data"][:10], "%Y-%m-%d").date()
        dias_desde_ultima_saida = max((hoje - d_ult).days, 0)

    dias_no_status_atual: int | None = None
    if ultimo and ultimo.get("data"):
        try:
            d_ult_ev = datetime.strptime(ultimo["data"][:10], "%Y-%m-%d").date()
            dias_no_status_atual = max((hoje - d_ult_ev).days, 0)
        except ValueError:
            dias_no_status_atual = None

    # Pares saída/banimento → próxima volta (tempo fora)
    ordenados = sorted(eventos, key=_xonha_sort_key)
    tempos_fora_dias: list[float] = []
    pendente_saida: dict[str, Any] | None = None
    for e in ordenados:
        tipo = e.get("tipo")
        if tipo in _XONHA_TIPOS_FORA:
            pendente_saida = e
        elif tipo == "volta" and pendente_saida is not None:
            try:
                h0 = (pendente_saida.get("hora") or "00:00")[:5]
                h1 = (e.get("hora") or "00:00")[:5]
                t0 = datetime.strptime(
                    f"{pendente_saida['data'][:10]} {h0}", "%Y-%m-%d %H:%M"
                )
                t1 = datetime.strptime(f"{e['data'][:10]} {h1}", "%Y-%m-%d %H:%M")
                delta_h = max((t1 - t0).total_seconds() / 3600.0, 0.0)
                tempos_fora_dias.append(delta_h / 24.0)
            except ValueError:
                pass
            pendente_saida = None

    tempo_medio_fora_dias: float | None = None
    maior_tempo_fora_dias: float | None = None
    if tempos_fora_dias:
        tempo_medio_fora_dias = round(sum(tempos_fora_dias) / len(tempos_fora_dias), 1)
        maior_tempo_fora_dias = round(max(tempos_fora_dias), 1)

    by_hour: dict[int, int] = {}
    for e in saidas:
        hora = (e.get("hora") or "").strip()
        if len(hora) >= 2 and hora[:2].isdigit():
            h = int(hora[:2])
            if 0 <= h <= 23:
                by_hour[h] = by_hour.get(h, 0) + 1
    horario_mais_comum: dict[str, Any] | None = None
    if by_hour:
        best_h = max(by_hour.items(), key=lambda kv: (kv[1], -kv[0]))
        horario_mais_comum = {
            "hora": f"{best_h[0]:02d}h",
            "quantidade": best_h[1],
        }

    # % das saídas/banimentos que tiveram volta depois
    taxa_retorno: float | None = None
    if total_placar > 0:
        taxa_retorno = round(100.0 * total_voltas / total_placar, 1)

    # Maior intervalo (dias) entre dois sumiços (saída ou banimento)
    recorde_paz_dias: int | None = None
    if len(fora_asc) >= 2:
        gaps_paz: list[int] = []
        for prev, cur in zip(fora_asc, fora_asc[1:]):
            try:
                d0 = datetime.strptime(prev["data"][:10], "%Y-%m-%d").date()
                d1 = datetime.strptime(cur["data"][:10], "%Y-%m-%d").date()
                gaps_paz.append(max((d1 - d0).days, 0))
            except ValueError:
                continue
        if gaps_paz:
            recorde_paz_dias = max(gaps_paz)

    return {
        "total_saidas": total_saidas,
        "total_voltas": total_voltas,
        "total_banimentos": total_banimentos,
        "total_placar": total_placar,
        "inicio_contagem": inicio_contagem,
        "media_saidas_por_mes": media_saidas_por_mes,
        "media_saidas_por_dia": media_saidas_por_dia,
        "media_dias_entre_saidas": media_dias_entre_saidas,
        "recorde_dia": recorde_dia,
        "recorde_mes": recorde_mes,
        "dias_semana": dias_semana,
        "status": status,
        "ultimo_evento": ultimo,
        "saidas_mes_atual": saidas_mes_atual,
        "saidas_ultimos_30_dias": saidas_ultimos_30_dias,
        "dias_desde_ultima_saida": dias_desde_ultima_saida,
        "dias_no_status_atual": dias_no_status_atual,
        "tempo_medio_fora_dias": tempo_medio_fora_dias,
        "maior_tempo_fora_dias": maior_tempo_fora_dias,
        "horario_mais_comum": horario_mais_comum,
        "taxa_retorno": taxa_retorno,
        "recorde_paz_dias": recorde_paz_dias,
    }
