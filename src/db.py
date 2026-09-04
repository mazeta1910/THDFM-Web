from __future__ import annotations

import json
import re
import secrets
import sqlite3
import unicodedata
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterator

import bcrypt

from src.config import COMPROVANTES_DIR, DATA_DIR, DB_PATH, NOME_MAX_LEN
from src.seed_data import OITAVAS, QUARTAS

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
    recusado_em TEXT,
    inativo_em TEXT
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
    confirmado_em TEXT,
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
    if "inativo_em" not in cols:
        conn.execute("ALTER TABLE participantes ADD COLUMN inativo_em TEXT")
    if "admin_login" not in cols:
        conn.execute("ALTER TABLE participantes ADD COLUMN admin_login TEXT")
    if "username" not in cols:
        conn.execute("ALTER TABLE participantes ADD COLUMN username TEXT")
    if "password_hash" not in cols:
        conn.execute("ALTER TABLE participantes ADD COLUMN password_hash TEXT")
    if "credenciais_em" not in cols:
        conn.execute("ALTER TABLE participantes ADD COLUMN credenciais_em TEXT")
    if "recados_visto_ate" not in cols:
        conn.execute(
            "ALTER TABLE participantes ADD COLUMN recados_visto_ate INTEGER NOT NULL DEFAULT 0"
        )
    if "perfil_frase" not in cols:
        conn.execute("ALTER TABLE participantes ADD COLUMN perfil_frase TEXT")
    if "perfil_relacionamento" not in cols:
        conn.execute("ALTER TABLE participantes ADD COLUMN perfil_relacionamento TEXT")
    if "perfil_aniversario" not in cols:
        conn.execute("ALTER TABLE participantes ADD COLUMN perfil_aniversario TEXT")
    if "banner_preset" not in cols:
        conn.execute(
            "ALTER TABLE participantes ADD COLUMN banner_preset TEXT NOT NULL DEFAULT 'padrao'"
        )
    if "banner_path" not in cols:
        conn.execute("ALTER TABLE participantes ADD COLUMN banner_path TEXT")
    if "times_json" not in cols:
        conn.execute("ALTER TABLE participantes ADD COLUMN times_json TEXT")
    if "sidebar_ordem_json" not in cols:
        conn.execute("ALTER TABLE participantes ADD COLUMN sidebar_ordem_json TEXT")
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
    if "confirmado_em" not in cols:
        conn.execute("ALTER TABLE jogos ADD COLUMN confirmado_em TEXT")
    for item in OITAVAS:
        ida = item.get("ida_em")
        if ida:
            conn.execute(
                "UPDATE jogos SET inicio_em = ? "
                "WHERE confronto_id = ? AND perna = 'ida' "
                "AND (inicio_em IS NULL OR inicio_em = '')",
                (ida, item["id"]),
            )
        volta = item.get("volta_em")
        if volta:
            # Preenche Volta vazia; também alinha com a tabela oficial se ainda
            # estiver em branco (primeira carga dos horários da volta).
            conn.execute(
                "UPDATE jogos SET inicio_em = ? "
                "WHERE confronto_id = ? AND perna = 'volta' "
                "AND (inicio_em IS NULL OR inicio_em = '')",
                (volta, item["id"]),
            )


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
            "INSERT INTO jogos (confronto_id, perna, mandante_clube_id, inicio_em) "
            "VALUES (?, 'volta', 'b', ?)",
            (item["id"], item.get("volta_em")),
        )


def _migrate_quartas_ordem_casa(conn: sqlite3.Connection) -> None:
    """Corrige clube_a/clube_b das quartas para o mandante da volta canônico.

    Ida: clube_a em casa. Volta: clube_b em casa (Grêmio, Galo, Vitória, Santos).
    Idempotente: só altera pares já cadastrados que estejam invertidos.
    """
    canon = {
        frozenset({p["clube_a"], p["clube_b"]}): (p["clube_a"], p["clube_b"])
        for p in QUARTAS
    }
    rows = conn.execute(
        "SELECT id, clube_a, clube_b FROM confrontos WHERE fase = 'quartas' ORDER BY id"
    ).fetchall()
    for r in rows:
        chave = frozenset({r["clube_a"], r["clube_b"]})
        alvo = canon.get(chave)
        if not alvo:
            continue
        want_a, want_b = alvo
        if r["clube_a"] == want_a and r["clube_b"] == want_b:
            continue
        conn.execute(
            "UPDATE confrontos SET clube_a = ?, clube_b = ? WHERE id = ?",
            (want_a, want_b, r["id"]),
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

    cols = {
        row[1] for row in conn.execute("PRAGMA table_info(xonha_eventos)").fetchall()
    }
    if "origem" not in cols:
        conn.execute("ALTER TABLE xonha_eventos ADD COLUMN origem TEXT")
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_xonha_eventos_origem "
        "ON xonha_eventos(origem) WHERE origem IS NOT NULL AND origem != ''"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_xonha_eventos_data "
        "ON xonha_eventos(data DESC, id DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_xonha_eventos_tipo_data "
        "ON xonha_eventos(tipo, data)"
    )


def _migrate_listra(conn: sqlite3.Connection) -> None:
    from src.listra_seed import LISTRA_ANO_ATUAL, LISTRA_ANOS, listra_seed_por_ano

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS listra_frases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            texto TEXT NOT NULL,
            responsavel TEXT NOT NULL DEFAULT '',
            criado_por_id INTEGER REFERENCES participantes(id),
            criado_em TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
            ordem INTEGER NOT NULL DEFAULT 0,
            ano INTEGER NOT NULL DEFAULT 2026
        )
        """
    )
    cols = {
        row[1] for row in conn.execute("PRAGMA table_info(listra_frases)").fetchall()
    }
    if "ano" not in cols:
        conn.execute(
            f"ALTER TABLE listra_frases ADD COLUMN ano INTEGER NOT NULL DEFAULT {int(LISTRA_ANO_ATUAL)}"
        )
        conn.execute(
            "UPDATE listra_frases SET ano = ? WHERE ano IS NULL OR ano = 0",
            (int(LISTRA_ANO_ATUAL),),
        )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS listra_permissoes (
            participante_id INTEGER PRIMARY KEY REFERENCES participantes(id) ON DELETE CASCADE,
            pode_adicionar INTEGER NOT NULL DEFAULT 0,
            pode_enviar INTEGER NOT NULL DEFAULT 0,
            atualizado_em TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_listra_frases_ano_ordem "
        "ON listra_frases(ano DESC, ordem ASC, id ASC)"
    )
    _migrar_listra_emoji_destaque(conn)
    _migrar_listra_reembolsos_itens(conn)
    _migrar_listra_meliantes(conn)
    for ano in LISTRA_ANOS:
        _seed_listra_ano_se_faltando(conn, int(ano), listra_seed_por_ano(int(ano)))
    _migrar_listra_emojis_do_seed(conn)


def _seed_listra_ano_se_faltando(
    conn: sqlite3.Connection, ano: int, frases: tuple[str, ...]
) -> None:
    if not frases:
        return
    if conn.execute(
        "SELECT 1 FROM listra_frases WHERE ano = ? LIMIT 1", (ano,)
    ).fetchone():
        return
    for i, raw in enumerate(frases, start=1):
        emoji, texto = split_leading_emoji(raw)
        conn.execute(
            "INSERT INTO listra_frases "
            "(texto, responsavel, ordem, ano, criado_em, emoji, destaque) "
            "VALUES (?, '', ?, ?, datetime('now', 'localtime'), ?, '')",
            (texto or raw, i, ano, emoji),
        )



def _migrate_perfil_karma(conn: sqlite3.Connection) -> None:
    """Votos de karma do perfil (média agregada por participante)."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS perfil_karma_votos (
          voter_id INTEGER NOT NULL REFERENCES participantes(id) ON DELETE CASCADE,
          target_id INTEGER NOT NULL REFERENCES participantes(id) ON DELETE CASCADE,
          categoria TEXT NOT NULL
            CHECK (categoria IN ('confiavel', 'legal', 'sexy', 'burro')),
          nivel INTEGER NOT NULL CHECK (nivel BETWEEN 1 AND 3),
          updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
          PRIMARY KEY (voter_id, target_id, categoria),
          CHECK (voter_id != target_id)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_perfil_karma_target "
        "ON perfil_karma_votos(target_id, categoria)"
    )


def _migrate_perfil_nutela(conn: sqlite3.Connection) -> None:
    """Votos nutella↔raíz do perfil (média 0–100 agregada por participante)."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS perfil_nutela_votos (
          voter_id INTEGER NOT NULL REFERENCES participantes(id) ON DELETE CASCADE,
          target_id INTEGER NOT NULL REFERENCES participantes(id) ON DELETE CASCADE,
          valor INTEGER NOT NULL CHECK (valor BETWEEN 0 AND 100),
          updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
          PRIMARY KEY (voter_id, target_id),
          CHECK (voter_id != target_id)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_perfil_nutela_target "
        "ON perfil_nutela_votos(target_id)"
    )


def _migrate_perfil_recados(conn: sqlite3.Connection) -> None:
    """Recados do mural, atrelados ao perfil de destino (texto e/ou mídia)."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS perfil_recados (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          target_id INTEGER NOT NULL REFERENCES participantes(id) ON DELETE CASCADE,
          autor_id INTEGER NOT NULL REFERENCES participantes(id) ON DELETE CASCADE,
          texto TEXT NOT NULL DEFAULT '',
          midia_path TEXT,
          parent_id INTEGER REFERENCES perfil_recados(id) ON DELETE CASCADE,
          criado_em TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        )
        """
    )
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(perfil_recados)").fetchall()}
    if "midia_path" not in cols:
        conn.execute("ALTER TABLE perfil_recados ADD COLUMN midia_path TEXT")
    # Bases antigas tinham CHECK(texto não vazio) — reconstrói sem o CHECK
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='perfil_recados'"
    ).fetchone()
    sql = (row["sql"] or "") if row else ""
    if "CHECK" in sql.upper():
        conn.executescript(
            """
            CREATE TABLE perfil_recados__new (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              target_id INTEGER NOT NULL REFERENCES participantes(id) ON DELETE CASCADE,
              autor_id INTEGER NOT NULL REFERENCES participantes(id) ON DELETE CASCADE,
              texto TEXT NOT NULL DEFAULT '',
              midia_path TEXT,
              parent_id INTEGER REFERENCES perfil_recados(id) ON DELETE CASCADE,
              criado_em TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            );
            INSERT INTO perfil_recados__new (id, target_id, autor_id, texto, midia_path, parent_id, criado_em)
            SELECT id, target_id, autor_id, COALESCE(texto, ''), midia_path, NULL, criado_em
            FROM perfil_recados;
            DROP TABLE perfil_recados;
            ALTER TABLE perfil_recados__new RENAME TO perfil_recados;
            """
        )
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(perfil_recados)").fetchall()}
    if "parent_id" not in cols:
        conn.execute("ALTER TABLE perfil_recados ADD COLUMN parent_id INTEGER")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_perfil_recados_target "
        "ON perfil_recados(target_id, id DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_perfil_recados_parent "
        "ON perfil_recados(parent_id, id)"
    )


def _migrate_perfil_recado_reacoes(conn: sqlite3.Connection) -> None:
    """Reações estilo Discord nos recados do mural."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS perfil_recado_reacoes (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          recado_id INTEGER NOT NULL REFERENCES perfil_recados(id) ON DELETE CASCADE,
          voter_id INTEGER NOT NULL REFERENCES participantes(id) ON DELETE CASCADE,
          emoji TEXT NOT NULL,
          criado_em TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
          UNIQUE (recado_id, voter_id, emoji)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_perfil_recado_reacoes_recado "
        "ON perfil_recado_reacoes(recado_id)"
    )


def _migrate_grid_progresso(conn: sqlite3.Connection) -> None:
    """Progresso diário do THDFM Grid (streak/histórico por participante)."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS grid_progresso (
          participante_id INTEGER NOT NULL REFERENCES participantes(id) ON DELETE CASCADE,
          dia TEXT NOT NULL,
          celulas_json TEXT NOT NULL DEFAULT '[]',
          finalizado INTEGER NOT NULL DEFAULT 0,
          atualizado_em TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
          PRIMARY KEY (participante_id, dia)
        )
        """
    )


def _migrate_grid_partida(conn: sqlite3.Connection) -> None:
    """Partidas Raiz/Xonha (substitui progresso único no ranking novo)."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS grid_partida (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          participante_id INTEGER NOT NULL REFERENCES participantes(id) ON DELETE CASCADE,
          dia TEXT NOT NULL,
          modo TEXT NOT NULL CHECK (modo IN ('raiz', 'xonha')),
          puzzle_salt TEXT NOT NULL DEFAULT '',
          celulas_json TEXT NOT NULL DEFAULT '[]',
          finalizado INTEGER NOT NULL DEFAULT 0,
          interrompido INTEGER NOT NULL DEFAULT 0,
          iniciado_em TEXT,
          encerrado_em TEXT,
          tempo_segundos INTEGER,
          pontos INTEGER NOT NULL DEFAULT 0,
          dicas_json TEXT NOT NULL DEFAULT '[]',
          criado_em TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
          atualizado_em TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_grid_partida_part_dia_modo "
        "ON grid_partida(participante_id, dia, modo)"
    )
    # No máx. 1 Raiz por participante/dia (parcial único via índice).
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_grid_partida_raiz_unica "
        "ON grid_partida(participante_id, dia) WHERE modo = 'raiz'"
    )


def _migrate_grid_xonha_passe(conn: sqlite3.Connection) -> None:
    """Passe mensal: Xonha ilimitado até valido_ate."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS grid_xonha_passe (
          participante_id INTEGER PRIMARY KEY REFERENCES participantes(id) ON DELETE CASCADE,
          valido_ate TEXT NOT NULL,
          liberado_em TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
          liberado_por TEXT NOT NULL DEFAULT ''
        )
        """
    )


def _migrate_grid_puzzle_salt(conn: sqlite3.Connection) -> None:
    """Salt por dia para regenerar eixos do puzzle sem mudar o algoritmo global."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS grid_puzzle_salt (
          dia TEXT PRIMARY KEY,
          salt TEXT NOT NULL,
          atualizado_em TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        )
        """
    )


def _migrate_hall_lendas(conn: sqlite3.Connection) -> None:
    """Hall das Lendas — uma ficha por participante (total doado + recado + moldura)."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS hall_lendas (
          participante_id INTEGER PRIMARY KEY REFERENCES participantes(id) ON DELETE CASCADE,
          valor_centavos INTEGER NOT NULL DEFAULT 0,
          recado TEXT NOT NULL DEFAULT '',
          borda TEXT NOT NULL DEFAULT 'anel',
          doado_em TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
          criado_em TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
          atualizado_em TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_hall_lendas_valor "
        "ON hall_lendas(valor_centavos DESC, doado_em DESC)"
    )


def _migrate_bug_reports(conn: sqlite3.Connection) -> None:
    """Reports de bugs do Grid — usuário envia; Mazeta responde/atualiza status."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS bug_reports (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          participante_id INTEGER NOT NULL REFERENCES participantes(id) ON DELETE CASCADE,
          titulo TEXT NOT NULL,
          mensagem TEXT NOT NULL,
          imagem_path TEXT,
          status TEXT NOT NULL DEFAULT 'aberto',
          resposta TEXT NOT NULL DEFAULT '',
          respondido_em TEXT,
          usuario_leu_resposta INTEGER NOT NULL DEFAULT 1,
          criado_em TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
          atualizado_em TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_bug_reports_part "
        "ON bug_reports(participante_id, criado_em DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_bug_reports_status "
        "ON bug_reports(status, atualizado_em DESC)"
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS bug_report_mensagens (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          report_id INTEGER NOT NULL REFERENCES bug_reports(id) ON DELETE CASCADE,
          autor TEXT NOT NULL,
          texto TEXT NOT NULL,
          criado_em TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_bug_report_mensagens_report "
        "ON bug_report_mensagens(report_id, criado_em ASC, id ASC)"
    )
    # Backfill do log a partir dos campos legados (uma vez).
    chave = "bug_report_mensagens_backfill_v1"
    if not conn.execute("SELECT 1 FROM meta WHERE chave = ?", (chave,)).fetchone():
        rows = conn.execute("SELECT * FROM bug_reports ORDER BY id ASC").fetchall()
        for row in rows:
            rid = int(row["id"])
            ja = conn.execute(
                "SELECT 1 FROM bug_report_mensagens WHERE report_id = ? LIMIT 1",
                (rid,),
            ).fetchone()
            if ja:
                continue
            msg = (row["mensagem"] or "").strip()
            if msg:
                conn.execute(
                    """
                    INSERT INTO bug_report_mensagens (report_id, autor, texto, criado_em)
                    VALUES (?, 'usuario', ?, ?)
                    """,
                    (rid, msg, row["criado_em"] or None),
                )
            resp = (row["resposta"] or "").strip()
            if resp:
                conn.execute(
                    """
                    INSERT INTO bug_report_mensagens (report_id, autor, texto, criado_em)
                    VALUES (?, 'admin', ?, ?)
                    """,
                    (
                        rid,
                        resp,
                        row["respondido_em"] or row["atualizado_em"] or None,
                    ),
                )
        conn.execute(
            "INSERT INTO meta (chave, valor) VALUES (?, ?)",
            (chave, "1"),
        )


def _reset_grid_progresso_lancamento(conn: sqlite3.Connection) -> None:
    """Zera o progresso do Grid uma vez — lançamento público (ranking do zero)."""
    chave = "grid_progresso_reset_v1"
    if conn.execute("SELECT 1 FROM meta WHERE chave = ?", (chave,)).fetchone():
        return
    conn.execute("DELETE FROM grid_progresso")
    conn.execute(
        "INSERT INTO meta (chave, valor) VALUES (?, ?)",
        (chave, "1"),
    )


def _purge_grid_progresso_pre_ranking(conn: sqlite3.Connection) -> None:
    """Remove progresso de dias antes do ranking oficial (ex.: 11/08 sem jogo)."""
    chave = "grid_progresso_ranking_desde_v1"
    if conn.execute("SELECT 1 FROM meta WHERE chave = ?", (chave,)).fetchone():
        return
    # Espelha GRID_RANKING_DESDE em grid_game (evita import circular no boot).
    desde = "2026-08-12"
    conn.execute("DELETE FROM grid_progresso WHERE dia < ?", (desde,))
    conn.execute(
        "INSERT INTO meta (chave, valor) VALUES (?, ?)",
        (chave, desde),
    )


def _cutover_grid_raiz_xonha_v1(conn: sqlite3.Connection) -> None:
    """Lança Raiz/Xonha: zera ranking antigo (progresso) uma vez."""
    chave = "grid_raiz_xonha_cutover_v1"
    if conn.execute("SELECT 1 FROM meta WHERE chave = ?", (chave,)).fetchone():
        return
    conn.execute("DELETE FROM grid_progresso")
    conn.execute(
        "INSERT INTO meta (chave, valor) VALUES (?, ?)",
        (chave, "1"),
    )


def _cutover_grid_pro_relaunch_v1(conn: sqlite3.Connection) -> None:
    """Relança o modo Pro: novo salt do dia + zera progresso/partidas Pro de hoje."""
    import secrets

    chave = "grid_pro_relaunch_v1"
    if conn.execute("SELECT 1 FROM meta WHERE chave = ?", (chave,)).fetchone():
        return
    # dia_grid depende da virada em meta — já migrada neste init.
    from src.grid_game import dia_grid

    dia = dia_grid()
    salt = secrets.token_hex(8)
    conn.execute(
        """
        INSERT INTO grid_puzzle_salt (dia, salt, atualizado_em)
        VALUES (?, ?, datetime('now', 'localtime'))
        ON CONFLICT(dia) DO UPDATE SET
          salt = excluded.salt,
          atualizado_em = datetime('now', 'localtime')
        """,
        (dia, salt),
    )
    conn.execute("DELETE FROM grid_progresso WHERE dia = ?", (dia,))
    conn.execute(
        "DELETE FROM grid_partida WHERE dia = ? AND modo = 'raiz'",
        (dia,),
    )
    conn.execute(
        "INSERT INTO meta (chave, valor) VALUES (?, ?)",
        (chave, dia),
    )


def init_db() -> None:
    with get_db() as conn:
        conn.executescript(SCHEMA)
        _migrate_participantes(conn)
        _migrate_jogos(conn)
        _migrar_celulares_br(conn)
        _migrate_recuperacao(conn)
        _migrate_xonhometro(conn)
        _migrate_listra(conn)
        _migrate_perfil_karma(conn)
        _migrate_perfil_nutela(conn)
        _migrate_perfil_recados(conn)
        _migrate_perfil_recado_reacoes(conn)
        _migrate_grid_progresso(conn)
        _migrate_grid_partida(conn)
        _migrate_grid_xonha_passe(conn)
        _migrate_grid_puzzle_salt(conn)
        _migrate_hall_lendas(conn)
        _migrate_bug_reports(conn)
        _migrate_quartas_ordem_casa(conn)
        _reset_grid_progresso_lancamento(conn)
        _purge_grid_progresso_pre_ranking(conn)
        _cutover_grid_raiz_xonha_v1(conn)
        _cutover_grid_pro_relaunch_v1(conn)
        row = conn.execute("SELECT valor FROM meta WHERE chave = 'janela'").fetchone()
        if not row:
            conn.execute(
                "INSERT INTO meta (chave, valor) VALUES ('janela', 'ida'), ('fase_atual', 'oitavas')"
            )
        if not conn.execute("SELECT 1 FROM confrontos LIMIT 1").fetchone():
            _seed_oitavas(conn)
    # Invalida cache de puzzle após eventual novo salt do cutover Pro.
    try:
        from src.grid_game import _gerar_puzzle_cached

        _gerar_puzzle_cached.cache_clear()
    except Exception:
        pass


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
    "avatar_path, celular, criado_em, link_enviado_em, recusado_em, inativo_em, "
    "admin_login, username, password_hash, credenciais_em, recados_visto_ate, "
    "perfil_frase, perfil_relacionamento, perfil_aniversario, "
    "banner_preset, banner_path, times_json, sidebar_ordem_json"
)


def participante_ativo_no_bolao(part: dict[str, Any] | None) -> bool:
    """Liberado e ainda no bolão (não marcado como inativo)."""
    if not part or part.get("status") != "liberado":
        return False
    return not (part.get("inativo_em") or "").strip()


def list_participantes() -> list[dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute(
            f"SELECT {_PARTICIPANTE_COLS} FROM participantes ORDER BY "
            "CASE "
            "WHEN admin_login IS NOT NULL AND admin_login != '' THEN 0 "
            "ELSE 1 END, "
            "CASE "
            "WHEN status = 'liberado' AND (inativo_em IS NULL OR inativo_em = '') THEN 3 "
            "WHEN status = 'liberado' THEN 4 "
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

    Aceita entradas comuns no Brasil:
    - (11) 99999-9999 / 11999999999
    - +55 11 99999-9999 / 5511999999999
    - 011 99999-9999 (zero de tronco antes do DDD)
    - 5555… (código do país duplicado por engano)
    - celular antigo sem o 9º dígito (DDD + 8 dígitos) → insere o 9

    Não confundir DDD 55 (RS) com código do país: só trata como
    internacional se, após limpar, tiver 12 ou 13 dígitos começando com 55.
    """
    digits = re.sub(r"\D+", "", celular or "")
    # 00… (saída internacional) ou 0… (tronco) — WhatsApp rejeita zero à esquerda
    while digits.startswith("00"):
        digits = digits[2:]
    if digits.startswith("0"):
        digits = digits.lstrip("0")
    # 55 duplicado: 5555119… (14/15 dígitos) → remove um 55
    if digits.startswith("5555") and len(digits) in (14, 15):
        digits = digits[2:]
    # 55 + DDD + 9 extra + 9 + 8 dígitos (14 no total) → tira o 9 duplicado
    if digits.startswith("55") and len(digits) == 14:
        local = digits[2:]
        if local[2] == "9" and local[3] == "9" and len(local) == 12:
            digits = "55" + local[:2] + "9" + local[4:]
    digits = _garantir_nono_digito_movel(digits)
    if digits.startswith("55") and len(digits) in (12, 13):
        return digits
    if len(digits) in (10, 11):
        local = _garantir_nono_digito_movel(digits)
        return "55" + local
    raise ValueError("Celular inválido")


def _garantir_nono_digito_movel(digits: str) -> str:
    """Insere o 9º dígito em celular BR antigo (DDD + 8 dígitos 6–9…).

    Aceita só local (10 dígitos) ou internacional 55+local (12 dígitos).
    Fixo/não-móvel (2–5 após o DDD) permanece como está.
    """
    if digits.startswith("55") and len(digits) == 12:
        local = digits[2:]
        if local[2] in "6789":
            return "55" + local[:2] + "9" + local[2:]
        return digits
    if len(digits) == 10 and digits[2] in "6789":
        return digits[:2] + "9" + digits[2:]
    return digits


def celular_whatsapp(celular: str | None) -> str | None:
    """Dígitos para wa.me / api.whatsapp.com (com 55). None se inválido."""
    if not celular:
        return None
    try:
        return normalizar_celular(celular)
    except ValueError:
        return None


def diagnostico_celular_whatsapp(celular: str | None) -> dict[str, Any]:
    """Explica se o celular serve para link do WhatsApp."""
    raw = (celular or "").strip()
    if not raw:
        return {
            "ok": False,
            "motivo": "sem_celular",
            "rotulo": "Sem celular cadastrado",
            "digits": None,
        }
    digits = celular_whatsapp(raw)
    if not digits:
        return {
            "ok": False,
            "motivo": "invalido",
            "rotulo": "Celular inválido — confira DDD e número",
            "digits": None,
        }
    return {
        "ok": True,
        "motivo": "ok",
        "rotulo": formatar_celular(digits),
        "digits": digits,
    }


def formatar_celular(celular: str | None) -> str:
    """Exibição: +55 (11) 99999-9999."""
    digits = celular_whatsapp(celular)
    if not digits:
        # Mostra o que deu para limpar, sem inventar link quebrado
        raw = re.sub(r"\D+", "", celular or "")
        return raw
    local = digits[2:] if digits.startswith("55") and len(digits) >= 12 else digits
    if len(local) == 11:
        return f"+55 ({local[:2]}) {local[2:7]}-{local[7:]}"
    if len(local) == 10:
        return f"+55 ({local[:2]}) {local[2:6]}-{local[6:]}"
    return f"+{digits}" if not digits.startswith("+") else digits


def url_whatsapp_chat(celular: str | None, texto: str = "") -> str | None:
    """Link de conversa no WhatsApp (phone= só dígitos internacionais)."""
    from urllib.parse import quote

    wa = celular_whatsapp(celular)
    if not wa:
        return None
    if texto:
        return f"https://api.whatsapp.com/send?phone={wa}&text={quote(texto)}"
    return f"https://api.whatsapp.com/send?phone={wa}"


def url_whatsapp_chat_me(celular: str | None, texto: str = "") -> str | None:
    """Alternativa wa.me — alguns clientes abrem melhor que api.whatsapp.com."""
    from urllib.parse import quote

    wa = celular_whatsapp(celular)
    if not wa:
        return None
    if texto:
        return f"https://wa.me/{wa}?text={quote(texto)}"
    return f"https://wa.me/{wa}"


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


def mensagem_whatsapp_cobranca_palpite(
    nome: str,
    base_url: str,
    token: str,
    *,
    fase_label: str,
    perna_label: str,
    n_feitos: int,
    n_jogos: int,
    trava_min: int | None = None,
    jogos: list[dict[str, Any]] | None = None,
    agora: datetime | None = None,
) -> str:
    """Lembrete individual para quem ainda não completou os palpites.

    `jogos` — lista de dicts com clube_a, clube_b, inicio_em (os que faltam
    para a pessoa). Cita os do dia de hoje ou, se não houver, o próximo dia.
    """
    from src.config import TRAVA_PALPITE_ANTES_MIN

    if trava_min is None:
        trava_min = TRAVA_PALPITE_ANTES_MIN
    link = f"{base_url.rstrip('/')}/p/{token}"
    primeiro = (nome or "").strip().split()[0] if (nome or "").strip() else ""
    oi = f"Oi, {primeiro}!" if primeiro else "Oi!"
    if n_jogos > 0 and 0 < n_feitos < n_jogos:
        situacao = (
            f"Vimos que você já fez {n_feitos} de {n_jogos} palpites da "
            f"{fase_label} ({perna_label}), mas ainda falta completar."
        )
    else:
        situacao = (
            f"Ainda não vimos seus palpites da {fase_label} ({perna_label}) "
            "no Bolão THDFM."
        )

    bloco_jogos = texto_jogos_proximos_cobranca(jogos or [], agora=agora)
    if bloco_jogos:
        quando = (
            f"{bloco_jogos}\n\n"
            f"Os palpites ficam disponíveis para alteração até {trava_min} min "
            "antes do início de cada partida."
        )
    else:
        quando = (
            "O(s) jogo(s) acontece(m) em breve — os palpites ficam disponíveis "
            f"para alteração até {trava_min} min antes do início de cada partida."
        )

    return (
        f"{oi}\n\n"
        f"{situacao}\n\n"
        f"{quando}\n\n"
        f"É por aqui (link pessoal):\n{link}\n\n"
        "Qualquer dúvida, fala com a gente!"
    )


def texto_jogos_proximos_cobranca(
    jogos: list[dict[str, Any]],
    *,
    agora: datetime | None = None,
) -> str:
    """Bloco WhatsApp listando os jogos do dia (ou do próximo dia com partida)."""
    from src.config import _TZ_SP
    from src.seed_data import parse_inicio_em

    now = agora or datetime.now(_TZ_SP)
    if now.tzinfo is None:
        now = now.replace(tzinfo=_TZ_SP)
    hoje = now.date()

    por_dia: dict[Any, list[tuple[Any, str, str]]] = {}
    for j in jogos:
        dt = parse_inicio_em(j.get("inicio_em"))
        if dt is None:
            continue
        label = (j.get("rotulo") or "").strip()
        if not label:
            a = (j.get("clube_a") or "?").strip()
            b = (j.get("clube_b") or "?").strip()
            label = f"{a} x {b}"
        hora = dt.strftime("%H:%M")
        por_dia.setdefault(dt.date(), []).append((dt, hora, label))

    if not por_dia:
        return ""

    # Prefere hoje; senão o próximo dia com jogo; senão o mais cedo que existir.
    if hoje in por_dia:
        dia = hoje
    else:
        futuros = sorted(d for d in por_dia if d >= hoje)
        dia = futuros[0] if futuros else min(por_dia)

    itens = sorted(por_dia[dia], key=lambda t: t[0])
    linhas = [f"• {label} — {hora}" for _, hora, label in itens]

    if dia == hoje:
        cabeca = f"Hoje ({dia.strftime('%d/%m')}) tem:"
    elif dia == hoje + timedelta(days=1):
        cabeca = f"Amanhã ({dia.strftime('%d/%m')}) tem:"
    else:
        cabeca = f"No dia {dia.strftime('%d/%m')} tem:"

    return cabeca + "\n" + "\n".join(linhas)


def jogos_ids_fase_perna(fase: str, perna: str) -> list[int]:
    """IDs dos jogos de uma fase/perna (ordem dos confrontos)."""
    if perna not in ("ida", "volta"):
        raise ValueError("perna inválida")
    with get_db() as conn:
        rows = conn.execute(
            "SELECT j.id FROM jogos j "
            "JOIN confrontos c ON c.id = j.confronto_id "
            "WHERE c.fase = ? AND j.perna = ? "
            "ORDER BY c.id",
            (fase, perna),
        ).fetchall()
        return [int(r["id"]) for r in rows]


def status_palpites_liberados(
    fase: str,
    perna: str,
    *,
    so_abertos: bool = True,
    janela: str | None = None,
) -> dict[str, Any]:
    """Rollup por participante liberado: completo / incompleto na fase+perna.

    Por padrão considera só jogos ainda editáveis (não travados por horário).
    Se todos já estiverem travados, cai nos jogos da fase/perna inteira para
    ainda dar para ver quem deixou de palpitar.
    """
    from src.seed_data import jogo_palpite_travado

    if perna not in ("ida", "volta"):
        raise ValueError("perna inválida")

    confrontos = list_confrontos_completos(fase)
    jogos_meta: list[dict[str, Any]] = []
    for c in confrontos:
        jogo = next((j for j in c["jogos"] if j.get("perna") == perna), None)
        if not jogo:
            continue
        travado = jogo_palpite_travado(jogo.get("inicio_em"), janela=janela)
        clube_a = c.get("clube_a")
        clube_b = c.get("clube_b")
        # Na volta o mandante é o clube B — lista como no placar do jogo.
        if perna == "volta":
            rotulo = f"{clube_b} x {clube_a}"
        else:
            rotulo = f"{clube_a} x {clube_b}"
        jogos_meta.append(
            {
                "id": int(jogo["id"]),
                "confronto_id": int(c["id"]),
                "inicio_em": jogo.get("inicio_em"),
                "travado": travado,
                "clube_a": clube_a,
                "clube_b": clube_b,
                "rotulo": rotulo,
            }
        )

    considerados = [j for j in jogos_meta if not j["travado"]] if so_abertos else list(jogos_meta)
    if so_abertos and not considerados and jogos_meta:
        considerados = list(jogos_meta)
    jogo_ids = [j["id"] for j in considerados]
    n_jogos = len(jogo_ids)
    ids_set = set(jogo_ids)
    por_id = {j["id"]: j for j in considerados}

    liberados = [p for p in list_participantes() if participante_ativo_no_bolao(p)]
    feitos_por_pid: dict[int, set[int]] = {int(p["id"]): set() for p in liberados}
    if jogo_ids:
        placeholders = ",".join("?" * len(jogo_ids))
        with get_db() as conn:
            rows = conn.execute(
                f"SELECT participante_id, jogo_id FROM palpites_jogo "
                f"WHERE jogo_id IN ({placeholders})",
                tuple(jogo_ids),
            ).fetchall()
            for r in rows:
                pid = int(r["participante_id"])
                jid = int(r["jogo_id"])
                if pid in feitos_por_pid and jid in ids_set:
                    feitos_por_pid[pid].add(jid)

    completos: list[dict[str, Any]] = []
    incompletos: list[dict[str, Any]] = []
    for p in liberados:
        pid = int(p["id"])
        feitos_ids = feitos_por_pid.get(pid, set())
        n_feitos = len(feitos_ids)
        if n_feitos > n_jogos:
            n_feitos = n_jogos
        completo = n_jogos > 0 and n_feitos >= n_jogos
        faltando = [por_id[jid] for jid in jogo_ids if jid not in feitos_ids]
        item = {
            "id": pid,
            "nome": p.get("nome") or "",
            "celular": p.get("celular"),
            "token": p.get("token"),
            "avatar_path": p.get("avatar_path"),
            "n_feitos": n_feitos,
            "n_jogos": n_jogos,
            "completo": completo,
            "parcial": n_feitos > 0 and not completo,
            "faltando_jogos": faltando,
        }
        if completo:
            completos.append(item)
        else:
            incompletos.append(item)

    completos.sort(key=lambda x: (x["nome"] or "").casefold())
    incompletos.sort(
        key=lambda x: (0 if x["n_feitos"] == 0 else 1, (x["nome"] or "").casefold())
    )

    return {
        "fase": fase,
        "perna": perna,
        "jogos": considerados,
        "jogos_todos": jogos_meta,
        "n_jogos": n_jogos,
        "n_completos": len(completos),
        "n_incompletos": len(incompletos),
        "completos": completos,
        "incompletos": incompletos,
        "ids_considerados": ids_set,
    }


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
    senha_nova: str | None = None,
    username: str | None = None,
) -> dict[str, Any]:
    """Dono atualiza username e/ou senha. Pelo menos um dos dois. Não devolve senha em claro."""
    part = get_participante(participante_id)
    if not part:
        raise ValueError("Participante não encontrado")
    if part.get("status") != "liberado":
        raise ValueError("Só dá para redefinir conta liberada")

    senha_raw = (senha_nova or "").strip() if senha_nova is not None else ""
    atualizar_senha = bool(senha_raw)
    atualizar_user = username is not None and str(username).strip() != ""

    if not atualizar_senha and not atualizar_user:
        raise ValueError("Informe um username novo e/ou uma senha nova")

    u = None
    ph = None
    if atualizar_user:
        u = normalizar_username(username)
        if not username_disponivel(u, exceto_id=participante_id):
            raise ValueError("Username já está em uso")
    if atualizar_senha:
        senha_ok = validar_senha_nova(senha_raw)
        ph = hash_senha(senha_ok)

    with get_db() as conn:
        if u is not None and ph is not None:
            conn.execute(
                "UPDATE participantes SET username = ?, password_hash = ?, "
                "credenciais_em = datetime('now', 'localtime') WHERE id = ?",
                (u, ph, participante_id),
            )
        elif u is not None:
            conn.execute(
                "UPDATE participantes SET username = ?, "
                "credenciais_em = datetime('now', 'localtime') WHERE id = ?",
                (u, participante_id),
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
            username = (part.get("username") or "").strip().lower()
            # Conta da sessão com username = login do .env (ex.: ramos) → vincula.
            if not atual and username == login:
                vincular_admin_login(part["id"], login)
                part = get_participante(part["id"]) or part
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
            "liberado_em = datetime('now', 'localtime'), "
            "recusado_em = NULL, inativo_em = NULL "
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


def inativar_participante(participante_id: int) -> bool:
    """Marca liberado como inativo (some da classificação/cobrança). Mantém histórico."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT status, inativo_em FROM participantes WHERE id = ?",
            (participante_id,),
        ).fetchone()
        if not row or row["status"] != "liberado":
            return False
        if (row["inativo_em"] or "").strip():
            return True
        conn.execute(
            "UPDATE participantes SET inativo_em = datetime('now', 'localtime') "
            "WHERE id = ?",
            (participante_id,),
        )
        return True


def reativar_participante(participante_id: int) -> bool:
    """Tira o liberado da lista de inativos (volta ao bolão ativo)."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT status FROM participantes WHERE id = ?", (participante_id,)
        ).fetchone()
        if not row or row["status"] != "liberado":
            return False
        conn.execute(
            "UPDATE participantes SET inativo_em = NULL WHERE id = ?",
            (participante_id,),
        )
        return True


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


BANNER_PRESETS = ("padrao", "laranja", "gramado", "noite", "carbono", "ouro")
PERFIL_TIMES_MAX = 12


def _parse_times_json(raw: str | None) -> list[str]:
    import json

    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    out: list[str] = []
    for item in data:
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
        if len(out) >= PERFIL_TIMES_MAX:
            break
    return out


def perfil_soft_do_participante(part: dict[str, Any] | None) -> dict[str, Any]:
    """Campos editáveis do perfil (frase, times, banner)."""
    from src.clubes_catalogo import carregar_clubes

    if not part:
        return {
            "frase": "",
            "relacionamento": "",
            "aniversario": "",
            "times_ids": [],
            "times": [],
            "banner": {"kind": "preset", "id": "padrao", "url": None},
        }
    times_ids = _parse_times_json(part.get("times_json"))
    by_id = {c["id"]: c for c in carregar_clubes() if c.get("tem_emblema")}
    times = []
    for tid in times_ids:
        c = by_id.get(tid)
        if not c:
            continue
        times.append(
            {
                "id": c["id"],
                "nome": c["nome"],
                "uf": c["uf"],
                "emblema": c["emblema"],
            }
        )
    banner_path = (part.get("banner_path") or "").strip() or None
    preset = (part.get("banner_preset") or "padrao").strip().lower()
    if preset not in BANNER_PRESETS:
        preset = "padrao"
    if banner_path:
        banner = {"kind": "custom", "id": None, "url": f"/banners/{banner_path}"}
    else:
        banner = {"kind": "preset", "id": preset, "url": None}
    return {
        "frase": (part.get("perfil_frase") or "").strip(),
        "relacionamento": (part.get("perfil_relacionamento") or "").strip(),
        "aniversario": (part.get("perfil_aniversario") or "").strip(),
        "times_ids": [t["id"] for t in times],
        "times": times,
        "banner": banner,
    }


def salvar_perfil_soft(
    participante_id: int,
    *,
    frase: str | None = None,
    relacionamento: str | None = None,
    aniversario: str | None = None,
    times_ids: list[str] | None = None,
    banner_preset: str | None = None,
    clear_banner_custom: bool = False,
) -> None:
    import json
    import re

    sets: list[str] = []
    args: list[Any] = []
    if frase is not None:
        sets.append("perfil_frase = ?")
        args.append(str(frase).strip()[:280] or None)
    if relacionamento is not None:
        sets.append("perfil_relacionamento = ?")
        args.append(str(relacionamento).strip()[:80] or None)
    if aniversario is not None:
        raw = str(aniversario).strip()
        if raw and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
            raise ValueError("aniversário inválido")
        sets.append("perfil_aniversario = ?")
        args.append(raw or None)
    if times_ids is not None:
        from src.clubes_catalogo import carregar_clubes

        valid = {c["id"] for c in carregar_clubes() if c.get("tem_emblema")}
        cleaned: list[str] = []
        for tid in times_ids:
            s = str(tid or "").strip()
            if s in valid and s not in cleaned:
                cleaned.append(s)
            if len(cleaned) >= PERFIL_TIMES_MAX:
                break
        sets.append("times_json = ?")
        args.append(json.dumps(cleaned, ensure_ascii=False))
    if banner_preset is not None:
        preset = str(banner_preset).strip().lower()
        if preset not in BANNER_PRESETS:
            raise ValueError("banner inválido")
        sets.append("banner_preset = ?")
        args.append(preset)
        if clear_banner_custom:
            sets.append("banner_path = NULL")
    elif clear_banner_custom:
        sets.append("banner_path = NULL")
    if not sets:
        return
    args.append(int(participante_id))
    with get_db() as conn:
        conn.execute(
            f"UPDATE participantes SET {', '.join(sets)} WHERE id = ?",
            args,
        )


def salvar_sidebar_ordem(
    participante_id: int,
    *,
    scope: str,
    ordem: list[str],
) -> dict[str, list[str]]:
    """Persiste ordem dos submenus arrastáveis (site/admin) no participante."""
    import json

    escopo = (scope or "").strip().lower()
    if escopo not in {"site", "admin"}:
        raise ValueError("escopo inválido")
    if not isinstance(ordem, list):
        raise ValueError("ordem inválida")
    limpa: list[str] = []
    for item in ordem:
        s = str(item or "").strip()
        if not s or s in limpa:
            continue
        if len(s) > 64:
            continue
        limpa.append(s)
        if len(limpa) >= 40:
            break

    with get_db() as conn:
        row = conn.execute(
            "SELECT sidebar_ordem_json FROM participantes WHERE id = ?",
            (int(participante_id),),
        ).fetchone()
        if not row:
            raise ValueError("participante inválido")
        atual: dict[str, Any] = {}
        raw = row["sidebar_ordem_json"] if row else None
        if raw:
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    atual = parsed
            except (TypeError, json.JSONDecodeError):
                atual = {}
        atual[escopo] = limpa
        conn.execute(
            "UPDATE participantes SET sidebar_ordem_json = ? WHERE id = ?",
            (json.dumps(atual, ensure_ascii=False), int(participante_id)),
        )
    return {k: list(v) for k, v in atual.items() if isinstance(v, list)}


def salvar_banner(participante_id: int, relative_path: str | None) -> None:
    with get_db() as conn:
        conn.execute(
            "UPDATE participantes SET banner_path = ? WHERE id = ?",
            (relative_path, int(participante_id)),
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


def set_inicio_jogo(
    jogo_id: int,
    inicio_em: str | None,
    *,
    permitir_confirmado: bool = False,
) -> None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT confirmado_em FROM jogos WHERE id = ?", (jogo_id,)
        ).fetchone()
        if not row:
            raise ValueError("jogo não encontrado")
        if not permitir_confirmado and (row["confirmado_em"] or "").strip():
            raise ValueError("jogo confirmado — desfaça a confirmação para alterar")
        conn.execute(
            "UPDATE jogos SET inicio_em = ? WHERE id = ?",
            (inicio_em, jogo_id),
        )


def proximo_confronto_id() -> int:
    with get_db() as conn:
        row = conn.execute("SELECT COALESCE(MAX(id), 0) AS m FROM confrontos").fetchone()
        return int(row["m"] or 0) + 1


def criar_confronto(
    fase: str,
    clube_a: str,
    clube_b: str,
    *,
    confronto_id: int | None = None,
    ida_em: str | None = None,
    volta_em: str | None = None,
) -> int:
    """Cria chave + jogos ida/volta. Mandante ida=a, volta=b."""
    from src.config import FASE_IDS

    if fase not in FASE_IDS:
        raise ValueError("fase inválida")
    a = (clube_a or "").strip()
    b = (clube_b or "").strip()
    if not a or not b or a == b:
        raise ValueError("clubes inválidos")
    cid = confronto_id or proximo_confronto_id()
    with get_db() as conn:
        conn.execute(
            "INSERT INTO confrontos (id, fase, clube_a, clube_b) VALUES (?, ?, ?, ?)",
            (cid, fase, a, b),
        )
        conn.execute(
            "INSERT INTO jogos (confronto_id, perna, mandante_clube_id, inicio_em) "
            "VALUES (?, 'ida', 'a', ?)",
            (cid, ida_em),
        )
        conn.execute(
            "INSERT INTO jogos (confronto_id, perna, mandante_clube_id, inicio_em) "
            "VALUES (?, 'volta', 'b', ?)",
            (cid, volta_em),
        )
    return cid


def substituir_confrontos_fase(
    fase: str,
    pares: list[dict[str, Any]],
) -> list[int]:
    """Apaga confrontos da fase e recria a partir de pares.

    Cada item: {clube_a, clube_b, ida_em?, volta_em?}.
    Remove palpites ligados aos jogos/confrontos antigos (senão o DELETE
    estoura FK e o Remontar falha depois que alguém já palpitou).
    """
    from src.config import FASE_IDS

    if fase not in FASE_IDS:
        raise ValueError("fase inválida")
    if fase == "oitavas":
        raise ValueError("oitavas não podem ser remontadas por aqui")
    ids: list[int] = []
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id FROM confrontos WHERE fase = ?", (fase,)
        ).fetchall()
        for r in rows:
            cid = int(r["id"])
            jogo_ids = [
                int(j["id"])
                for j in conn.execute(
                    "SELECT id FROM jogos WHERE confronto_id = ?", (cid,)
                ).fetchall()
            ]
            if jogo_ids:
                placeholders = ",".join("?" * len(jogo_ids))
                conn.execute(
                    f"DELETE FROM palpites_jogo WHERE jogo_id IN ({placeholders})",
                    jogo_ids,
                )
            conn.execute(
                "DELETE FROM palpites_penaltis WHERE confronto_id = ?", (cid,)
            )
            conn.execute("DELETE FROM jogos WHERE confronto_id = ?", (cid,))
            conn.execute("DELETE FROM confrontos WHERE id = ?", (cid,))
        next_id = int(
            conn.execute("SELECT COALESCE(MAX(id), 0) AS m FROM confrontos").fetchone()[
                "m"
            ]
            or 0
        )
        for par in pares:
            a = (par.get("clube_a") or "").strip()
            b = (par.get("clube_b") or "").strip()
            if not a or not b or a == b:
                raise ValueError("par inválido")
            next_id += 1
            conn.execute(
                "INSERT INTO confrontos (id, fase, clube_a, clube_b) VALUES (?, ?, ?, ?)",
                (next_id, fase, a, b),
            )
            conn.execute(
                "INSERT INTO jogos (confronto_id, perna, mandante_clube_id, inicio_em) "
                "VALUES (?, 'ida', 'a', ?)",
                (next_id, par.get("ida_em")),
            )
            conn.execute(
                "INSERT INTO jogos (confronto_id, perna, mandante_clube_id, inicio_em) "
                "VALUES (?, 'volta', 'b', ?)",
                (next_id, par.get("volta_em")),
            )
            ids.append(next_id)
        if fase == "quartas":
            _migrate_quartas_ordem_casa(conn)
    return ids


def inverter_mandantes_confronto(confronto_id: int) -> dict[str, Any]:
    """Troca clube_a ↔ clube_b (quem manda na ida / decide na volta).

    Bloqueado se algum jogo já estiver confirmado.
    """
    with get_db() as conn:
        c = conn.execute(
            "SELECT * FROM confrontos WHERE id = ?", (confronto_id,)
        ).fetchone()
        if not c:
            raise ValueError("confronto não encontrado")
        if c["fase"] == "oitavas":
            raise ValueError("oitavas não podem ser invertidas por aqui")
        jogos = conn.execute(
            "SELECT * FROM jogos WHERE confronto_id = ?", (confronto_id,)
        ).fetchall()
        for j in jogos:
            if j["confirmado_em"]:
                raise ValueError(
                    "Desfaça a confirmação dos placares antes de inverter o mando"
                )
        a, b = c["clube_a"], c["clube_b"]
        conn.execute(
            "UPDATE confrontos SET clube_a = ?, clube_b = ? WHERE id = ?",
            (b, a, confronto_id),
        )
        return {"id": confronto_id, "clube_a": b, "clube_b": a, "fase": c["fase"]}


def classificados_da_fase(fase: str) -> list[dict[str, Any]]:
    """Vencedores oficiais das chaves da fase (agregado + pênaltis)."""
    from src.scoring import quem_classifica_agregado

    out: list[dict[str, Any]] = []
    for c in list_confrontos_completos(fase):
        jogos = {j["perna"]: j for j in c.get("jogos") or []}
        ida = jogos.get("ida")
        volta = jogos.get("volta")
        if not ida or not volta:
            continue
        if (
            ida.get("gols_mandante") is None
            or ida.get("gols_visitante") is None
            or volta.get("gols_mandante") is None
            or volta.get("gols_visitante") is None
        ):
            continue
        lado = quem_classifica_agregado(
            int(ida["gols_mandante"]),
            int(ida["gols_visitante"]),
            int(volta["gols_mandante"]),
            int(volta["gols_visitante"]),
            penaltis_clube_id=volta.get("penaltis_clube_id"),
        )
        if lado not in ("a", "b"):
            continue
        clube = c["clube_a"] if lado == "a" else c["clube_b"]
        out.append(
            {
                "confronto_id": c["id"],
                "clube": clube,
                "lado": lado,
                "fase": fase,
            }
        )
    return out


def get_jogo(jogo_id: int) -> dict[str, Any] | None:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM jogos WHERE id = ?", (jogo_id,)).fetchone()
        return dict(row) if row else None


def jogo_confirmado(jogo: dict[str, Any] | None) -> bool:
    if not jogo:
        return False
    return bool((jogo.get("confirmado_em") or "").strip())


def set_resultado_jogo(
    jogo_id: int,
    gols_mandante: int,
    gols_visitante: int,
    penaltis_clube_id: str | None = None,
    *,
    permitir_confirmado: bool = False,
) -> None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT confirmado_em FROM jogos WHERE id = ?", (jogo_id,)
        ).fetchone()
        if not row:
            raise ValueError("jogo não encontrado")
        if not permitir_confirmado and (row["confirmado_em"] or "").strip():
            raise ValueError("jogo confirmado — desfaça a confirmação para alterar")
        conn.execute(
            "UPDATE jogos SET gols_mandante = ?, gols_visitante = ?, penaltis_clube_id = ? "
            "WHERE id = ?",
            (gols_mandante, gols_visitante, penaltis_clube_id, jogo_id),
        )


def confirmar_jogo(jogo_id: int) -> dict[str, Any]:
    """Trava o placar oficial do jogo. Exige gols preenchidos."""
    with get_db() as conn:
        row = conn.execute("SELECT * FROM jogos WHERE id = ?", (jogo_id,)).fetchone()
        if not row:
            raise ValueError("jogo não encontrado")
        if row["gols_mandante"] is None or row["gols_visitante"] is None:
            raise ValueError("salve o placar antes de confirmar")
        if (row["confirmado_em"] or "").strip():
            return dict(row)
        conn.execute(
            "UPDATE jogos SET confirmado_em = datetime('now', 'localtime') WHERE id = ?",
            (jogo_id,),
        )
        out = conn.execute("SELECT * FROM jogos WHERE id = ?", (jogo_id,)).fetchone()
        return dict(out) if out else dict(row)


def desfazer_confirmacao_jogo(jogo_id: int) -> dict[str, Any]:
    """Reabre edição do placar oficial."""
    with get_db() as conn:
        row = conn.execute("SELECT * FROM jogos WHERE id = ?", (jogo_id,)).fetchone()
        if not row:
            raise ValueError("jogo não encontrado")
        conn.execute(
            "UPDATE jogos SET confirmado_em = NULL WHERE id = ?", (jogo_id,)
        )
        out = conn.execute("SELECT * FROM jogos WHERE id = ?", (jogo_id,)).fetchone()
        return dict(out) if out else dict(row)


def confirmar_jogos_da_fase(fase: str) -> int:
    """Confirma todos os jogos da fase que já têm placar. Retorna quantos travou."""
    with get_db() as conn:
        cur = conn.execute(
            "UPDATE jogos SET confirmado_em = datetime('now', 'localtime') "
            "WHERE id IN ("
            "  SELECT j.id FROM jogos j "
            "  JOIN confrontos c ON c.id = j.confronto_id "
            "  WHERE c.fase = ? "
            "  AND j.gols_mandante IS NOT NULL AND j.gols_visitante IS NOT NULL "
            "  AND (j.confirmado_em IS NULL OR j.confirmado_em = '')"
            ")",
            (fase,),
        )
        return int(cur.rowcount or 0)


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
            "OR j.penaltis_clube_id IS NOT NULL OR j.confirmado_em IS NOT NULL)",
            (fase, perna),
        ).fetchall()
        n = len(rows)
        conn.execute(
            "UPDATE jogos SET gols_mandante = NULL, gols_visitante = NULL, "
            "penaltis_clube_id = NULL, confirmado_em = NULL "
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


def list_xonha_eventos(*, com_motivo: bool = True) -> list[dict[str, Any]]:
    """Lista eventos do Xonhômetro (mais recente primeiro).

    ``com_motivo=False`` evita carregar textos longos — útil para stats/resumo
    da página pública (a timeline completa vem sob demanda).
    """
    cols = "id, tipo, data, hora, criado_em"
    if com_motivo:
        cols += ", motivo"
    with get_db() as conn:
        rows = conn.execute(
            f"SELECT {cols} "
            "FROM xonha_eventos "
            "ORDER BY data DESC, COALESCE(hora, '') DESC, id DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def list_xonha_eventos_ano(ano: str, *, com_motivo: bool = True) -> list[dict[str, Any]]:
    """Eventos de um ano (mais recente primeiro) — payload do admin sob demanda."""
    ano_s = str(ano or "").strip()
    if len(ano_s) != 4 or not ano_s.isdigit():
        return []
    cols = "id, tipo, data, hora, criado_em"
    if com_motivo:
        cols += ", motivo"
    with get_db() as conn:
        rows = conn.execute(
            f"SELECT {cols} "
            "FROM xonha_eventos "
            "WHERE substr(data, 1, 4) = ? "
            "ORDER BY data DESC, COALESCE(hora, '') DESC, id DESC",
            (ano_s,),
        ).fetchall()
        return [dict(r) for r in rows]


def agrupar_xonha_eventos_por_ano(
    eventos: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Agrupa eventos por ano (mais recente primeiro).

    Dentro de cada ano, devolve ordem cronológica (antigo → novo) para a
    linha do tempo horizontal.
    """
    itens = eventos if eventos is not None else list_xonha_eventos()
    por_ano: dict[str, list[dict[str, Any]]] = {}
    for ev in itens:
        data = str(ev.get("data") or "")
        ano = data[:4]
        if len(ano) != 4 or not ano.isdigit():
            continue
        por_ano.setdefault(ano, []).append(ev)

    grupos: list[dict[str, Any]] = []
    for ano in sorted(por_ano.keys(), reverse=True):
        # list_xonha_eventos vem DESC; inverte para a timeline (esquerda = mais antigo)
        cronologicos = list(reversed(por_ano[ano]))
        grupos.append(
            {
                "ano": ano,
                "eventos": cronologicos,
                "quantidade": len(cronologicos),
            }
        )
    return grupos


def resumo_xonha_anos(
    eventos: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Só ano + quantidade (HTML inicial leve, sem montar a timeline)."""
    return [
        {"ano": g["ano"], "quantidade": g["quantidade"]}
        for g in agrupar_xonha_eventos_por_ano(eventos)
    ]


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


def contar_xonha_eventos() -> int:
    with get_db() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM xonha_eventos").fetchone()
        return int(row["n"] if row else 0)


def importar_xonha_eventos_whatsapp(
    *,
    substituir: bool = True,
    path: Path | str | None = None,
) -> dict[str, Any]:
    """Importa saídas/voltas/banimentos inferidos do export WhatsApp.

    Com ``substituir=True`` (padrão), apaga os registros atuais e reinsere
    o histórico completo do JSON. Com ``False``, só insere origens novas.
    """
    from src.xonhometro_seed import carregar_eventos_import, caminho_import_padrao

    arquivo = Path(path) if path else caminho_import_padrao()
    eventos, meta = carregar_eventos_import(arquivo)
    if not eventos:
        raise ValueError("Nenhum evento válido no arquivo de importação.")

    inseridos = 0
    ignorados = 0
    with get_db() as conn:
        if substituir:
            conn.execute("DELETE FROM xonha_eventos")
        for ev in eventos:
            tipo = ev["tipo"]
            data = _validar_data_xonha(ev["data"])
            hora = _validar_hora_xonha(ev.get("hora"))
            motivo = (ev.get("motivo") or "").strip() or None
            if motivo and len(motivo) > 500:
                raise ValueError("Motivo muito longo (máx. 500).")
            origem = (ev.get("origem") or "").strip() or None
            if not substituir and origem:
                existe = conn.execute(
                    "SELECT 1 FROM xonha_eventos WHERE origem = ? LIMIT 1",
                    (origem,),
                ).fetchone()
                if existe:
                    ignorados += 1
                    continue
            try:
                conn.execute(
                    "INSERT INTO xonha_eventos (tipo, data, hora, motivo, origem) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (tipo, data, hora, motivo, origem),
                )
                inseridos += 1
            except sqlite3.IntegrityError:
                ignorados += 1

    return {
        "inseridos": inseridos,
        "ignorados": ignorados,
        "total_arquivo": len(eventos),
        "substituir": substituir,
        "meta": meta,
        "total_atual": contar_xonha_eventos(),
    }


def formatar_duracao(
    segundos: float | int,
    *,
    prefixo: str = "Há ",
    sufixo: str = "",
) -> str:
    """Duração legível com unidades compostas (ex.: 13 horas, 5 minutos e 9 segundos)."""
    total = max(int(segundos), 0)
    anos, rem = divmod(total, 31536000)
    meses, rem = divmod(rem, 2592000)
    dias, rem = divmod(rem, 86400)
    horas, rem = divmod(rem, 3600)
    minutos, segs = divmod(rem, 60)

    parts: list[str] = []

    def _add(n: int, um: str, varios: str) -> None:
        if n:
            parts.append(f"{n} {um if n == 1 else varios}")

    _add(anos, "ano", "anos")
    _add(meses, "mês", "meses")
    _add(dias, "dia", "dias")

    # Em minutos/horas+ sempre detalha até segundos (relógio ao vivo).
    if anos or meses or dias or horas:
        parts.append(f"{horas} {'hora' if horas == 1 else 'horas'}")
        parts.append(f"{minutos} {'minuto' if minutos == 1 else 'minutos'}")
        parts.append(f"{segs} {'segundo' if segs == 1 else 'segundos'}")
    elif minutos:
        parts.append(f"{minutos} {'minuto' if minutos == 1 else 'minutos'}")
        parts.append(f"{segs} {'segundo' if segs == 1 else 'segundos'}")
    else:
        parts.append(f"{segs} {'segundo' if segs == 1 else 'segundos'}")

    if len(parts) == 1:
        corpo = parts[0]
    elif len(parts) == 2:
        corpo = f"{parts[0]} e {parts[1]}"
    else:
        corpo = ", ".join(parts[:-1]) + f" e {parts[-1]}"
    return f"{prefixo}{corpo}{sufixo}"


def formatar_duracao_status(segundos: float | int) -> str:
    """Texto do relógio do status atual."""
    return formatar_duracao(segundos, prefixo="Há ", sufixo=" nesse status.")


def _xonha_evento_dt(e: dict[str, Any]) -> datetime | None:
    try:
        data = (e.get("data") or "")[:10]
        hora = (e.get("hora") or "00:00").strip()[:5]
        if len(hora) < 5:
            hora = "00:00"
        return datetime.strptime(f"{data} {hora}", "%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        return None


def xonha_stats(eventos: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Totais, médias, recorde do dia/mês e dias da semana mais frequentes.

    Aceita ``eventos`` já carregados para evitar um segundo SELECT na mesma
    request (motivos não são necessários para as estatísticas).
    """
    from datetime import date as date_cls

    if eventos is None:
        eventos = list_xonha_eventos(com_motivo=False)
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

    # Média de tempo entre sumiços (saída ou banimento)
    media_dias_entre_saidas: float | None = None
    media_tempo_entre_saidas_texto: str | None = None
    if len(fora_asc) >= 2:
        gaps_s: list[float] = []
        for prev, cur in zip(fora_asc, fora_asc[1:]):
            t0 = _xonha_evento_dt(prev)
            t1 = _xonha_evento_dt(cur)
            if t0 is None or t1 is None:
                continue
            gaps_s.append(abs((t1 - t0).total_seconds()))
        if gaps_s:
            media_s = sum(gaps_s) / len(gaps_s)
            media_dias_entre_saidas = round(media_s / 86400.0, 1)
            media_tempo_entre_saidas_texto = formatar_duracao(
                media_s, prefixo="", sufixo=""
            )

    media_saidas_por_mes: float | None = None
    media_saidas_por_dia: float | None = None
    if saidas_asc:
        d_first = datetime.strptime(saidas_asc[0]["data"][:10], "%Y-%m-%d").date()
        d_last = datetime.strptime(saidas_asc[-1]["data"][:10], "%Y-%m-%d").date()
        months = (d_last.year - d_first.year) * 12 + (d_last.month - d_first.month) + 1
        months = max(months, 1)
        media_saidas_por_mes = round(total_saidas / months, 2)

        # Mantido para compatibilidade (admin legado); UI pública usa recorde de permanência.
        hoje = date_cls.today()
        dias = max((hoje - d_first).days + 1, 1)
        media_saidas_por_dia = round(total_saidas / dias, 3)
    elif fora_asc:
        # Só banimentos: ainda dá pra estimar média mensal de "saídas" = 0
        pass

    # Recordes / ranking: saídas + banimentos (mesmo critério do placar)
    by_day: dict[str, dict[str, int]] = {}
    by_month: dict[str, dict[str, int]] = {}
    by_weekday: dict[int, dict[str, int]] = {
        i: {"saidas": 0, "banimentos": 0, "total": 0} for i in range(7)
    }
    by_ban_day: dict[str, int] = {}
    for e in fora_asc:
        day = (e.get("data") or "")[:10]
        if not day:
            continue
        tipo_e = e.get("tipo")
        key = "saidas" if tipo_e == "saida" else "banimentos"
        slot = by_day.setdefault(day, {"saidas": 0, "banimentos": 0, "total": 0})
        slot[key] += 1
        slot["total"] += 1
        ym = day[:7]
        mslot = by_month.setdefault(ym, {"saidas": 0, "banimentos": 0, "total": 0})
        mslot[key] += 1
        mslot["total"] += 1
        wd = datetime.strptime(day, "%Y-%m-%d").weekday()  # seg=0
        by_weekday[wd][key] += 1
        by_weekday[wd]["total"] += 1
        if tipo_e == "banimento":
            by_ban_day[day] = by_ban_day.get(day, 0) + 1

    def _pack_recorde_dia(day: str, slot: dict[str, int]) -> dict[str, Any]:
        return {
            "data": day,
            "quantidade": slot["total"],
            "saidas": slot["saidas"],
            "banimentos": slot["banimentos"],
        }

    recorde_dia: dict[str, Any] | None = None
    if by_day:
        best_day = max(
            by_day.items(), key=lambda kv: (kv[1]["total"], kv[0])
        )
        recorde_dia = _pack_recorde_dia(best_day[0], best_day[1])

    recorde_mes: dict[str, Any] | None = None
    if by_month:
        best_m = max(
            by_month.items(), key=lambda kv: (kv[1]["total"], kv[0])
        )
        y, m = best_m[0].split("-")
        slot = best_m[1]
        recorde_mes = {
            "ano_mes": best_m[0],
            "label": f"{_XONHA_MESES[int(m)]}/{y}",
            "quantidade": slot["total"],
            "saidas": slot["saidas"],
            "banimentos": slot["banimentos"],
        }

    recorde_banimento_dia: dict[str, Any] | None = None
    if by_ban_day:
        best_ban = max(by_ban_day.items(), key=lambda kv: (kv[1], kv[0]))
        recorde_banimento_dia = {
            "data": best_ban[0],
            "quantidade": best_ban[1],
        }

    # Todos os dias da semana, do mais movimentado ao menos
    max_wd = max((v["total"] for v in by_weekday.values()), default=0)
    dias_semana = []
    for wd, slot in sorted(
        by_weekday.items(), key=lambda kv: (-kv[1]["total"], kv[0])
    ):
        total_wd = slot["total"]
        bar_pct = round((total_wd / max_wd * 100), 1) if max_wd else 0.0
        saida_pct = (
            round(slot["saidas"] / total_wd * bar_pct, 1) if total_wd else 0.0
        )
        ban_pct = (
            round(slot["banimentos"] / total_wd * bar_pct, 1) if total_wd else 0.0
        )
        dias_semana.append(
            {
                "dia": _XONHA_DIAS_SEMANA[wd],
                "quantidade": total_wd,
                "saidas": slot["saidas"],
                "banimentos": slot["banimentos"],
                "weekday": wd,
                "bar_pct": bar_pct,
                "saida_pct": saida_pct,
                "ban_pct": ban_pct,
            }
        )

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
    ym_atual = hoje.strftime("%Y-%m")
    # Conta sumiços do mês (saídas + banimentos), alinhado ao placar
    saidas_mes_atual = sum(
        1 for e in fora_asc if (e.get("data") or "")[:7] == ym_atual
    )
    corte_30 = hoje.toordinal() - 29
    saidas_ultimos_30_dias = 0
    for e in fora_asc:
        day = (e.get("data") or "")[:10]
        if not day:
            continue
        try:
            if datetime.strptime(day, "%Y-%m-%d").date().toordinal() >= corte_30:
                saidas_ultimos_30_dias += 1
        except ValueError:
            continue

    dias_desde_ultima_saida: int | None = None
    tempo_desde_ultima_saida_texto: str | None = None
    if fora_asc:
        ult_fora = fora_asc[-1]
        d_ult = datetime.strptime(ult_fora["data"][:10], "%Y-%m-%d").date()
        dias_desde_ultima_saida = max((hoje - d_ult).days, 0)
        t_ult = _xonha_evento_dt(ult_fora)
        if t_ult is not None:
            tempo_desde_ultima_saida_texto = formatar_duracao(
                max((datetime.now() - t_ult).total_seconds(), 0),
                prefixo="",
                sufixo="",
            )

    dias_no_status_atual: int | None = None
    status_desde: str | None = None
    if ultimo and ultimo.get("data"):
        try:
            d_ult_ev = datetime.strptime(ultimo["data"][:10], "%Y-%m-%d").date()
            dias_no_status_atual = max((hoje - d_ult_ev).days, 0)
            hora = (ultimo.get("hora") or "00:00").strip()[:5]
            if len(hora) < 5:
                hora = "00:00"
            status_desde = f"{ultimo['data'][:10]}T{hora}:00"
        except ValueError:
            dias_no_status_atual = None
            status_desde = None

    status_duracao_texto: str | None = None
    if status_desde:
        try:
            t0 = datetime.strptime(status_desde, "%Y-%m-%dT%H:%M:%S")
            status_duracao_texto = formatar_duracao_status(
                (datetime.now() - t0).total_seconds()
            )
        except ValueError:
            status_duracao_texto = None

    # Pares saída/banimento → próxima volta (tempo fora)
    ordenados = sorted(eventos, key=_xonha_sort_key)
    tempos_fora_s: list[float] = []
    pendente_saida: dict[str, Any] | None = None
    for e in ordenados:
        tipo = e.get("tipo")
        if tipo in _XONHA_TIPOS_FORA:
            pendente_saida = e
        elif tipo == "volta" and pendente_saida is not None:
            t0 = _xonha_evento_dt(pendente_saida)
            t1 = _xonha_evento_dt(e)
            if t0 is not None and t1 is not None:
                delta_s = (t1 - t0).total_seconds()
                if delta_s > 0:
                    tempos_fora_s.append(delta_s)
            pendente_saida = None

    tempo_medio_fora_dias: float | None = None
    maior_tempo_fora_dias: float | None = None
    tempo_medio_fora_texto: str | None = None
    maior_tempo_fora_texto: str | None = None
    if tempos_fora_s:
        media_s = sum(tempos_fora_s) / len(tempos_fora_s)
        max_s = max(tempos_fora_s)
        tempo_medio_fora_dias = round(media_s / 86400.0, 2)
        maior_tempo_fora_dias = round(max_s / 86400.0, 2)
        tempo_medio_fora_texto = formatar_duracao(media_s, prefixo="", sufixo="")
        maior_tempo_fora_texto = formatar_duracao(max_s, prefixo="", sufixo="")

    # Recorde de permanência: maior tempo contínuo DENTRO (volta → próxima saída/ban)
    permanencias_s: list[float] = []
    pendente_volta: dict[str, Any] | None = None
    for e in ordenados:
        tipo = e.get("tipo")
        if tipo == "volta":
            pendente_volta = e
        elif tipo in _XONHA_TIPOS_FORA and pendente_volta is not None:
            t0 = _xonha_evento_dt(pendente_volta)
            t1 = _xonha_evento_dt(e)
            if t0 is not None and t1 is not None:
                delta_s = (t1 - t0).total_seconds()
                if delta_s > 0:
                    permanencias_s.append(delta_s)
            pendente_volta = None
    if pendente_volta is not None and status == "dentro":
        t0 = _xonha_evento_dt(pendente_volta)
        if t0 is not None:
            delta_s = (datetime.now() - t0).total_seconds()
            if delta_s > 0:
                permanencias_s.append(delta_s)

    recorde_permanencia_dias: float | None = None
    recorde_permanencia_texto: str | None = None
    if permanencias_s:
        max_perm = max(permanencias_s)
        recorde_permanencia_dias = round(max_perm / 86400.0, 2)
        recorde_permanencia_texto = formatar_duracao(max_perm, prefixo="", sufixo="")

    by_hour: dict[int, int] = {}
    for e in fora_asc:
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
        "media_tempo_entre_saidas_texto": media_tempo_entre_saidas_texto,
        "recorde_dia": recorde_dia,
        "recorde_mes": recorde_mes,
        "recorde_banimento_dia": recorde_banimento_dia,
        "dias_semana": dias_semana,
        "status": status,
        "ultimo_evento": ultimo,
        "saidas_mes_atual": saidas_mes_atual,
        "saidas_ultimos_30_dias": saidas_ultimos_30_dias,
        "dias_desde_ultima_saida": dias_desde_ultima_saida,
        "tempo_desde_ultima_saida_texto": tempo_desde_ultima_saida_texto,
        "dias_no_status_atual": dias_no_status_atual,
        "status_desde": status_desde,
        "status_duracao_texto": status_duracao_texto,
        "tempo_medio_fora_dias": tempo_medio_fora_dias,
        "maior_tempo_fora_dias": maior_tempo_fora_dias,
        "tempo_medio_fora_texto": tempo_medio_fora_texto,
        "maior_tempo_fora_texto": maior_tempo_fora_texto,
        "recorde_permanencia_dias": recorde_permanencia_dias,
        "recorde_permanencia_texto": recorde_permanencia_texto,
        "horario_mais_comum": horario_mais_comum,
        "taxa_retorno": taxa_retorno,
        "recorde_paz_dias": recorde_paz_dias,
    }


# --- Listra THDFM -----------------------------------------------------------

_LISTRA_FRASE_COLS = (
    "id, texto, responsavel, criado_por_id, criado_em, ordem, ano, emoji, destaque"
)


def split_leading_emoji(texto: str) -> tuple[str, str]:
    """Separa emoji inicial (estilo Listra 2025) do restante do texto."""
    t = (texto or "").strip()
    if not t:
        return "", ""
    parts = t.split(None, 1)
    head = parts[0]
    rest = parts[1] if len(parts) > 1 else ""
    # Token sem letra/dígito ASCII e com caractere não-ASCII → trata como emoji.
    if any(c.isascii() and c.isalnum() for c in head):
        return "", t
    if all(ord(c) < 128 for c in head):
        return "", t
    return head, rest


def listra_emoji_efetivo(frase: dict[str, Any]) -> str:
    emoji = (frase.get("emoji") or "").strip()
    if emoji:
        return emoji
    legado, _ = split_leading_emoji(frase.get("texto") or "")
    return legado


def listra_texto_contexto(frase: dict[str, Any]) -> str:
    """Texto completo exibido na Listra (sem o emoji da coluna)."""
    texto = (frase.get("texto") or "").strip()
    emoji = (frase.get("emoji") or "").strip()
    if emoji:
        return texto
    _, resto = split_leading_emoji(texto)
    return resto or texto


def listra_trecho_compartilhar(frase: dict[str, Any]) -> str:
    """Trecho que vai no WhatsApp: destaque se houver, senão o texto de contexto."""
    destaque = (frase.get("destaque") or "").strip()
    if destaque:
        return destaque
    return listra_texto_contexto(frase)


def listra_linha_compartilhar(frase: dict[str, Any]) -> str:
    """Uma linha pronta para o export (sem o prefixo '* ')."""
    emoji = listra_emoji_efetivo(frase)
    trecho = listra_trecho_compartilhar(frase)
    if not trecho and not emoji:
        return ""
    if emoji and trecho:
        # Evita duplicar se o trecho já começa com o mesmo emoji.
        if trecho.startswith(emoji):
            return trecho
        return f"{emoji} {trecho}"
    return emoji or trecho


def listra_marcar_destaque_html(texto: str, destaque: str) -> str:
    """HTML escapado com o trecho compartilhável em <mark>."""
    import html as html_mod

    base = texto or ""
    dest = (destaque or "").strip()
    if not dest or dest not in base:
        return html_mod.escape(base)
    out: list[str] = []
    cursor = 0
    while True:
        idx = base.find(dest, cursor)
        if idx < 0:
            out.append(html_mod.escape(base[cursor:]))
            break
        out.append(html_mod.escape(base[cursor:idx]))
        out.append(f'<mark class="listra-destaque">{html_mod.escape(dest)}</mark>')
        cursor = idx + len(dest)
    return "".join(out)


def listra_frase_api(frase: dict[str, Any]) -> dict[str, Any]:
    """Payload JSON de uma frase (campos crus + derivados para o front)."""
    emoji = listra_emoji_efetivo(frase)
    texto_ctx = listra_texto_contexto(frase)
    destaque = (frase.get("destaque") or "").strip()
    return {
        "id": int(frase["id"]),
        "ano": int(frase["ano"]) if frase.get("ano") is not None else None,
        "texto": frase.get("texto") or "",
        "emoji": (frase.get("emoji") or "").strip(),
        "destaque": destaque,
        "responsavel": (frase.get("responsavel") or "").strip(),
        "criado_em": frase.get("criado_em") or "",
        "ordem": frase.get("ordem"),
        "emoji_efetivo": emoji,
        "texto_contexto": texto_ctx,
        "linha_share": listra_linha_compartilhar(frase),
        "texto_html": listra_marcar_destaque_html(texto_ctx, destaque),
    }


def _migrar_listra_emoji_destaque(conn: sqlite3.Connection) -> None:
    cols = {
        row[1] for row in conn.execute("PRAGMA table_info(listra_frases)").fetchall()
    }
    if "emoji" not in cols:
        conn.execute(
            "ALTER TABLE listra_frases ADD COLUMN emoji TEXT NOT NULL DEFAULT ''"
        )
    if "destaque" not in cols:
        conn.execute(
            "ALTER TABLE listra_frases ADD COLUMN destaque TEXT NOT NULL DEFAULT ''"
        )
    # Separa emoji embutido no texto (acervo 2025) para a coluna dedicada.
    rows = conn.execute(
        "SELECT id, texto, emoji FROM listra_frases "
        "WHERE (emoji IS NULL OR emoji = '') AND texto IS NOT NULL AND texto != ''"
    ).fetchall()
    for row in rows:
        emoji, resto = split_leading_emoji(row["texto"] or "")
        if not emoji:
            continue
        conn.execute(
            "UPDATE listra_frases SET emoji = ?, texto = ? WHERE id = ?",
            (emoji, resto or row["texto"], row["id"]),
        )


def _migrar_listra_emojis_do_seed(conn: sqlite3.Connection) -> None:
    """Preenche emoji vazio com o prefixo do seed (não sobrescreve o que já tem)."""
    from src.listra_seed import LISTRA_ANOS, listra_seed_por_ano

    for ano in LISTRA_ANOS:
        seed = listra_seed_por_ano(int(ano))
        for ordem, raw in enumerate(seed, start=1):
            emoji, texto_seed = split_leading_emoji(raw)
            if not emoji:
                continue
            texto_alvo = (texto_seed or raw).strip()
            row = conn.execute(
                "SELECT id, texto, emoji FROM listra_frases "
                "WHERE ano = ? AND (emoji IS NULL OR emoji = '') AND texto = ? "
                "LIMIT 1",
                (int(ano), texto_alvo),
            ).fetchone()
            if not row:
                row = conn.execute(
                    "SELECT id, texto, emoji FROM listra_frases "
                    "WHERE ano = ? AND ordem = ? LIMIT 1",
                    (int(ano), int(ordem)),
                ).fetchone()
            if not row or (row["emoji"] or "").strip():
                continue
            texto = row["texto"] or ""
            if texto.startswith(emoji + " ") or texto.startswith(emoji + "\n"):
                resto = texto[len(emoji) :].lstrip()
                conn.execute(
                    "UPDATE listra_frases SET emoji = ?, texto = ? WHERE id = ?",
                    (emoji, resto or texto, row["id"]),
                )
            else:
                conn.execute(
                    "UPDATE listra_frases SET emoji = ? WHERE id = ?",
                    (emoji, row["id"]),
                )


def _migrar_listra_reembolsos_itens(conn: sqlite3.Connection) -> None:
    """Separa 'lista dos reembilos' e 'blodo de notas' do aviso de reembolso."""
    rows = conn.execute(
        f"SELECT {_LISTRA_FRASE_COLS} FROM listra_frases "
        "WHERE texto LIKE '%lista dos reembilos%' "
        "AND texto LIKE '%blodo de notas%' "
        "AND instr(texto, char(10) || '- ') > 0"
    ).fetchall()
    for row in rows:
        texto = row["texto"] or ""
        head: list[str] = []
        extras: list[str] = []
        for line in texto.split("\n"):
            if line.startswith("- "):
                item = line[2:].strip()
                if item:
                    extras.append(item)
            else:
                if extras:
                    # Linha depois de itens com "- ": mantém no último extra.
                    extras[-1] = f"{extras[-1]}\n{line}".strip()
                else:
                    head.append(line)
        if len(extras) < 2:
            continue
        parte1 = "\n".join(head).strip()
        if not parte1:
            continue
        ano = int(row["ano"])
        ordem = int(row["ordem"])
        conn.execute(
            "UPDATE listra_frases SET ordem = ordem + ? "
            "WHERE ano = ? AND ordem > ?",
            (len(extras), ano, ordem),
        )
        conn.execute(
            "UPDATE listra_frases SET texto = ? WHERE id = ?",
            (parte1, row["id"]),
        )
        for i, extra in enumerate(extras, start=1):
            conn.execute(
                "INSERT INTO listra_frases "
                "(texto, responsavel, criado_por_id, ordem, ano, criado_em, emoji, destaque) "
                "VALUES (?, ?, ?, ?, ?, ?, '', '')",
                (
                    extra,
                    row["responsavel"] or "",
                    row["criado_por_id"],
                    ordem + i,
                    ano,
                    row["criado_em"],
                ),
            )


def _migrar_listra_meliantes(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS listra_meliantes (
            nome TEXT PRIMARY KEY,
            criado_em TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
            participante_id INTEGER REFERENCES participantes(id)
        )
        """
    )
    cols = {
        row[1] for row in conn.execute("PRAGMA table_info(listra_meliantes)").fetchall()
    }
    if "participante_id" not in cols:
        conn.execute(
            "ALTER TABLE listra_meliantes ADD COLUMN participante_id INTEGER "
            "REFERENCES participantes(id)"
        )
    rows = conn.execute(
        "SELECT DISTINCT TRIM(responsavel) AS nome FROM listra_frases "
        "WHERE responsavel IS NOT NULL AND TRIM(responsavel) != ''"
    ).fetchall()
    for row in rows:
        nome = (row["nome"] or "").strip()
        if not nome:
            continue
        conn.execute(
            "INSERT OR IGNORE INTO listra_meliantes (nome, criado_em) "
            "VALUES (?, datetime('now', 'localtime'))",
            (nome,),
        )
    # Vincula meliantes livres a participantes liberados com o mesmo nome.
    conn.execute(
        """
        UPDATE listra_meliantes
        SET participante_id = (
          SELECT p.id FROM participantes p
          WHERE p.status = 'liberado'
            AND TRIM(p.nome) = listra_meliantes.nome COLLATE NOCASE
          ORDER BY p.id ASC
          LIMIT 1
        )
        WHERE participante_id IS NULL
        """
    )


def list_listra_meliantes() -> list[str]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT nome FROM listra_meliantes ORDER BY nome COLLATE NOCASE"
        ).fetchall()
        return [str(r["nome"]) for r in rows]


def list_listra_meliantes_detalhe() -> list[dict[str, Any]]:
    """Meliantes com contagem de frases e vínculo de participante."""
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT m.nome,
                   m.criado_em,
                   m.participante_id,
                   p.nome AS participante_nome,
                   p.username AS participante_username,
                   COALESCE(COUNT(f.id), 0) AS usos
            FROM listra_meliantes m
            LEFT JOIN participantes p ON p.id = m.participante_id
            LEFT JOIN listra_frases f
              ON TRIM(f.responsavel) = m.nome
            GROUP BY m.nome, m.criado_em, m.participante_id,
                     p.nome, p.username
            ORDER BY m.nome COLLATE NOCASE
            """
        ).fetchall()
        out: list[dict[str, Any]] = []
        for r in rows:
            d = dict(r)
            d["usos"] = int(d.get("usos") or 0)
            d["vinculado"] = bool(d.get("participante_id"))
            out.append(d)
        return out


def list_participantes_candidatos_meliante() -> list[dict[str, Any]]:
    """Liberados que ainda não estão no gestor de meliantes."""
    cols_p = ", ".join(f"p.{c.strip()}" for c in _PARTICIPANTE_COLS.split(","))
    with get_db() as conn:
        rows = conn.execute(
            f"""
            SELECT {cols_p}
            FROM participantes p
            WHERE p.status = 'liberado'
              AND NOT EXISTS (
                SELECT 1 FROM listra_meliantes m
                WHERE m.participante_id = p.id
                   OR m.nome = p.nome COLLATE NOCASE
              )
            ORDER BY p.nome COLLATE NOCASE
            """
        ).fetchall()
        return [dict(r) for r in rows]


def list_participantes_para_vincular_meliante() -> list[dict[str, Any]]:
    """Liberados ainda sem vínculo de meliante (para link manual)."""
    cols_p = ", ".join(f"p.{c.strip()}" for c in _PARTICIPANTE_COLS.split(","))
    with get_db() as conn:
        rows = conn.execute(
            f"""
            SELECT {cols_p}
            FROM participantes p
            WHERE p.status = 'liberado'
              AND NOT EXISTS (
                SELECT 1 FROM listra_meliantes m
                WHERE m.participante_id = p.id
              )
            ORDER BY p.nome COLLATE NOCASE
            """
        ).fetchall()
        return [dict(r) for r in rows]


def ensure_listra_meliante(nome: str) -> str:
    """Registra o meliante (se novo) e devolve o nome normalizado."""
    nome_ok = re.sub(r"\s+", " ", (nome or "").strip())
    if not nome_ok:
        return ""
    if len(nome_ok) > NOME_MAX_LEN:
        raise ValueError(f"Meliante com no máximo {NOME_MAX_LEN} caracteres.")
    with get_db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO listra_meliantes (nome, criado_em) "
            "VALUES (?, datetime('now', 'localtime'))",
            (nome_ok,),
        )
        # Se já existe participante liberado com esse nome, vincula.
        conn.execute(
            """
            UPDATE listra_meliantes
            SET participante_id = (
              SELECT p.id FROM participantes p
              WHERE p.status = 'liberado'
                AND TRIM(p.nome) = listra_meliantes.nome COLLATE NOCASE
              ORDER BY p.id ASC
              LIMIT 1
            )
            WHERE nome = ? COLLATE NOCASE
              AND participante_id IS NULL
            """,
            (nome_ok,),
        )
    return nome_ok


def criar_listra_meliante(
    nome: str = "",
    *,
    participante_id: int | None = None,
) -> str:
    """Cadastra meliante livre ou a partir de um participante liberado."""
    if participante_id is not None:
        part = get_participante(int(participante_id))
        if not part or part.get("status") != "liberado":
            raise ValueError("Participante inválido para meliante.")
        nome_ok = re.sub(r"\s+", " ", (part.get("nome") or "").strip())
        if not nome_ok:
            raise ValueError("Participante sem nome.")
        with get_db() as conn:
            existe = conn.execute(
                "SELECT 1 FROM listra_meliantes "
                "WHERE participante_id = ? OR nome = ? COLLATE NOCASE "
                "LIMIT 1",
                (int(participante_id), nome_ok),
            ).fetchone()
            if existe:
                raise ValueError("Esse meliante já está cadastrado.")
            conn.execute(
                "INSERT INTO listra_meliantes (nome, criado_em, participante_id) "
                "VALUES (?, datetime('now', 'localtime'), ?)",
                (nome_ok, int(participante_id)),
            )
        return nome_ok

    nome_ok = re.sub(r"\s+", " ", (nome or "").strip())
    if not nome_ok:
        raise ValueError("Informe o nome do meliante.")
    if len(nome_ok) > NOME_MAX_LEN:
        raise ValueError(f"Meliante com no máximo {NOME_MAX_LEN} caracteres.")
    with get_db() as conn:
        existe = conn.execute(
            "SELECT 1 FROM listra_meliantes WHERE nome = ? COLLATE NOCASE LIMIT 1",
            (nome_ok,),
        ).fetchone()
        if existe:
            raise ValueError("Esse meliante já está cadastrado.")
        # Se houver usuário liberado com o mesmo nome, vincula automaticamente.
        part = conn.execute(
            "SELECT id FROM participantes "
            "WHERE status = 'liberado' AND nome = ? COLLATE NOCASE "
            "ORDER BY id ASC LIMIT 1",
            (nome_ok,),
        ).fetchone()
        pid = int(part["id"]) if part else None
        conn.execute(
            "INSERT INTO listra_meliantes (nome, criado_em, participante_id) "
            "VALUES (?, datetime('now', 'localtime'), ?)",
            (nome_ok, pid),
        )
    return nome_ok


def apagar_listra_meliante(nome: str) -> bool:
    """Remove o meliante da lista (frases existentes mantêm o nome)."""
    nome_ok = re.sub(r"\s+", " ", (nome or "").strip())
    if not nome_ok:
        return False
    with get_db() as conn:
        cur = conn.execute(
            "DELETE FROM listra_meliantes WHERE nome = ? COLLATE NOCASE",
            (nome_ok,),
        )
        return cur.rowcount > 0


def vincular_listra_meliante(nome: str, participante_id: int) -> str:
    """Associa manualmente um meliante existente a um usuário liberado."""
    nome_ok = re.sub(r"\s+", " ", (nome or "").strip())
    if not nome_ok:
        raise ValueError("Meliante não encontrado.")
    part = get_participante(int(participante_id))
    if not part or part.get("status") != "liberado":
        raise ValueError("Participante inválido para vínculo.")
    with get_db() as conn:
        mel = conn.execute(
            "SELECT nome, participante_id FROM listra_meliantes "
            "WHERE nome = ? COLLATE NOCASE LIMIT 1",
            (nome_ok,),
        ).fetchone()
        if not mel:
            raise ValueError("Meliante não encontrado.")
        if mel["participante_id"]:
            raise ValueError("Esse meliante já está vinculado a um usuário.")
        ocupado = conn.execute(
            "SELECT nome FROM listra_meliantes WHERE participante_id = ? LIMIT 1",
            (int(participante_id),),
        ).fetchone()
        if ocupado:
            raise ValueError(
                f"O usuário já está vinculado ao meliante {ocupado['nome']}."
            )
        conn.execute(
            "UPDATE listra_meliantes SET participante_id = ? "
            "WHERE nome = ? COLLATE NOCASE",
            (int(participante_id), nome_ok),
        )
    return str(mel["nome"])


def desvincular_listra_meliante(nome: str) -> str:
    """Remove o vínculo com usuário, mantendo o meliante como nome livre."""
    nome_ok = re.sub(r"\s+", " ", (nome or "").strip())
    if not nome_ok:
        raise ValueError("Meliante não encontrado.")
    with get_db() as conn:
        mel = conn.execute(
            "SELECT nome, participante_id FROM listra_meliantes "
            "WHERE nome = ? COLLATE NOCASE LIMIT 1",
            (nome_ok,),
        ).fetchone()
        if not mel:
            raise ValueError("Meliante não encontrado.")
        if not mel["participante_id"]:
            raise ValueError("Esse meliante já está livre.")
        conn.execute(
            "UPDATE listra_meliantes SET participante_id = NULL "
            "WHERE nome = ? COLLATE NOCASE",
            (nome_ok,),
        )
    return str(mel["nome"])


def list_listra_frases(ano: int | None = None) -> list[dict[str, Any]]:
    with get_db() as conn:
        if ano is None:
            rows = conn.execute(
                f"SELECT {_LISTRA_FRASE_COLS} FROM listra_frases "
                "ORDER BY ano DESC, ordem ASC, id ASC"
            ).fetchall()
        else:
            rows = conn.execute(
                f"SELECT {_LISTRA_FRASE_COLS} FROM listra_frases "
                "WHERE ano = ? ORDER BY ordem ASC, id ASC",
                (int(ano),),
            ).fetchall()
        return [dict(r) for r in rows]


def list_listra_por_anos(*, com_frases: bool = True) -> list[dict[str, Any]]:
    """Cards por ano: atual primeiro, depois os anteriores.

    ``com_frases=False`` devolve só cascas (ano/título/total) — first paint leve.
    """
    from src.listra_seed import LISTRA_ANO_ATUAL, LISTRA_ANOS, listra_titulo

    if not com_frases:
        return resumo_listra_anos()

    out: list[dict[str, Any]] = []
    for ano in LISTRA_ANOS:
        frases = list_listra_frases(ano)
        out.append(
            {
                "ano": ano,
                "titulo": listra_titulo(ano),
                "frases": frases,
                "total": len(frases),
                "atual": ano == LISTRA_ANO_ATUAL,
            }
        )
    return out


def resumo_listra_anos() -> list[dict[str, Any]]:
    """Só ano + título + quantidade (sem embutir as frases no HTML)."""
    from src.listra_seed import LISTRA_ANO_ATUAL, LISTRA_ANOS, listra_titulo

    with get_db() as conn:
        rows = conn.execute(
            "SELECT ano, COUNT(*) AS total FROM listra_frases GROUP BY ano"
        ).fetchall()
    counts = {int(r["ano"]): int(r["total"]) for r in rows}
    return [
        {
            "ano": ano,
            "titulo": listra_titulo(ano),
            "frases": [],
            "total": counts.get(int(ano), 0),
            "atual": ano == LISTRA_ANO_ATUAL,
        }
        for ano in LISTRA_ANOS
    ]


def listra_texto_whatsapp(
    frases: list[dict[str, Any]] | None = None,
    *,
    ano: int | None = None,
) -> str:
    """Export estilo Listra 2025: título + linhas `N. emoji frase`."""
    from src.listra_seed import LISTRA_ANO_ATUAL, listra_titulo

    if frases is None:
        ano_ok = int(ano) if ano is not None else LISTRA_ANO_ATUAL
        itens = list_listra_frases(ano_ok)
        titulo = listra_titulo(ano_ok)
    else:
        ano_ok = int(ano) if ano is not None else (
            int(frases[0]["ano"]) if frases and frases[0].get("ano") else LISTRA_ANO_ATUAL
        )
        itens = frases
        titulo = listra_titulo(ano_ok)
    linhas = [f"*{titulo}*", ""]
    n = 0
    for f in itens:
        linha = listra_linha_compartilhar(f)
        if not linha:
            continue
        n += 1
        for i, parte in enumerate(linha.splitlines()):
            parte = parte.strip()
            if not parte:
                continue
            if i == 0:
                linhas.append(f"{n}. {parte}")
            else:
                # Continuação de linha (frase multilinha): alinha sob o texto.
                linhas.append(f"   {parte}")
    return "\n".join(linhas).rstrip() + "\n"


def _eh_somente_emoji(valor: str) -> bool:
    """True se o valor for só emoji/símbolo (sem texto alfabético)."""
    if not valor:
        return True
    if re.search(r"[A-Za-z]", valor):
        return False
    for ch in valor:
        o = ord(ch)
        if o < 128:
            # Dígitos / # / * só entram em keycaps (1️⃣, #️⃣).
            if ch.isdigit() or ch in "#*":
                continue
            return False
    # Precisa de algum caractere de emoji/símbolo ou marcador de sequência.
    tem_emoji = False
    for ch in valor:
        o = ord(ch)
        cat = unicodedata.category(ch)
        if (
            o >= 0x2600
            or cat in ("So", "Sk")
            or ch in ("\u200d", "\ufe0e", "\ufe0f", "\u20e3")
            or 0x1F3FB <= o <= 0x1F3FF
        ):
            tem_emoji = True
            break
    return tem_emoji


def _normalizar_listra_emoji(emoji: str) -> str:
    emoji_ok = re.sub(r"\s+", "", (emoji or "").strip())
    if not emoji_ok:
        return ""
    if len(emoji_ok) > 16:
        raise ValueError("Emoji com no máximo 16 caracteres.")
    if not _eh_somente_emoji(emoji_ok):
        raise ValueError("O campo emoji aceita apenas emojis.")
    return emoji_ok


def _normalizar_listra_destaque(destaque: str, texto: str) -> str:
    dest_ok = re.sub(r"\s+\n", "\n", (destaque or "").strip())
    dest_ok = re.sub(r"[ \t]+", " ", dest_ok)
    if not dest_ok:
        return ""
    if len(dest_ok) > 500:
        raise ValueError("Trecho compartilhável com no máximo 500 caracteres.")
    # Aceita trecho mesmo fora do texto (usuário pode enxugar), mas recomenda
    # estar contido — só valida tamanho.
    _ = texto
    return dest_ok


def _normalizar_listra_frase_campos(
    texto: str,
    responsavel: str,
    *,
    emoji: str = "",
    destaque: str = "",
    exigir_responsavel: bool = True,
) -> tuple[str, str, str, str]:
    texto_ok = re.sub(r"\s+\n", "\n", (texto or "").strip())
    texto_ok = re.sub(r"[ \t]+", " ", texto_ok)
    if not texto_ok:
        raise ValueError("Informe a frase.")
    if len(texto_ok) > 2000:
        raise ValueError("Frase com no máximo 2000 caracteres.")
    resp_ok = re.sub(r"\s+", " ", (responsavel or "").strip())
    if exigir_responsavel and not resp_ok:
        raise ValueError("Informe o responsável.")
    if len(resp_ok) > NOME_MAX_LEN:
        raise ValueError(f"Responsável com no máximo {NOME_MAX_LEN} caracteres.")
    emoji_ok = _normalizar_listra_emoji(emoji)
    # Se colaram emoji no começo do texto e o campo emoji está vazio, separa.
    if not emoji_ok:
        emoji_ok, resto = split_leading_emoji(texto_ok)
        if emoji_ok:
            texto_ok = resto or texto_ok
    dest_ok = _normalizar_listra_destaque(destaque, texto_ok)
    return texto_ok, resp_ok, emoji_ok, dest_ok


def criar_listra_frase(
    texto: str,
    responsavel: str,
    *,
    criado_por_id: int | None = None,
    ano: int | None = None,
    emoji: str = "",
    destaque: str = "",
) -> dict[str, Any]:
    from src.listra_seed import LISTRA_ANO_ATUAL, LISTRA_ANOS

    texto_ok, resp_ok, emoji_ok, dest_ok = _normalizar_listra_frase_campos(
        texto, responsavel, emoji=emoji, destaque=destaque
    )
    if resp_ok:
        ensure_listra_meliante(resp_ok)
    ano_ok = int(ano) if ano is not None else LISTRA_ANO_ATUAL
    if ano_ok not in LISTRA_ANOS:
        raise ValueError("Ano inválido para a Listra.")
    with get_db() as conn:
        ordem = conn.execute(
            "SELECT COALESCE(MAX(ordem), 0) + 1 FROM listra_frases WHERE ano = ?",
            (ano_ok,),
        ).fetchone()[0]
        cur = conn.execute(
            "INSERT INTO listra_frases "
            "(texto, responsavel, criado_por_id, ordem, ano, criado_em, emoji, destaque) "
            "VALUES (?, ?, ?, ?, ?, datetime('now', 'localtime'), ?, ?)",
            (texto_ok, resp_ok, criado_por_id, ordem, ano_ok, emoji_ok, dest_ok),
        )
        row = conn.execute(
            f"SELECT {_LISTRA_FRASE_COLS} FROM listra_frases WHERE id = ?",
            (cur.lastrowid,),
        ).fetchone()
        return dict(row)


def get_listra_frase(frase_id: int) -> dict[str, Any] | None:
    with get_db() as conn:
        row = conn.execute(
            f"SELECT {_LISTRA_FRASE_COLS} FROM listra_frases WHERE id = ?",
            (frase_id,),
        ).fetchone()
        return dict(row) if row else None


def atualizar_listra_frase(
    frase_id: int,
    *,
    texto: str,
    responsavel: str,
    emoji: str = "",
    destaque: str = "",
) -> dict[str, Any]:
    if not get_listra_frase(frase_id):
        raise ValueError("Frase não encontrada.")
    # Responsável pode ficar vazio (volta a aparecer como Acervo do ano).
    texto_ok, resp_ok, emoji_ok, dest_ok = _normalizar_listra_frase_campos(
        texto,
        responsavel,
        emoji=emoji,
        destaque=destaque,
        exigir_responsavel=False,
    )
    if resp_ok:
        ensure_listra_meliante(resp_ok)
    with get_db() as conn:
        conn.execute(
            "UPDATE listra_frases SET texto = ?, responsavel = ?, emoji = ?, destaque = ? "
            "WHERE id = ?",
            (texto_ok, resp_ok, emoji_ok, dest_ok, frase_id),
        )
        row = conn.execute(
            f"SELECT {_LISTRA_FRASE_COLS} FROM listra_frases WHERE id = ?",
            (frase_id,),
        ).fetchone()
        return dict(row)


def apagar_listra_frase(frase_id: int) -> bool:
    with get_db() as conn:
        cur = conn.execute("DELETE FROM listra_frases WHERE id = ?", (frase_id,))
        return cur.rowcount > 0


def ultima_listra_frase() -> dict[str, Any] | None:
    """Frase mais recente do acervo (qualquer ano)."""
    with get_db() as conn:
        row = conn.execute(
            f"SELECT {_LISTRA_FRASE_COLS} FROM listra_frases "
            "ORDER BY datetime(criado_em) DESC, id DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None


def get_listra_permissao(participante_id: int) -> dict[str, Any]:
    with get_db() as conn:
        row = conn.execute(
            "SELECT participante_id, pode_adicionar, pode_enviar, atualizado_em "
            "FROM listra_permissoes WHERE participante_id = ?",
            (participante_id,),
        ).fetchone()
        if not row:
            return {
                "participante_id": participante_id,
                "pode_adicionar": False,
                "pode_enviar": False,
                "atualizado_em": None,
            }
        return {
            "participante_id": row["participante_id"],
            "pode_adicionar": bool(row["pode_adicionar"]),
            "pode_enviar": bool(row["pode_enviar"]),
            "atualizado_em": row["atualizado_em"],
        }


def list_listra_permissoes_com_participantes() -> list[dict[str, Any]]:
    """Participantes liberados + flags da Listra (para o painel admin)."""
    cols_p = ", ".join(f"p.{c.strip()}" for c in _PARTICIPANTE_COLS.split(","))
    with get_db() as conn:
        rows = conn.execute(
            f"""
            SELECT {cols_p},
                   COALESCE(lp.pode_adicionar, 0) AS pode_adicionar,
                   COALESCE(lp.pode_enviar, 0) AS pode_enviar
            FROM participantes p
            LEFT JOIN listra_permissoes lp ON lp.participante_id = p.id
            WHERE p.status = 'liberado'
            ORDER BY
              CASE WHEN p.admin_login IS NOT NULL AND p.admin_login != '' THEN 0 ELSE 1 END,
              p.nome COLLATE NOCASE
            """
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["pode_adicionar"] = bool(d.get("pode_adicionar"))
            d["pode_enviar"] = bool(d.get("pode_enviar"))
            out.append(d)
        return out


def salvar_listra_permissao(
    participante_id: int,
    *,
    pode_adicionar: bool,
    pode_enviar: bool,
) -> None:
    part = get_participante(participante_id)
    if not part:
        raise ValueError("Participante não encontrado.")
    if part.get("status") != "liberado":
        raise ValueError("Só participantes liberados recebem permissão da Listra.")
    with get_db() as conn:
        if not pode_adicionar and not pode_enviar:
            conn.execute(
                "DELETE FROM listra_permissoes WHERE participante_id = ?",
                (participante_id,),
            )
            return
        conn.execute(
            """
            INSERT INTO listra_permissoes
              (participante_id, pode_adicionar, pode_enviar, atualizado_em)
            VALUES (?, ?, ?, datetime('now', 'localtime'))
            ON CONFLICT(participante_id) DO UPDATE SET
              pode_adicionar = excluded.pode_adicionar,
              pode_enviar = excluded.pode_enviar,
              atualizado_em = datetime('now', 'localtime')
            """,
            (
                participante_id,
                1 if pode_adicionar else 0,
                1 if pode_enviar else 0,
            ),
        )


def salvar_listra_permissoes_lote(
    itens: list[tuple[int, bool, bool]],
) -> None:
    for pid, add, env in itens:
        salvar_listra_permissao(pid, pode_adicionar=add, pode_enviar=env)

KARMA_CATEGORIAS = ("confiavel", "legal", "sexy", "burro")


def salvar_karma_voto(
    voter_id: int,
    target_id: int,
    categoria: str,
    nivel: int,
) -> None:
    cat = (categoria or "").strip().lower()
    if cat not in KARMA_CATEGORIAS:
        raise ValueError("categoria inválida")
    n = int(nivel)
    if n < 1 or n > 3:
        raise ValueError("nível inválido")
    if int(voter_id) == int(target_id):
        raise ValueError("não pode votar no próprio karma")
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO perfil_karma_votos (voter_id, target_id, categoria, nivel, updated_at)
            VALUES (?, ?, ?, ?, datetime('now', 'localtime'))
            ON CONFLICT(voter_id, target_id, categoria) DO UPDATE SET
              nivel = excluded.nivel,
              updated_at = datetime('now', 'localtime')
            """,
            (int(voter_id), int(target_id), cat, n),
        )


def karma_resumo(target_id: int, voter_id: int | None = None) -> dict[str, Any]:
    """Médias arredondadas (0–3), contagens e voto do visitante."""
    tid = int(target_id)
    medias = {c: 0 for c in KARMA_CATEGORIAS}
    counts = {c: 0 for c in KARMA_CATEGORIAS}
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT categoria, AVG(nivel * 1.0) AS media, COUNT(*) AS n
            FROM perfil_karma_votos
            WHERE target_id = ?
            GROUP BY categoria
            """,
            (tid,),
        ).fetchall()
        for row in rows:
            cat = row["categoria"]
            if cat not in medias:
                continue
            n = int(row["n"] or 0)
            counts[cat] = n
            if n > 0:
                medias[cat] = int(max(0, min(3, round(float(row["media"])))))
        meu_voto: dict[str, int] = {}
        if voter_id is not None and int(voter_id) != tid:
            votos = conn.execute(
                """
                SELECT categoria, nivel FROM perfil_karma_votos
                WHERE target_id = ? AND voter_id = ?
                """,
                (tid, int(voter_id)),
            ).fetchall()
            for row in votos:
                meu_voto[row["categoria"]] = int(row["nivel"])
    return {
        "target_id": tid,
        "medias": medias,
        "counts": counts,
        "meu_voto": meu_voto if voter_id is not None and int(voter_id) != tid else None,
        "pode_votar": bool(voter_id is not None and int(voter_id) != tid),
    }


def salvar_nutela_voto(voter_id: int, target_id: int, valor: int) -> None:
    v = int(valor)
    if v < 0 or v > 100:
        raise ValueError("valor inválido")
    if int(voter_id) == int(target_id):
        raise ValueError("não pode votar no próprio nutella")
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO perfil_nutela_votos (voter_id, target_id, valor, updated_at)
            VALUES (?, ?, ?, datetime('now', 'localtime'))
            ON CONFLICT(voter_id, target_id) DO UPDATE SET
              valor = excluded.valor,
              updated_at = datetime('now', 'localtime')
            """,
            (int(voter_id), int(target_id), v),
        )


def nutela_resumo(target_id: int, voter_id: int | None = None) -> dict[str, Any]:
    """Média 0–100 (50 sem votos), contagem e voto do visitante."""
    tid = int(target_id)
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT AVG(valor * 1.0) AS media, COUNT(*) AS n
            FROM perfil_nutela_votos
            WHERE target_id = ?
            """,
            (tid,),
        ).fetchone()
        n = int(row["n"] or 0) if row else 0
        if n > 0:
            media = int(max(0, min(100, round(float(row["media"])))))
        else:
            media = 50
        meu_voto = None
        if voter_id is not None and int(voter_id) != tid:
            voto = conn.execute(
                """
                SELECT valor FROM perfil_nutela_votos
                WHERE target_id = ? AND voter_id = ?
                """,
                (tid, int(voter_id)),
            ).fetchone()
            if voto:
                meu_voto = int(voto["valor"])
    return {
        "target_id": tid,
        "media": media,
        "count": n,
        "meu_voto": meu_voto if voter_id is not None and int(voter_id) != tid else None,
        "pode_votar": bool(voter_id is not None and int(voter_id) != tid),
    }



PERFIL_RECADOS_MAX = 40
PERFIL_RECADOS_POR_PAGINA = 5
PERFIL_RECADO_RESPOSTAS_MAX = 30
RECADO_REACOES_EMOJI = (
    "👍",
    "❤️",
    "😂",
    "😮",
    "😢",
    "😡",
    "🔥",
    "👏",
    "🎉",
    "🙏",
)


def _normalizar_recado_emoji(emoji: str) -> str:
    em = (emoji or "").strip()
    if em not in RECADO_REACOES_EMOJI:
        raise ValueError("emoji inválido")
    return em


def reacoes_dos_recados(
    recado_ids: list[int],
    *,
    voter_id: int | None = None,
) -> dict[int, list[dict[str, Any]]]:
    """Agrega reações por recado: [{emoji, count, mine, autores}, ...] na ordem de aparição."""
    ids = [int(x) for x in recado_ids if x is not None]
    if not ids:
        return {}
    placeholders = ",".join("?" for _ in ids)
    with get_db() as conn:
        rows = conn.execute(
            f"""
            SELECT recado_id, emoji, COUNT(*) AS n,
                   MIN(criado_em) AS first_at,
                   MAX(CASE WHEN voter_id = ? THEN 1 ELSE 0 END) AS mine
            FROM perfil_recado_reacoes
            WHERE recado_id IN ({placeholders})
            GROUP BY recado_id, emoji
            ORDER BY first_at ASC, emoji ASC
            """,
            (int(voter_id) if voter_id else 0, *ids),
        ).fetchall()
        autor_rows = conn.execute(
            f"""
            SELECT r.recado_id, r.emoji, r.voter_id, p.nome, r.criado_em
            FROM perfil_recado_reacoes r
            JOIN participantes p ON p.id = r.voter_id
            WHERE r.recado_id IN ({placeholders})
            ORDER BY r.criado_em ASC, p.nome COLLATE NOCASE ASC
            """,
            (*ids,),
        ).fetchall()
    autores_map: dict[tuple[int, str], list[dict[str, Any]]] = {}
    for row in autor_rows:
        key = (int(row["recado_id"]), str(row["emoji"]))
        nome = (row["nome"] or "").strip() or "alguém"
        autores_map.setdefault(key, []).append(
            {"id": int(row["voter_id"]), "nome": nome}
        )
    out: dict[int, list[dict[str, Any]]] = {i: [] for i in ids}
    for row in rows:
        rid = int(row["recado_id"])
        emoji = str(row["emoji"])
        out.setdefault(rid, []).append(
            {
                "emoji": emoji,
                "count": int(row["n"] or 0),
                "mine": bool(row["mine"]),
                "autores": autores_map.get((rid, emoji), []),
            }
        )
    return out


def toggle_recado_reacao(
    recado_id: int,
    voter_id: int,
    emoji: str,
    *,
    target_id: int | None = None,
) -> list[dict[str, Any]]:
    """Liga/desliga a reação do votante; devolve o resumo do recado."""
    rid = int(recado_id)
    vid = int(voter_id)
    em = _normalizar_recado_emoji(emoji)
    voter = get_participante(vid)
    if not voter or voter.get("status") != "liberado":
        raise ValueError("votante inválido")
    with get_db() as conn:
        row = conn.execute(
            "SELECT id, target_id FROM perfil_recados WHERE id = ?",
            (rid,),
        ).fetchone()
        if not row:
            raise ValueError("recado não encontrado")
        if target_id is not None and int(row["target_id"]) != int(target_id):
            raise ValueError("recado não encontrado")
        existing = conn.execute(
            """
            SELECT id FROM perfil_recado_reacoes
            WHERE recado_id = ? AND voter_id = ? AND emoji = ?
            """,
            (rid, vid, em),
        ).fetchone()
        if existing:
            conn.execute("DELETE FROM perfil_recado_reacoes WHERE id = ?", (existing["id"],))
        else:
            conn.execute(
                """
                INSERT INTO perfil_recado_reacoes (recado_id, voter_id, emoji)
                VALUES (?, ?, ?)
                """,
                (rid, vid, em),
            )
    return reacoes_dos_recados([rid], voter_id=vid).get(rid, [])


def _apagar_arquivo_recado(midia_path: str | None) -> None:
    rel = (midia_path or "").strip()
    if not rel or "/" in rel or "\\" in rel or ".." in rel:
        return
    try:
        from src import config as cfg

        path = cfg.RECADOS_DIR / rel
        if path.is_file():
            path.unlink(missing_ok=True)
    except OSError:
        pass


def _recado_dict_from_row(
    row: sqlite3.Row,
    *,
    reacoes: list[dict[str, Any]] | None = None,
    respostas: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    keys = set(row.keys())
    nome = str(row["autor_nome"] if "autor_nome" in keys else "").strip() or "alguém"
    at = row["criado_em"] or ""
    if at and "T" not in str(at):
        at = str(at).replace(" ", "T", 1)
    rid = int(row["id"])
    parent_raw = row["parent_id"] if "parent_id" in keys else None
    avatar = row["autor_avatar"] if "autor_avatar" in keys else None
    return {
        "id": str(rid),
        "target_id": int(row["target_id"]),
        "autor_id": int(row["autor_id"]),
        "autor": nome,
        "avatar_path": avatar,
        "iniciais": (nome[:2] if nome else "??").upper(),
        "texto": row["texto"] or "",
        "midia_path": row["midia_path"] or None,
        "parent_id": str(int(parent_raw)) if parent_raw is not None else None,
        "at": at or None,
        "reacoes": reacoes or [],
        "respostas": respostas if respostas is not None else [],
    }


def contar_recados_raiz(target_id: int) -> int:
    tid = int(target_id)
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS n
            FROM perfil_recados
            WHERE target_id = ? AND parent_id IS NULL
            """,
            (tid,),
        ).fetchone()
    return int(row["n"] or 0) if row else 0


def listar_recados(
    target_id: int,
    *,
    limite: int = PERFIL_RECADOS_MAX,
    offset: int = 0,
    voter_id: int | None = None,
) -> list[dict[str, Any]]:
    tid = int(target_id)
    lim = max(1, min(int(limite), PERFIL_RECADOS_MAX))
    off = max(0, int(offset))
    with get_db() as conn:
        roots = conn.execute(
            """
            SELECT r.id, r.target_id, r.autor_id, r.texto, r.midia_path, r.parent_id, r.criado_em,
                   a.nome AS autor_nome, a.avatar_path AS autor_avatar
            FROM perfil_recados r
            JOIN participantes a ON a.id = r.autor_id
            WHERE r.target_id = ? AND r.parent_id IS NULL
            ORDER BY r.id DESC
            LIMIT ? OFFSET ?
            """,
            (tid, lim, off),
        ).fetchall()
        root_ids = [int(row["id"]) for row in roots]
        replies: list[sqlite3.Row] = []
        if root_ids:
            placeholders = ",".join("?" for _ in root_ids)
            replies = conn.execute(
                f"""
                SELECT r.id, r.target_id, r.autor_id, r.texto, r.midia_path, r.parent_id, r.criado_em,
                       a.nome AS autor_nome, a.avatar_path AS autor_avatar
                FROM perfil_recados r
                JOIN participantes a ON a.id = r.autor_id
                WHERE r.target_id = ? AND r.parent_id IN ({placeholders})
                ORDER BY r.id ASC
                """,
                (tid, *root_ids),
            ).fetchall()
    all_ids = root_ids + [int(row["id"]) for row in replies]
    reacoes_map = reacoes_dos_recados(all_ids, voter_id=voter_id)
    by_parent: dict[int, list[dict[str, Any]]] = {i: [] for i in root_ids}
    for row in replies:
        pid = int(row["parent_id"])
        by_parent.setdefault(pid, []).append(
            _recado_dict_from_row(
                row,
                reacoes=reacoes_map.get(int(row["id"]), []),
                respostas=[],
            )
        )
    out: list[dict[str, Any]] = []
    for row in roots:
        rid = int(row["id"])
        out.append(
            _recado_dict_from_row(
                row,
                reacoes=reacoes_map.get(rid, []),
                respostas=by_parent.get(rid, []),
            )
        )
    return out


def limpar_grid_progresso() -> int:
    """Apaga todo o progresso do Grid (ranking/streak)."""
    with get_db() as conn:
        cur = conn.execute("DELETE FROM grid_progresso")
        n = int(cur.rowcount or 0)
        conn.execute("DELETE FROM grid_partida")
        return n


def limpar_grid_progresso_dia(dia: str) -> int:
    """Apaga progresso e partidas do Grid de um dia (restore/regen com limpar)."""
    with get_db() as conn:
        cur = conn.execute(
            "DELETE FROM grid_progresso WHERE dia = ?",
            (str(dia),),
        )
        n = int(cur.rowcount or 0)
        cur2 = conn.execute(
            "DELETE FROM grid_partida WHERE dia = ?",
            (str(dia),),
        )
        n += int(cur2.rowcount or 0)
        return n


def parse_grid_virada(valor: str | int | None) -> tuple[int, int]:
    """Aceita 'HH:MM', 'H:MM', 'HH' ou int → (hora, minuto)."""
    if valor is None:
        return (0, 0)
    if isinstance(valor, bool):
        raise ValueError("hora da virada inválida")
    if isinstance(valor, int):
        if not 0 <= valor <= 23:
            raise ValueError("hora da virada deve ser entre 0 e 23")
        return (valor, 0)
    raw = str(valor).strip()
    if not raw:
        return (0, 0)
    if re.fullmatch(r"\d{1,2}", raw):
        h = int(raw)
        if not 0 <= h <= 23:
            raise ValueError("hora da virada deve ser entre 0 e 23")
        return (h, 0)
    m = re.fullmatch(r"(\d{1,2})\s*[:hH]\s*(\d{1,2})", raw)
    if not m:
        raise ValueError("use o formato HH:MM (ex.: 18:30)")
    h, mi = int(m.group(1)), int(m.group(2))
    if not 0 <= h <= 23 or not 0 <= mi <= 59:
        raise ValueError("hora inválida (0–23, minutos 0–59)")
    return (h, mi)


def format_grid_virada(hora: int, minuto: int = 0) -> str:
    return f"{int(hora):02d}:{int(minuto):02d}"


def get_grid_virada_hm() -> tuple[int, int]:
    """(hora, minuto) local da virada. Aceita meta legada só com hora."""
    raw = (get_meta("grid_virada_hora", "0") or "0").strip()
    try:
        return parse_grid_virada(raw)
    except ValueError:
        return (0, 0)


def get_grid_virada_hora() -> int:
    """Compat: só a hora (0–23)."""
    return get_grid_virada_hm()[0]


def set_grid_virada_hora(hora: int | str, minuto: int | None = None) -> str:
    """Grava virada como HH:MM. Retorna o rótulo salvo."""
    if minuto is not None:
        h, mi = int(hora), int(minuto)
        if not 0 <= h <= 23 or not 0 <= mi <= 59:
            raise ValueError("hora inválida (0–23, minutos 0–59)")
    else:
        h, mi = parse_grid_virada(hora)
    rotulo = format_grid_virada(h, mi)
    set_meta("grid_virada_hora", rotulo)
    return rotulo


def get_grid_salt(dia: str) -> str | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT salt FROM grid_puzzle_salt WHERE dia = ?",
            (str(dia),),
        ).fetchone()
        return str(row["salt"]) if row and row["salt"] else None


def set_grid_salt(dia: str, salt: str) -> str:
    dia_s = str(dia)
    salt_s = str(salt).strip()
    if not salt_s:
        raise ValueError("salt vazio")
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO grid_puzzle_salt (dia, salt, atualizado_em)
            VALUES (?, ?, datetime('now', 'localtime'))
            ON CONFLICT(dia) DO UPDATE SET
              salt = excluded.salt,
              atualizado_em = datetime('now', 'localtime')
            """,
            (dia_s, salt_s),
        )
    return salt_s


def clear_grid_salt(dia: str) -> bool:
    with get_db() as conn:
        cur = conn.execute(
            "DELETE FROM grid_puzzle_salt WHERE dia = ?",
            (str(dia),),
        )
        return int(cur.rowcount or 0) > 0


def listar_grid_dias(*, limite: int = 60) -> list[dict[str, Any]]:
    """Dias com pelo menos um jogo (progresso), no período do ranking; mais recentes primeiro.

    Dias só com salt/regen e sem jogadores não entram em “Dias com atividade”.
    """
    from src.grid_game import GRID_RANKING_DESDE

    lim = max(1, min(int(limite), 366))
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT dia,
                   COUNT(*) AS jogadores,
                   SUM(CASE WHEN finalizado = 1 THEN 1 ELSE 0 END) AS finalizados
            FROM grid_progresso
            WHERE dia >= ?
            GROUP BY dia
            HAVING COUNT(*) > 0
            ORDER BY dia DESC
            LIMIT ?
            """,
            (GRID_RANKING_DESDE, lim),
        ).fetchall()
        salts = {
            str(r["dia"]): str(r["salt"])
            for r in conn.execute(
                "SELECT dia, salt FROM grid_puzzle_salt WHERE dia >= ? ORDER BY dia DESC LIMIT ?",
                (GRID_RANKING_DESDE, lim),
            ).fetchall()
        }
    out: list[dict[str, Any]] = []
    for row in rows:
        dia = str(row["dia"])
        jogadores = int(row["jogadores"] or 0)
        if jogadores <= 0:
            continue
        out.append(
            {
                "dia": dia,
                "jogadores": jogadores,
                "finalizados": int(row["finalizados"] or 0),
                "salt": salts.get(dia),
                "regenerado": dia in salts,
            }
        )
    return out[:lim]


def listar_grid_progresso_dia(dia: str) -> list[dict[str, Any]]:
    """Respostas legadas (grid_progresso) de um dia — preferir partidas."""
    dia_s = str(dia)
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT g.participante_id, p.nome, p.avatar_path, p.username,
                   g.celulas_json, g.finalizado, g.atualizado_em
            FROM grid_progresso g
            JOIN participantes p ON p.id = g.participante_id
            WHERE g.dia = ?
            ORDER BY g.finalizado DESC, g.atualizado_em DESC, p.nome COLLATE NOCASE ASC
            """,
            (dia_s,),
        ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        try:
            celulas = json.loads(row["celulas_json"] or "[]")
        except json.JSONDecodeError:
            celulas = []
        ok, filled = _contar_celulas_ok(celulas)
        out.append(
            {
                "participante_id": int(row["participante_id"]),
                "nome": (row["nome"] or "").strip() or "alguém",
                "username": row["username"],
                "avatar_path": row["avatar_path"],
                "celulas": celulas,
                "finalizado": bool(row["finalizado"]),
                "atualizado_em": row["atualizado_em"],
                "celulas_ok": ok,
                "celulas_preenchidas": filled,
                "modo": "raiz",
                "modo_rotulo": "Pro",
                "indice_dia": 1,
            }
        )
    return out


def listar_grid_partidas_dia(dia: str) -> list[dict[str, Any]]:
    """Tentativas do dia (Pro + Contínuo) para o painel Mazeta, com tipo."""
    dia_s = str(dia)
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT g.id, g.participante_id, p.nome, p.avatar_path, p.username,
                   g.modo, g.celulas_json, g.finalizado, g.interrompido,
                   g.pontos, g.atualizado_em, g.criado_em
            FROM grid_partida g
            JOIN participantes p ON p.id = g.participante_id
            WHERE g.dia = ?
            ORDER BY g.criado_em ASC, g.id ASC
            """,
            (dia_s,),
        ).fetchall()
    # índice Contínuo por participante (ordem de criação no dia)
    contagem_xonha: dict[int, int] = {}
    out: list[dict[str, Any]] = []
    for row in rows:
        try:
            celulas = json.loads(row["celulas_json"] or "[]")
        except json.JSONDecodeError:
            celulas = []
        ok, filled = _contar_celulas_ok(celulas)
        modo = str(row["modo"] or "raiz")
        pid = int(row["participante_id"])
        if modo == "xonha":
            contagem_xonha[pid] = contagem_xonha.get(pid, 0) + 1
            indice = contagem_xonha[pid]
            modo_rotulo = f"Contínuo {indice}"
        else:
            indice = 1
            modo_rotulo = "Pro"
        status = "finalizado"
        if row["interrompido"]:
            status = "interrompido"
        elif not row["finalizado"]:
            status = "em andamento"
        out.append(
            {
                "partida_id": int(row["id"]),
                "participante_id": pid,
                "nome": (row["nome"] or "").strip() or "alguém",
                "username": row["username"],
                "avatar_path": row["avatar_path"],
                "celulas": celulas,
                "finalizado": bool(row["finalizado"]),
                "interrompido": bool(row["interrompido"]),
                "status": status,
                "atualizado_em": row["atualizado_em"],
                "celulas_ok": ok,
                "celulas_preenchidas": filled,
                "pontos": int(row["pontos"] or 0),
                "modo": modo,
                "modo_rotulo": modo_rotulo,
                "indice_dia": indice,
            }
        )
    # Legado: progresso sem partida correspondente
    if not out:
        return listar_grid_progresso_dia(dia_s)
    return out


def _apagar_recados_e_midias(
    conn: sqlite3.Connection, rows: list[sqlite3.Row]
) -> list[str]:
    """Apaga linhas (e filhos) e devolve paths de mídia a remover do disco."""
    midias: list[str] = []
    for row in rows:
        rid = int(row["id"])
        filhos = conn.execute(
            "SELECT id, midia_path FROM perfil_recados WHERE parent_id = ?",
            (rid,),
        ).fetchall()
        for filho in filhos:
            if filho["midia_path"]:
                midias.append(str(filho["midia_path"]))
            conn.execute("DELETE FROM perfil_recados WHERE id = ?", (int(filho["id"]),))
        if row["midia_path"]:
            midias.append(str(row["midia_path"]))
        conn.execute("DELETE FROM perfil_recados WHERE id = ?", (rid,))
    return midias


def criar_recado(
    target_id: int,
    autor_id: int,
    texto: str,
    *,
    midia_path: str | None = None,
    parent_id: int | None = None,
) -> dict[str, Any]:
    tid = int(target_id)
    aid = int(autor_id)
    body = (texto or "").strip()
    midia = (midia_path or "").strip() or None
    pid = int(parent_id) if parent_id is not None else None
    if midia and ("/" in midia or "\\" in midia or ".." in midia):
        raise ValueError("mídia inválida")
    if not body and not midia:
        raise ValueError("recado vazio")
    if len(body) > 280:
        body = body[:280]
    alvo = get_participante(tid)
    if not alvo or alvo.get("status") != "liberado":
        raise ValueError("perfil inválido")
    autor = get_participante(aid)
    if not autor or autor.get("status") != "liberado":
        raise ValueError("autor inválido")
    extras_midia: list[str] = []
    with get_db() as conn:
        if pid is not None:
            parent = conn.execute(
                """
                SELECT id, target_id, parent_id FROM perfil_recados
                WHERE id = ?
                """,
                (pid,),
            ).fetchone()
            if not parent or int(parent["target_id"]) != tid:
                raise ValueError("recado não encontrado")
            if parent["parent_id"] is not None:
                raise ValueError("só é possível responder ao recado original")
        cur = conn.execute(
            """
            INSERT INTO perfil_recados (target_id, autor_id, texto, midia_path, parent_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            (tid, aid, body, midia, pid),
        )
        rid = int(cur.lastrowid)
        if pid is not None:
            extras = conn.execute(
                """
                SELECT id, midia_path FROM perfil_recados
                WHERE parent_id = ?
                ORDER BY id DESC
                LIMIT -1 OFFSET ?
                """,
                (pid, PERFIL_RECADO_RESPOSTAS_MAX),
            ).fetchall()
            extras_midia.extend(_apagar_recados_e_midias(conn, extras))
        else:
            # mantém só os N mais recentes no mural (raízes)
            extras = conn.execute(
                """
                SELECT id, midia_path FROM perfil_recados
                WHERE target_id = ? AND parent_id IS NULL
                ORDER BY id DESC
                LIMIT -1 OFFSET ?
                """,
                (tid, PERFIL_RECADOS_MAX),
            ).fetchall()
            extras_midia.extend(_apagar_recados_e_midias(conn, extras))
    for rel in extras_midia:
        _apagar_arquivo_recado(rel)
    lista = listar_recados(tid, limite=PERFIL_RECADOS_MAX, voter_id=aid)
    if pid is not None:
        for item in lista:
            for resp in item.get("respostas") or []:
                if resp["id"] == str(rid):
                    return resp
    else:
        for item in lista:
            if item["id"] == str(rid):
                return item
    return {
        "id": str(rid),
        "target_id": tid,
        "autor_id": aid,
        "autor": (autor.get("nome") or "").strip() or "alguém",
        "avatar_path": autor.get("avatar_path"),
        "iniciais": ((autor.get("nome") or "??")[:2]).upper(),
        "texto": body,
        "midia_path": midia,
        "parent_id": str(pid) if pid is not None else None,
        "at": None,
        "reacoes": [],
        "respostas": [],
    }


def apagar_recado(target_id: int, recado_id: int, *, actor_id: int) -> bool:
    """Dono do mural ou autor do recado podem apagar."""
    tid = int(target_id)
    rid = int(recado_id)
    aid = int(actor_id)
    midias: list[str] = []
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT id, target_id, autor_id, midia_path FROM perfil_recados
            WHERE id = ? AND target_id = ?
            """,
            (rid, tid),
        ).fetchone()
        if not row:
            return False
        if aid != int(row["target_id"]) and aid != int(row["autor_id"]):
            raise ValueError("sem permissão")
        midias.extend(_apagar_recados_e_midias(conn, [row]))
    for rel in midias:
        _apagar_arquivo_recado(rel)
    return True


def contar_recados_novos(target_id: int) -> int:
    """Quantos recados no mural ainda não foram vistos pelo dono."""
    tid = int(target_id)
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS n
            FROM perfil_recados r
            JOIN participantes p ON p.id = r.target_id
            WHERE r.target_id = ?
              AND r.id > COALESCE(p.recados_visto_ate, 0)
            """,
            (tid,),
        ).fetchone()
    return int(row["n"] or 0) if row else 0


def marcar_recados_vistos(target_id: int) -> int:
    """Marca o mural como lido até o último recado atual. Devolve o id visto."""
    tid = int(target_id)
    with get_db() as conn:
        row = conn.execute(
            "SELECT COALESCE(MAX(id), 0) AS max_id FROM perfil_recados WHERE target_id = ?",
            (tid,),
        ).fetchone()
        max_id = int(row["max_id"] or 0) if row else 0
        conn.execute(
            "UPDATE participantes SET recados_visto_ate = ? WHERE id = ?",
            (max_id, tid),
        )
    return max_id


def get_grid_progresso(participante_id: int, dia: str) -> dict[str, Any] | None:
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT participante_id, dia, celulas_json, finalizado, atualizado_em
            FROM grid_progresso
            WHERE participante_id = ? AND dia = ?
            """,
            (int(participante_id), str(dia)),
        ).fetchone()
        if not row:
            return None
        try:
            celulas = json.loads(row["celulas_json"] or "[]")
        except json.JSONDecodeError:
            celulas = []
        return {
            "participante_id": int(row["participante_id"]),
            "dia": row["dia"],
            "celulas": celulas,
            "finalizado": bool(row["finalizado"]),
            "atualizado_em": row["atualizado_em"],
        }


def salvar_grid_progresso(
    participante_id: int,
    dia: str,
    celulas: list,
    *,
    finalizado: bool = False,
) -> dict[str, Any]:
    pid = int(participante_id)
    dia_s = str(dia)
    payload = json.dumps(celulas, ensure_ascii=False)
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO grid_progresso (participante_id, dia, celulas_json, finalizado, atualizado_em)
            VALUES (?, ?, ?, ?, datetime('now', 'localtime'))
            ON CONFLICT(participante_id, dia) DO UPDATE SET
              celulas_json = excluded.celulas_json,
              finalizado = excluded.finalizado,
              atualizado_em = datetime('now', 'localtime')
            """,
            (pid, dia_s, payload, 1 if finalizado else 0),
        )
    out = get_grid_progresso(pid, dia_s)
    assert out is not None
    return out


def _row_grid_partida(row: sqlite3.Row) -> dict[str, Any]:
    try:
        celulas = json.loads(row["celulas_json"] or "[]")
    except json.JSONDecodeError:
        celulas = []
    try:
        dicas = json.loads(row["dicas_json"] or "[]")
    except json.JSONDecodeError:
        dicas = []
    return {
        "id": int(row["id"]),
        "participante_id": int(row["participante_id"]),
        "dia": row["dia"],
        "modo": row["modo"],
        "puzzle_salt": row["puzzle_salt"] or "",
        "celulas": celulas,
        "finalizado": bool(row["finalizado"]),
        "interrompido": bool(row["interrompido"]),
        "iniciado_em": row["iniciado_em"],
        "encerrado_em": row["encerrado_em"],
        "tempo_segundos": row["tempo_segundos"],
        "pontos": int(row["pontos"] or 0),
        "dicas": dicas if isinstance(dicas, list) else [],
        "criado_em": row["criado_em"],
        "atualizado_em": row["atualizado_em"],
    }


def get_grid_partida(partida_id: int) -> dict[str, Any] | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM grid_partida WHERE id = ?",
            (int(partida_id),),
        ).fetchone()
        return _row_grid_partida(row) if row else None


def get_grid_partida_raiz(participante_id: int, dia: str) -> dict[str, Any] | None:
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT * FROM grid_partida
            WHERE participante_id = ? AND dia = ? AND modo = 'raiz'
            """,
            (int(participante_id), str(dia)),
        ).fetchone()
        return _row_grid_partida(row) if row else None


def get_grid_partida_aberta(
    participante_id: int, dia: str, *, modo: str
) -> dict[str, Any] | None:
    """Última partida do modo ainda em andamento (não finalizada/interrompida)."""
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT * FROM grid_partida
            WHERE participante_id = ? AND dia = ? AND modo = ?
              AND COALESCE(finalizado, 0) = 0
              AND COALESCE(interrompido, 0) = 0
            ORDER BY id DESC
            LIMIT 1
            """,
            (int(participante_id), str(dia), str(modo)),
        ).fetchone()
        return _row_grid_partida(row) if row else None


def contar_grid_partidas_dia(
    participante_id: int,
    dia: str,
    *,
    modo: str,
    so_encerradas: bool = False,
) -> int:
    """Conta partidas do dia. Com so_encerradas=True, ignora a aberta (cota Contínuo)."""
    with get_db() as conn:
        if so_encerradas:
            row = conn.execute(
                """
                SELECT COUNT(*) AS n FROM grid_partida
                WHERE participante_id = ? AND dia = ? AND modo = ?
                  AND (
                    COALESCE(finalizado, 0) = 1
                    OR COALESCE(interrompido, 0) = 1
                  )
                """,
                (int(participante_id), str(dia), str(modo)),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT COUNT(*) AS n FROM grid_partida
                WHERE participante_id = ? AND dia = ? AND modo = ?
                """,
                (int(participante_id), str(dia), str(modo)),
            ).fetchone()
        return int(row["n"] or 0) if row else 0


def indice_grid_partida_dia(
    participante_id: int,
    dia: str,
    *,
    modo: str,
    partida_id: int,
) -> int:
    """Índice 1-based da partida entre as do mesmo dia/modo (ordem de criação)."""
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS n FROM grid_partida
            WHERE participante_id = ? AND dia = ? AND modo = ? AND id <= ?
            """,
            (int(participante_id), str(dia), str(modo), int(partida_id)),
        ).fetchone()
        return max(1, int(row["n"] or 1) if row else 1)

def criar_grid_partida(
    participante_id: int,
    dia: str,
    *,
    modo: str,
    puzzle_salt: str = "",
    iniciado_em: str | None = None,
) -> dict[str, Any]:
    if modo not in ("raiz", "xonha"):
        raise ValueError("modo inválido")
    pid = int(participante_id)
    dia_s = str(dia)
    with get_db() as conn:
        cur = conn.execute(
            """
            INSERT INTO grid_partida (
              participante_id, dia, modo, puzzle_salt, celulas_json,
              iniciado_em, criado_em, atualizado_em
            ) VALUES (?, ?, ?, ?, '[]', ?, datetime('now', 'localtime'), datetime('now', 'localtime'))
            """,
            (pid, dia_s, modo, str(puzzle_salt or ""), iniciado_em),
        )
        pid_row = int(cur.lastrowid)
    out = get_grid_partida(pid_row)
    assert out is not None
    return out


def atualizar_grid_partida(
    partida_id: int,
    *,
    celulas: list | None = None,
    finalizado: bool | None = None,
    interrompido: bool | None = None,
    iniciado_em: str | None = None,
    encerrado_em: str | None = None,
    tempo_segundos: int | None = None,
    pontos: int | None = None,
    dicas: list | None = None,
) -> dict[str, Any]:
    sets: list[str] = ["atualizado_em = datetime('now', 'localtime')"]
    args: list[Any] = []
    if celulas is not None:
        sets.append("celulas_json = ?")
        args.append(json.dumps(celulas, ensure_ascii=False))
    if finalizado is not None:
        sets.append("finalizado = ?")
        args.append(1 if finalizado else 0)
    if interrompido is not None:
        sets.append("interrompido = ?")
        args.append(1 if interrompido else 0)
    if iniciado_em is not None:
        sets.append("iniciado_em = ?")
        args.append(iniciado_em)
    if encerrado_em is not None:
        sets.append("encerrado_em = ?")
        args.append(encerrado_em)
    if tempo_segundos is not None:
        sets.append("tempo_segundos = ?")
        args.append(int(tempo_segundos))
    if pontos is not None:
        sets.append("pontos = ?")
        args.append(int(pontos))
    if dicas is not None:
        sets.append("dicas_json = ?")
        args.append(json.dumps(dicas, ensure_ascii=False))
    args.append(int(partida_id))
    with get_db() as conn:
        conn.execute(
            f"UPDATE grid_partida SET {', '.join(sets)} WHERE id = ?",
            tuple(args),
        )
    out = get_grid_partida(int(partida_id))
    assert out is not None
    return out


def get_grid_xonha_passe(participante_id: int) -> dict[str, Any] | None:
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT participante_id, valido_ate, liberado_em, liberado_por
            FROM grid_xonha_passe WHERE participante_id = ?
            """,
            (int(participante_id),),
        ).fetchone()
        if not row:
            return None
        return {
            "participante_id": int(row["participante_id"]),
            "valido_ate": row["valido_ate"],
            "liberado_em": row["liberado_em"],
            "liberado_por": row["liberado_por"] or "",
        }


def grid_xonha_passe_ativo(participante_id: int, *, hoje: str | None = None) -> bool:
    from src.grid_game import dia_grid

    row = get_grid_xonha_passe(participante_id)
    if not row:
        return False
    ref = hoje or dia_grid()
    return str(row["valido_ate"]) >= str(ref)


def liberar_grid_xonha_passe(
    participante_id: int,
    *,
    valido_ate: str,
    liberado_por: str = "",
) -> dict[str, Any]:
    pid = int(participante_id)
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO grid_xonha_passe (participante_id, valido_ate, liberado_em, liberado_por)
            VALUES (?, ?, datetime('now', 'localtime'), ?)
            ON CONFLICT(participante_id) DO UPDATE SET
              valido_ate = excluded.valido_ate,
              liberado_em = datetime('now', 'localtime'),
              liberado_por = excluded.liberado_por
            """,
            (pid, str(valido_ate), str(liberado_por or "")),
        )
    out = get_grid_xonha_passe(pid)
    assert out is not None
    return out


def grid_streak(participante_id: int, *, ate_dia: str | None = None) -> int:
    """Dias consecutivos finalizados até ate_dia (inclusive), contando para trás."""
    from datetime import date, timedelta

    from src.grid_game import GRID_RANKING_DESDE, dia_grid

    pid = int(participante_id)
    fim = date.fromisoformat(ate_dia or dia_grid())
    ini = date.fromisoformat(GRID_RANKING_DESDE)
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT dia FROM grid_progresso
            WHERE participante_id = ? AND finalizado = 1 AND dia <= ? AND dia >= ?
            ORDER BY dia DESC
            """,
            (pid, fim.isoformat(), GRID_RANKING_DESDE),
        ).fetchall()
    feitos = {r["dia"] for r in rows}
    streak = 0
    cursor = fim
    while cursor >= ini and cursor.isoformat() in feitos:
        streak += 1
        cursor = cursor - timedelta(days=1)
    return streak


def _contar_celulas_ok(celulas: Any) -> tuple[int, int]:
    """Devolve (acertos, preenchidas) a partir do JSON 3×3."""
    ok = 0
    filled = 0
    if not isinstance(celulas, list):
        return 0, 0
    for row in celulas:
        if not isinstance(row, list):
            continue
        for cell in row:
            if not isinstance(cell, dict) or not cell.get("clube"):
                continue
            filled += 1
            if cell.get("ok"):
                ok += 1
    return ok, filled


def _rep_clube_celula(cell: dict[str, Any]) -> int:
    """Rep FM do clube na célula (snapshot) ou lookup no catálogo."""
    clube = cell.get("clube") if isinstance(cell, dict) else None
    if not isinstance(clube, dict):
        return 0
    if "rep" in clube and clube.get("rep") is not None:
        try:
            return max(0, int(clube.get("rep") or 0))
        except (TypeError, ValueError):
            pass
    cid = str(clube.get("id") or "").strip()
    if not cid:
        return 0
    try:
        from src.grid_game import clubes_por_id

        cat = clubes_por_id().get(cid)
        if cat:
            return max(0, int(cat.get("rep") or 0))
    except Exception:
        pass
    return 0


def _somar_pontos_rep(celulas: Any) -> int:
    """Soma pontos de desempate: menor reputação FM → mais pontos (só acertos)."""
    from src.clubes_catalogo import pontos_rep_desempate

    total = 0
    if not isinstance(celulas, list):
        return 0
    for row in celulas:
        if not isinstance(row, list):
            continue
        for cell in row:
            if not isinstance(cell, dict) or not cell.get("clube") or not cell.get("ok"):
                continue
            total += pontos_rep_desempate(_rep_clube_celula(cell))
    return total


def ranking_grid(*, limite: int = 50) -> list[dict[str, Any]]:
    """Ranking: dias finalizados → acertos → streak → pontos Rep (obscuro vale mais)."""
    from src.grid_game import GRID_RANKING_DESDE

    lim = max(1, min(int(limite), 200))
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT p.id AS participante_id, p.nome, p.avatar_path,
                   g.dia, g.celulas_json, g.finalizado
            FROM grid_progresso g
            JOIN participantes p ON p.id = g.participante_id
            WHERE p.status = 'liberado' AND g.dia >= ?
            ORDER BY p.id ASC, g.dia DESC
            """,
            (GRID_RANKING_DESDE,),
        ).fetchall()
    agg: dict[int, dict[str, Any]] = {}
    for row in rows:
        pid = int(row["participante_id"])
        item = agg.setdefault(
            pid,
            {
                "participante_id": pid,
                "nome": (row["nome"] or "").strip() or "alguém",
                "avatar_path": row["avatar_path"],
                "dias_finalizados": 0,
                "celulas_ok": 0,
                "celulas_preenchidas": 0,
                "pontos_rep": 0,
            },
        )
        try:
            celulas = json.loads(row["celulas_json"] or "[]")
        except json.JSONDecodeError:
            celulas = []
        ok, filled = _contar_celulas_ok(celulas)
        item["celulas_ok"] += ok
        item["celulas_preenchidas"] += filled
        item["pontos_rep"] += _somar_pontos_rep(celulas)
        if row["finalizado"]:
            item["dias_finalizados"] += 1
    out: list[dict[str, Any]] = []
    for pid, item in agg.items():
        if item["celulas_preenchidas"] <= 0 and item["dias_finalizados"] <= 0:
            continue
        item["streak"] = grid_streak(pid)
        item["taxa"] = (
            round(100.0 * item["celulas_ok"] / item["celulas_preenchidas"])
            if item["celulas_preenchidas"]
            else 0
        )
        out.append(item)
    out.sort(
        key=lambda r: (
            -int(r["dias_finalizados"]),
            -int(r["celulas_ok"]),
            -int(r["streak"]),
            -int(r["pontos_rep"]),
            (r["nome"] or "").casefold(),
        )
    )
    from src.ranking import _zona_classificacao

    total = len(out)
    limited = out[:lim]
    for i, item in enumerate(limited, start=1):
        item["posicao"] = i
        item["zona"] = _zona_classificacao(i, total)
    return anexar_hall_borda(limited)


def grid_streak_modo(
    participante_id: int,
    modo: str,
    *,
    ate_dia: str | None = None,
) -> int:
    """Dias consecutivos com ≥1 partida finalizada no modo.

    No Contínuo, só a **primeira** partida do dia (menor id) conta para o streak.
    """
    from datetime import date, timedelta

    from src.grid_game import GRID_RANKING_DESDE, dia_grid

    if modo not in ("raiz", "xonha"):
        return 0
    pid = int(participante_id)
    fim = date.fromisoformat(ate_dia or dia_grid())
    ini = date.fromisoformat(GRID_RANKING_DESDE)
    with get_db() as conn:
        if modo == "xonha":
            rows = conn.execute(
                """
                SELECT g.dia FROM (
                  SELECT MIN(id) AS primeira_id
                  FROM grid_partida
                  WHERE participante_id = ? AND modo = 'xonha'
                    AND dia <= ? AND dia >= ?
                  GROUP BY dia
                ) p
                JOIN grid_partida g ON g.id = p.primeira_id
                WHERE g.finalizado = 1
                ORDER BY g.dia DESC
                """,
                (pid, fim.isoformat(), GRID_RANKING_DESDE),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT DISTINCT dia FROM grid_partida
                WHERE participante_id = ? AND modo = ? AND finalizado = 1
                  AND dia <= ? AND dia >= ?
                ORDER BY dia DESC
                """,
                (pid, modo, fim.isoformat(), GRID_RANKING_DESDE),
            ).fetchall()
    feitos = {r["dia"] for r in rows}
    streak = 0
    cursor = fim
    while cursor >= ini and cursor.isoformat() in feitos:
        streak += 1
        cursor = cursor - timedelta(days=1)
    return streak


def ranking_grid_modo(modo: str, *, limite: int = 50) -> list[dict[str, Any]]:
    """Ranking por score único (Raiz ou Xonha) a partir de grid_partida.

    No Contínuo (xonha), só a **primeira** partida de cada dia conta no score
    (as demais são só diversão).

    Score = acertos + completo + tempo + raridade(média×índice) − dicas (+ streak).
    Raridade ajuda quem joga times obscuros, sem reverter um déficit grande
    de acertos; ainda desempatam via pontos_rep bruto.
    """
    from src.grid_game import GRID_RANKING_DESDE, dia_grid
    from src.grid_score import pontos_partida, pontos_rep_celulas, score_ranking

    if modo not in ("raiz", "xonha"):
        raise ValueError("modo inválido")
    lim = max(1, min(int(limite), 200))
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT p.id AS participante_id, p.nome, p.avatar_path,
                   g.id AS partida_id, g.dia, g.celulas_json, g.finalizado,
                   g.interrompido, g.pontos, g.tempo_segundos, g.dicas_json
            FROM grid_partida g
            JOIN participantes p ON p.id = g.participante_id
            WHERE p.status = 'liberado' AND g.modo = ? AND g.dia >= ?
            ORDER BY p.id ASC, g.dia ASC, g.id ASC
            """,
            (modo, GRID_RANKING_DESDE),
        ).fetchall()
    agg: dict[int, dict[str, Any]] = {}
    # Contínuo: (participante_id, dia) já contabilizado = só a 1ª partida
    xonha_primeiro_dia: set[tuple[int, str]] = set()
    hoje = dia_grid()
    for row in rows:
        pid = int(row["participante_id"])
        dia = str(row["dia"])
        if modo == "xonha":
            chave = (pid, dia)
            if chave in xonha_primeiro_dia:
                continue
            xonha_primeiro_dia.add(chave)
        item = agg.setdefault(
            pid,
            {
                "participante_id": pid,
                "nome": (row["nome"] or "").strip() or "alguém",
                "avatar_path": row["avatar_path"],
                "dias_finalizados": 0,
                "partidas_finalizadas": 0,
                "celulas_ok": 0,
                "celulas_preenchidas": 0,
                "pontos_partidas": [],
                "pontos_rep": 0,
                "tempos": [],
            },
        )
        try:
            celulas = json.loads(row["celulas_json"] or "[]")
        except json.JSONDecodeError:
            celulas = []
        try:
            dicas = json.loads(row["dicas_json"] or "[]")
        except (json.JSONDecodeError, TypeError):
            dicas = []
        if not isinstance(dicas, list):
            dicas = []
        ok, filled = _contar_celulas_ok(celulas)
        item["celulas_ok"] += ok
        item["celulas_preenchidas"] += filled
        item["pontos_rep"] += pontos_rep_celulas(celulas)
        finalizado = bool(row["finalizado"])
        interrompido = bool(row["interrompido"])
        tempo = row["tempo_segundos"]
        try:
            tempo_i = int(tempo) if tempo is not None else None
        except (TypeError, ValueError):
            tempo_i = None
        # Recalcula sem raridade (pontos gravados antigos ainda incluíam Rep).
        pts = pontos_partida(
            celulas,
            finalizado=finalizado,
            interrompido=interrompido,
            tempo_segundos=tempo_i,
            dicas=dicas,
        )
        item["pontos_partidas"].append(pts)
        if finalizado:
            item["partidas_finalizadas"] += 1
            if modo == "raiz":
                item["dias_finalizados"] += 1
            if tempo_i is not None:
                item["tempos"].append(tempo_i)
        elif modo == "raiz" and filled > 0:
            # partida raiz iniciada conta dia jogado parcial? não — só finalizados
            pass
    # dias_finalizados no xonha = dias distintos com a 1ª partida finalizada
    if modo == "xonha":
        with get_db() as conn:
            for pid in list(agg.keys()):
                n = conn.execute(
                    """
                    SELECT COUNT(*) AS n FROM (
                      SELECT MIN(id) AS primeira_id
                      FROM grid_partida
                      WHERE participante_id = ? AND modo = 'xonha' AND dia >= ?
                      GROUP BY dia
                    ) p
                    JOIN grid_partida g ON g.id = p.primeira_id
                    WHERE g.finalizado = 1
                    """,
                    (pid, GRID_RANKING_DESDE),
                ).fetchone()
                agg[pid]["dias_finalizados"] = int(n["n"] or 0) if n else 0

    out: list[dict[str, Any]] = []
    for pid, item in agg.items():
        if item["celulas_preenchidas"] <= 0 and item["partidas_finalizadas"] <= 0:
            continue
        streak = grid_streak_modo(pid, modo, ate_dia=hoje)
        item["streak"] = streak
        item["score"] = score_ranking(item.pop("pontos_partidas"), streak=streak)
        item["taxa"] = (
            round(100.0 * item["celulas_ok"] / item["celulas_preenchidas"])
            if item["celulas_preenchidas"]
            else 0
        )
        tempos = item.pop("tempos")
        item["tempo_medio"] = (
            int(round(sum(tempos) / len(tempos))) if tempos else None
        )
        out.append(item)
    out.sort(
        key=lambda r: (
            -int(r["score"]),
            -int(r["dias_finalizados"]),
            -int(r["celulas_ok"]),
            -int(r.get("pontos_rep") or 0),
            (r["nome"] or "").casefold(),
        )
    )
    from src.ranking import _zona_classificacao

    total = len(out)
    limited = out[:lim]
    for i, item in enumerate(limited, start=1):
        item["posicao"] = i
        item["zona"] = _zona_classificacao(i, total)
        item["modo"] = modo
    return anexar_hall_borda(limited)


def posicao_ranking_grid_modo(participante_id: int, modo: str) -> int | None:
    """Posição 1-based do jogador no ranking do modo, ou None se ausente."""
    if modo not in ("raiz", "xonha"):
        return None
    pid = int(participante_id)
    for item in ranking_grid_modo(modo, limite=200):
        if int(item.get("participante_id") or 0) == pid:
            try:
                pos = int(item.get("posicao") or 0)
            except (TypeError, ValueError):
                return None
            return pos if pos > 0 else None
    return None


def limpar_grid_partidas() -> int:
    with get_db() as conn:
        cur = conn.execute("DELETE FROM grid_partida")
        return int(cur.rowcount or 0)


def grid_stats_participante(participante_id: int) -> dict[str, Any]:
    """Agregados do Grid para o bloco do perfil."""
    from src.grid_game import GRID_RANKING_DESDE

    pid = int(participante_id)
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT dia, celulas_json, finalizado
            FROM grid_progresso
            WHERE participante_id = ? AND dia >= ?
            ORDER BY dia DESC
            """,
            (pid, GRID_RANKING_DESDE),
        ).fetchall()
    dias_finalizados = 0
    celulas_ok = 0
    celulas_preenchidas = 0
    for row in rows:
        try:
            celulas = json.loads(row["celulas_json"] or "[]")
        except json.JSONDecodeError:
            celulas = []
        ok, filled = _contar_celulas_ok(celulas)
        celulas_ok += ok
        celulas_preenchidas += filled
        if row["finalizado"]:
            dias_finalizados += 1
    streak = grid_streak(pid)
    taxa = None
    if celulas_preenchidas:
        taxa = round(100.0 * celulas_ok / celulas_preenchidas)
    ranking = ranking_grid(limite=500)
    posicao = None
    for item in ranking:
        if int(item["participante_id"]) == pid:
            posicao = item.get("posicao")
            break
    return {
        "dias_finalizados": dias_finalizados,
        "celulas_ok": celulas_ok,
        "celulas_preenchidas": celulas_preenchidas,
        "taxa": taxa,
        "streak": streak,
        "posicao": posicao,
        "total_ranking": len(ranking),
        "jogou": bool(rows),
    }



def _hall_lenda_row(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if not row:
        return None
    from src.hall_lendas import borda_ok, borda_rotulo, format_quando, format_valor_brl

    nome = (row["nome"] or "").strip() or "alguém"
    valor = int(row["valor_centavos"] or 0)
    borda = borda_ok(row["borda"])
    return {
        "participante_id": int(row["participante_id"]),
        "nome": nome,
        "username": row["username"],
        "avatar_path": row["avatar_path"],
        "status": row["status"],
        "valor_centavos": valor,
        "valor_rotulo": format_valor_brl(valor),
        "recado": (row["recado"] or "").strip(),
        "borda": borda,
        "borda_rotulo": borda_rotulo(borda),
        "doado_em": row["doado_em"],
        "quando_rotulo": format_quando(row["doado_em"]),
        "criado_em": row["criado_em"],
        "atualizado_em": row["atualizado_em"],
    }


def get_hall_lenda(participante_id: int) -> dict[str, Any] | None:
    pid = int(participante_id)
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT h.*, p.nome, p.username, p.avatar_path, p.status
            FROM hall_lendas h
            JOIN participantes p ON p.id = h.participante_id
            WHERE h.participante_id = ?
            """,
            (pid,),
        ).fetchone()
    return _hall_lenda_row(row)


def is_lenda(participante_id: int) -> bool:
    return get_hall_lenda(int(participante_id)) is not None


def contar_hall_lendas() -> int:
    with get_db() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM hall_lendas").fetchone()
    return int(row["n"] or 0) if row else 0


def listar_hall_lendas(*, pagina: int = 1, por_pagina: int = 10) -> dict[str, Any]:
    """Lista pública ordenada por total doado (desc)."""
    from src.hall_lendas import HALL_POR_PAGINA

    por = max(1, min(int(por_pagina or HALL_POR_PAGINA), 50))
    pag = max(1, int(pagina or 1))
    total = contar_hall_lendas()
    offset = (pag - 1) * por
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT h.*, p.nome, p.username, p.avatar_path, p.status
            FROM hall_lendas h
            JOIN participantes p ON p.id = h.participante_id
            ORDER BY h.valor_centavos DESC, h.doado_em DESC, p.nome COLLATE NOCASE ASC
            LIMIT ? OFFSET ?
            """,
            (por, offset),
        ).fetchall()
    itens = [_hall_lenda_row(r) for r in rows]
    itens = [x for x in itens if x]
    pages = max(1, (total + por - 1) // por) if total else 1
    return {
        "itens": itens,
        "total": total,
        "pagina": pag,
        "por_pagina": por,
        "paginas": pages,
        "tem_anterior": pag > 1,
        "tem_proxima": pag < pages,
    }


def upsert_hall_lenda(
    participante_id: int,
    *,
    valor_centavos_add: int = 0,
    recado: str | None = None,
    borda: str | None = None,
    substituir_valor: int | None = None,
) -> dict[str, Any]:
    """Cria ou atualiza lenda. Soma valor_centavos_add ao total (ou substitui)."""
    from src.hall_lendas import agora_local_iso, borda_ok

    pid = int(participante_id)
    part = get_participante(pid)
    if not part:
        raise ValueError("Participante não encontrado")
    if part.get("status") != "liberado":
        raise ValueError("Só participantes liberados entram no Hall")

    add = max(0, int(valor_centavos_add or 0))
    agora = agora_local_iso()
    atual = get_hall_lenda(pid)
    if atual is None and add <= 0 and substituir_valor is None:
        raise ValueError("informe um valor de doação para criar a lenda")

    if atual is None:
        total = int(substituir_valor) if substituir_valor is not None else add
        b = borda_ok(borda)
        texto = (recado or "").strip()
        with get_db() as conn:
            conn.execute(
                """
                INSERT INTO hall_lendas (
                  participante_id, valor_centavos, recado, borda, doado_em, criado_em, atualizado_em
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (pid, total, texto, b, agora, agora, agora),
            )
    else:
        if substituir_valor is not None:
            total = max(0, int(substituir_valor))
        else:
            total = int(atual["valor_centavos"]) + add
        texto = atual["recado"] if recado is None else str(recado).strip()
        b = borda_ok(borda) if borda is not None else atual["borda"]
        # Atualiza doado_em só quando entra valor novo (soma); edição de total/recado mantém data.
        doado_em = agora if add > 0 else atual["doado_em"]
        with get_db() as conn:
            conn.execute(
                """
                UPDATE hall_lendas SET
                  valor_centavos = ?,
                  recado = ?,
                  borda = ?,
                  doado_em = ?,
                  atualizado_em = ?
                WHERE participante_id = ?
                """,
                (total, texto, b, doado_em, agora, pid),
            )
    out = get_hall_lenda(pid)
    assert out is not None
    return out


def set_hall_borda(participante_id: int, borda: str) -> dict[str, Any]:
    from src.hall_lendas import agora_local_iso, borda_ok

    pid = int(participante_id)
    if not get_hall_lenda(pid):
        raise ValueError("Participante não é lenda")
    b = borda_ok(borda)
    with get_db() as conn:
        conn.execute(
            """
            UPDATE hall_lendas SET borda = ?, atualizado_em = ?
            WHERE participante_id = ?
            """,
            (b, agora_local_iso(), pid),
        )
    out = get_hall_lenda(pid)
    assert out is not None
    return out


def apagar_hall_lenda(participante_id: int) -> bool:
    with get_db() as conn:
        cur = conn.execute(
            "DELETE FROM hall_lendas WHERE participante_id = ?",
            (int(participante_id),),
        )
        return int(cur.rowcount or 0) > 0


def map_hall_bordas(participante_ids: list[int] | tuple[int, ...] | set[int]) -> dict[int, str]:
    """Mapa participante_id → borda (só quem é lenda)."""
    from src.hall_lendas import borda_ok

    ids = sorted({int(x) for x in participante_ids if x is not None})
    if not ids:
        return {}
    placeholders = ",".join("?" * len(ids))
    with get_db() as conn:
        rows = conn.execute(
            f"SELECT participante_id, borda FROM hall_lendas WHERE participante_id IN ({placeholders})",
            ids,
        ).fetchall()
    return {int(r["participante_id"]): borda_ok(r["borda"]) for r in rows}


def anexar_hall_borda(
    itens: list[dict[str, Any]],
    *,
    id_key: str = "participante_id",
) -> list[dict[str, Any]]:
    """Injeta hall_borda / is_lenda em cada dict (in-place)."""
    ids: list[int] = []
    for it in itens:
        raw = it.get(id_key)
        if raw is None and id_key != "id":
            raw = it.get("id")
        if raw is not None:
            ids.append(int(raw))
    mapa = map_hall_bordas(ids)
    for it in itens:
        raw = it.get(id_key)
        if raw is None and id_key != "id":
            raw = it.get("id")
        borda = mapa.get(int(raw)) if raw is not None else None
        it["hall_borda"] = borda
        it["is_lenda"] = borda is not None
    return itens


def get_hall_hero_html() -> str:
    from src.hall_lendas import HALL_HERO_DEFAULT, HALL_HERO_META, sanitize_hall_hero_html

    raw = get_meta(HALL_HERO_META)
    if raw is None or not str(raw).strip():
        return HALL_HERO_DEFAULT
    return sanitize_hall_hero_html(raw)


def set_hall_hero_html(html: str) -> str:
    from src.hall_lendas import HALL_HERO_META, sanitize_hall_hero_html

    limpo = sanitize_hall_hero_html(html)
    set_meta(HALL_HERO_META, limpo)
    return limpo


def list_participantes_liberados() -> list[dict[str, Any]]:
    """Liberados ativos para o seletor do admin do Hall."""
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT id, nome, username, avatar_path, status
            FROM participantes
            WHERE status = 'liberado'
              AND (inativo_em IS NULL OR inativo_em = '')
            ORDER BY nome COLLATE NOCASE ASC
            """
        ).fetchall()
    return [dict(r) for r in rows]


BUG_STATUS_OK = frozenset({"aberto", "em_analise", "resolvido"})


def _bug_row(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if not row:
        return None
    d = dict(row)
    d["usuario_leu_resposta"] = bool(d.get("usuario_leu_resposta"))
    return d


def _anexar_bug_mensagens(reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not reports:
        return reports
    ids = [int(r["id"]) for r in reports]
    placeholders = ",".join("?" for _ in ids)
    by_id: dict[int, list[dict[str, Any]]] = {i: [] for i in ids}
    with get_db() as conn:
        rows = conn.execute(
            f"""
            SELECT id, report_id, autor, texto, criado_em
            FROM bug_report_mensagens
            WHERE report_id IN ({placeholders})
            ORDER BY criado_em ASC, id ASC
            """,
            ids,
        ).fetchall()
    for row in rows:
        by_id.setdefault(int(row["report_id"]), []).append(dict(row))
    for r in reports:
        msgs = by_id.get(int(r["id"]), [])
        if not msgs:
            # Fallback legado se o backfill ainda não rodou neste banco.
            msgs = [
                {
                    "id": 0,
                    "report_id": int(r["id"]),
                    "autor": "usuario",
                    "texto": r.get("mensagem") or "",
                    "criado_em": r.get("criado_em"),
                }
            ]
            resp = (r.get("resposta") or "").strip()
            if resp:
                msgs.append(
                    {
                        "id": 0,
                        "report_id": int(r["id"]),
                        "autor": "admin",
                        "texto": resp,
                        "criado_em": r.get("respondido_em") or r.get("atualizado_em"),
                    }
                )
        r["mensagens"] = msgs
    return reports


def criar_bug_report(
    participante_id: int,
    *,
    titulo: str,
    mensagem: str,
    imagem_path: str | None = None,
) -> dict[str, Any]:
    titulo = re.sub(r"\s+", " ", (titulo or "").strip())
    mensagem = (mensagem or "").strip()
    if not titulo:
        raise ValueError("Informe o título")
    if len(titulo) > 120:
        raise ValueError("Título com no máximo 120 caracteres")
    if not mensagem:
        raise ValueError("Escreva a mensagem do bug")
    if len(mensagem) > 4000:
        raise ValueError("Mensagem com no máximo 4000 caracteres")
    img = (imagem_path or "").strip() or None
    if img and ("/" in img or "\\" in img or ".." in img):
        raise ValueError("Imagem inválida")
    with get_db() as conn:
        cur = conn.execute(
            """
            INSERT INTO bug_reports
              (participante_id, titulo, mensagem, imagem_path, status, usuario_leu_resposta)
            VALUES (?, ?, ?, ?, 'aberto', 1)
            """,
            (int(participante_id), titulo, mensagem, img),
        )
        rid = int(cur.lastrowid)
        conn.execute(
            """
            INSERT INTO bug_report_mensagens (report_id, autor, texto)
            VALUES (?, 'usuario', ?)
            """,
            (rid, mensagem),
        )
        row = conn.execute(
            "SELECT * FROM bug_reports WHERE id = ?", (rid,)
        ).fetchone()
    out = _bug_row(row)
    assert out is not None
    out["mensagens"] = [
        {
            "id": 0,
            "report_id": rid,
            "autor": "usuario",
            "texto": mensagem,
            "criado_em": out.get("criado_em"),
        }
    ]
    return out


def listar_bug_reports_usuario(participante_id: int) -> list[dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM bug_reports
            WHERE participante_id = ?
            ORDER BY criado_em DESC, id DESC
            """,
            (int(participante_id),),
        ).fetchall()
    return _anexar_bug_mensagens([_bug_row(r) for r in rows if r])  # type: ignore[misc]


def listar_bug_reports_admin(*, status: str | None = None) -> list[dict[str, Any]]:
    st = (status or "").strip().lower() or None
    if st and st not in BUG_STATUS_OK:
        st = None
    with get_db() as conn:
        if st:
            rows = conn.execute(
                """
                SELECT b.*, p.nome AS autor_nome, p.username AS autor_username,
                       p.avatar_path AS autor_avatar
                FROM bug_reports b
                JOIN participantes p ON p.id = b.participante_id
                WHERE b.status = ?
                ORDER BY
                  CASE b.status
                    WHEN 'aberto' THEN 0
                    WHEN 'em_analise' THEN 1
                    ELSE 2
                  END,
                  b.atualizado_em DESC,
                  b.id DESC
                """,
                (st,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT b.*, p.nome AS autor_nome, p.username AS autor_username,
                       p.avatar_path AS autor_avatar
                FROM bug_reports b
                JOIN participantes p ON p.id = b.participante_id
                ORDER BY
                  CASE b.status
                    WHEN 'aberto' THEN 0
                    WHEN 'em_analise' THEN 1
                    ELSE 2
                  END,
                  b.atualizado_em DESC,
                  b.id DESC
                """
            ).fetchall()
    return _anexar_bug_mensagens([_bug_row(r) for r in rows if r])  # type: ignore[misc]


def get_bug_report(report_id: int) -> dict[str, Any] | None:
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT b.*, p.nome AS autor_nome, p.username AS autor_username,
                   p.avatar_path AS autor_avatar
            FROM bug_reports b
            JOIN participantes p ON p.id = b.participante_id
            WHERE b.id = ?
            """,
            (int(report_id),),
        ).fetchone()
    out = _bug_row(row)
    if not out:
        return None
    return _anexar_bug_mensagens([out])[0]


def atualizar_bug_report_admin(
    report_id: int,
    *,
    status: str,
    resposta: str | None = None,
) -> dict[str, Any]:
    st = (status or "").strip().lower()
    if st not in BUG_STATUS_OK:
        raise ValueError("Status inválido")
    resp = (resposta if resposta is not None else "").strip()
    if len(resp) > 4000:
        raise ValueError("Resposta com no máximo 4000 caracteres")
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM bug_reports WHERE id = ?", (int(report_id),)
        ).fetchone()
        if not row:
            raise ValueError("Report não encontrado")
        acrescentou = bool(resp)
        if acrescentou:
            conn.execute(
                """
                INSERT INTO bug_report_mensagens (report_id, autor, texto)
                VALUES (?, 'admin', ?)
                """,
                (int(report_id), resp),
            )
            conn.execute(
                """
                UPDATE bug_reports
                SET status = ?,
                    resposta = ?,
                    respondido_em = datetime('now', 'localtime'),
                    usuario_leu_resposta = 0,
                    atualizado_em = datetime('now', 'localtime')
                WHERE id = ?
                """,
                (st, resp, int(report_id)),
            )
        else:
            # Só status — mantém o log e a última resposta intactos.
            conn.execute(
                """
                UPDATE bug_reports
                SET status = ?,
                    atualizado_em = datetime('now', 'localtime')
                WHERE id = ?
                """,
                (st, int(report_id)),
            )
        out = conn.execute(
            """
            SELECT b.*, p.nome AS autor_nome, p.username AS autor_username,
                   p.avatar_path AS autor_avatar
            FROM bug_reports b
            JOIN participantes p ON p.id = b.participante_id
            WHERE b.id = ?
            """,
            (int(report_id),),
        ).fetchone()
    result = _bug_row(out)
    assert result is not None
    return _anexar_bug_mensagens([result])[0]


def contar_bug_reports_nao_lidos(participante_id: int) -> int:
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS n
            FROM bug_reports
            WHERE participante_id = ?
              AND usuario_leu_resposta = 0
              AND TRIM(COALESCE(resposta, '')) != ''
            """,
            (int(participante_id),),
        ).fetchone()
    return int(row["n"] if row else 0)


def marcar_bug_reports_lidos(participante_id: int) -> None:
    with get_db() as conn:
        conn.execute(
            """
            UPDATE bug_reports
            SET usuario_leu_resposta = 1
            WHERE participante_id = ?
              AND usuario_leu_resposta = 0
            """,
            (int(participante_id),),
        )


def contar_bug_reports_abertos() -> int:
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS n
            FROM bug_reports
            WHERE status IN ('aberto', 'em_analise')
            """
        ).fetchone()
    return int(row["n"] if row else 0)
