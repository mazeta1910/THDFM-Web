"""Auditoria de mudanças do painel (Fase C — Atividade).

Tabela `admin_audit`: eventos de escrita com autor, entidade e antes/depois.
Separado do access log (tráfego HTTP).
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlencode

from src import db

# Campos sensíveis nunca entram no JSON de auditoria.
_SECRET_KEYS = frozenset(
    {
        "password",
        "senha",
        "password_hash",
        "token",
        "secret",
        "smtp_password",
        "admin_password",
    }
)

_SKIP_AUDIT_PATHS = frozenset(
    {
        "/admin/login",
        "/admin/logout",
    }
)


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def sanitize(obj: Any) -> Any:
    if obj is None:
        return None
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            key = str(k)
            if key.casefold() in _SECRET_KEYS or key.casefold().endswith("_hash"):
                out[key] = "…"
            else:
                out[key] = sanitize(v)
        return out
    if isinstance(obj, (list, tuple)):
        return [sanitize(x) for x in obj]
    if isinstance(obj, (str, int, float, bool)):
        return obj
    return str(obj)


def snap_participante(part: dict[str, Any] | None) -> dict[str, Any] | None:
    if not part:
        return None
    keys = (
        "id",
        "nome",
        "celular",
        "status",
        "inativo_em",
        "link_enviado_em",
        "avatar_path",
        "admin_login",
        "recusado_em",
    )
    return {k: part.get(k) for k in keys}


def record(
    *,
    autor: str,
    acao: str,
    entidade: str,
    entidade_id: str | int | None = None,
    resumo: str = "",
    antes: Any = None,
    depois: Any = None,
    path: str = "",
) -> None:
    """Grava um evento. Nunca levanta para não quebrar a ação admin."""
    try:
        eid = "" if entidade_id is None else str(entidade_id)
        with db.get_db() as conn:
            conn.execute(
                """
                INSERT INTO admin_audit
                  (ts, autor, acao, entidade, entidade_id, resumo, antes_json, depois_json, path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _now(),
                    (autor or "—").strip() or "—",
                    (acao or "acao").strip()[:80],
                    (entidade or "sistema").strip()[:80],
                    eid[:80],
                    (resumo or "")[:240],
                    json.dumps(sanitize(antes), ensure_ascii=False)
                    if antes is not None
                    else None,
                    json.dumps(sanitize(depois), ensure_ascii=False)
                    if depois is not None
                    else None,
                    (path or "")[:240],
                ),
            )
    except Exception:
        return


def list_events(
    *,
    autor: str | None = None,
    entidade: str | None = None,
    entidade_id: str | None = None,
    dia_de: str | None = None,
    dia_ate: str | None = None,
    q: str | None = None,
    limit: int = 300,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    args: list[Any] = []
    if autor:
        clauses.append("lower(autor) LIKE ?")
        args.append(f"%{autor.strip().casefold()}%")
    if entidade:
        clauses.append("lower(entidade) = ?")
        args.append(entidade.strip().casefold())
    if entidade_id:
        clauses.append("entidade_id = ?")
        args.append(str(entidade_id).strip())
    if dia_de:
        clauses.append("substr(ts, 1, 10) >= ?")
        args.append(dia_de.strip()[:10])
    if dia_ate:
        clauses.append("substr(ts, 1, 10) <= ?")
        args.append(dia_ate.strip()[:10])
    if q:
        needle = f"%{q.strip().casefold()}%"
        clauses.append(
            "(lower(resumo) LIKE ? OR lower(acao) LIKE ? OR lower(path) LIKE ? "
            "OR lower(entidade_id) LIKE ?)"
        )
        args.extend([needle, needle, needle, needle])
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    lim = max(1, min(int(limit), 1000))
    sql = (
        "SELECT id, ts, autor, acao, entidade, entidade_id, resumo, "
        "antes_json, depois_json, path "
        f"FROM admin_audit{where} ORDER BY ts DESC, id DESC LIMIT ?"
    )
    args.append(lim)
    with db.get_db() as conn:
        rows = conn.execute(sql, args).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["quando"] = format_quando(d["ts"])
        out.append(d)
    return out


def count_events(
    *,
    autor: str | None = None,
    entidade: str | None = None,
    entidade_id: str | None = None,
    dia_de: str | None = None,
    dia_ate: str | None = None,
    q: str | None = None,
) -> int:
    clauses: list[str] = []
    args: list[Any] = []
    if autor:
        clauses.append("lower(autor) LIKE ?")
        args.append(f"%{autor.strip().casefold()}%")
    if entidade:
        clauses.append("lower(entidade) = ?")
        args.append(entidade.strip().casefold())
    if entidade_id:
        clauses.append("entidade_id = ?")
        args.append(str(entidade_id).strip())
    if dia_de:
        clauses.append("substr(ts, 1, 10) >= ?")
        args.append(dia_de.strip()[:10])
    if dia_ate:
        clauses.append("substr(ts, 1, 10) <= ?")
        args.append(dia_ate.strip()[:10])
    if q:
        needle = f"%{q.strip().casefold()}%"
        clauses.append(
            "(lower(resumo) LIKE ? OR lower(acao) LIKE ? OR lower(path) LIKE ? "
            "OR lower(entidade_id) LIKE ?)"
        )
        args.extend([needle, needle, needle, needle])
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    with db.get_db() as conn:
        row = conn.execute(
            f"SELECT COUNT(*) AS n FROM admin_audit{where}", args
        ).fetchone()
    return int(row["n"] if row else 0)


def recent_for_entidade(
    entidade: str, entidade_id: str | int, *, limit: int = 5
) -> list[dict[str, Any]]:
    return list_events(
        entidade=entidade,
        entidade_id=str(entidade_id),
        limit=limit,
    )


def entidades_conhecidas() -> list[str]:
    with db.get_db() as conn:
        rows = conn.execute(
            "SELECT DISTINCT entidade FROM admin_audit ORDER BY entidade"
        ).fetchall()
    return [r["entidade"] for r in rows if r["entidade"]]


def format_quando(ts: str, *, agora: datetime | None = None) -> dict[str, str]:
    iso = ts
    label = ts
    relativo = ""
    try:
        dt = datetime.strptime(ts[:19], "%Y-%m-%d %H:%M:%S")
        label = dt.strftime("%d/%m %H:%M:%S")
        iso = dt.strftime("%Y-%m-%dT%H:%M:%S")
        now = agora or datetime.now()
        delta = now - dt
        if timedelta(0) <= delta < timedelta(hours=24):
            secs = int(delta.total_seconds())
            if secs < 60:
                relativo = "há instantes"
            elif secs < 3600:
                relativo = f"há {secs // 60} min"
            else:
                relativo = f"há {secs // 3600} h"
    except ValueError:
        pass
    return {"label": label, "iso": iso, "relativo": relativo}


def query_string(filtros: dict[str, Any]) -> str:
    parts: dict[str, str] = {}
    for k in ("autor", "entidade", "entidade_id", "de", "ate", "q"):
        v = filtros.get(k)
        if v:
            parts[k] = str(v)
    return urlencode(parts)


def infer_entidade(path: str) -> tuple[str, str]:
    """(entidade, entidade_id) a partir do path /admin/..."""
    p = (path or "").rstrip("/")
    m = re.search(r"/admin/participante", p)
    if m:
        return "participante", ""
    m = re.search(r"/admin/(?:liberar|apagar|inativar|reativar|recusar|reabrir)", p)
    if m:
        return "participante", ""
    if "/admin/sistema" in p:
        return "sistema", ""
    if "/admin/resultados" in p or "/admin/resultado" in p or "/admin/jogo/" in p:
        return "resultado", ""
    if "/admin/janela" in p or "/admin/fase" in p or "/admin/avancar-fase" in p:
        return "bolao", ""
    if "/admin/permissoes" in p or "/admin/credenciais" in p:
        return "admin", ""
    if "/admin/acervo" in p:
        return "acervo", ""
    if "/admin/grid" in p or "/admin/reports" in p:
        return "grid", ""
    if "/admin/xonhometro" in p:
        return "xonhometro", ""
    if "/admin/listra" in p:
        return "listra", ""
    if "/admin/hall-lendas" in p:
        return "hall", ""
    if p.startswith("/admin"):
        return "admin", ""
    return "sistema", ""


def should_skip_path(path: str) -> bool:
    p = (path or "").split("?", 1)[0]
    if p in _SKIP_AUDIT_PATHS:
        return True
    if p.startswith("/admin/sistema/atividade"):
        return True
    return False
