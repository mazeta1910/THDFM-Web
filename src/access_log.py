"""Access log do painel Sistema (Fase B).

Política (spec v2 §7):
- Detalhe: autenticados + /admin/* + escritas
- Anônimo GET público: só agregado
- IP truncado (/24 IPv4, /48 IPv6) + UA curto
- Retenção 14 dias + purge com registro
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlencode

from src import db

RETENCAO_DIAS = 14
UA_MAX = 80
PATH_MAX = 240
PURGE_META = "access_log_ultimo_purge"
AGG_VIEW = "agregados"

_SKIP_PREFIXES = (
    "/static/",
    "/emblemas/",
    "/emblemas-fm/",
    "/avatars/",
    "/bandeiras-uf/",
    "/hall-hero/",
    "/bug-reports/",
    "/comprovantes/",
)
_SKIP_EXACT = frozenset(
    {
        "/favicon.ico",
        "/health",
        "/robots.txt",
        "/ads.txt",
        "/sitemap.xml",
    }
)
_WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def truncate_ip(raw: str | None) -> str:
    ip = (raw or "").strip()
    if not ip:
        return "—"
    if "," in ip:
        ip = ip.split(",", 1)[0].strip()
    if ip.startswith("::ffff:") and "." in ip:
        ip = ip.split("::ffff:", 1)[1]
    if re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}", ip):
        a, b, c, _ = ip.split(".")
        return f"{a}.{b}.{c}.0"
    if ":" in ip:
        # /48 = primeiros 3 hextetos (ignora zona %iface)
        core = ip.split("%", 1)[0]
        # compact form: split on :: carefully
        if "::" in core:
            left, _, right = core.partition("::")
            left_parts = [p for p in left.split(":") if p]
            while len(left_parts) < 3:
                left_parts.append("0")
            hextets = left_parts[:3]
        else:
            parts = [p for p in core.split(":") if p]
            hextets = (parts + ["0", "0", "0"])[:3]
        return ":".join(hextets) + "::"
    return ip[:64] if ip else "—"


def short_ua(raw: str | None) -> str:
    ua = re.sub(r"\s+", " ", (raw or "").strip())
    if not ua:
        return "—"
    if len(ua) <= UA_MAX:
        return ua
    return ua[: UA_MAX - 1] + "…"


def normalize_path(path: str | None) -> str:
    p = (path or "/").split("?", 1)[0] or "/"
    if len(p) > PATH_MAX:
        return p[: PATH_MAX - 1] + "…"
    return p


def should_skip(path: str, method: str) -> bool:
    p = normalize_path(path)
    if p in _SKIP_EXACT:
        return True
    if any(p.startswith(pref) for pref in _SKIP_PREFIXES):
        return True
    # Não logar o próprio access-log em loop de refresh (GET lista).
    if p.startswith("/admin/sistema/access-log") and method.upper() == "GET":
        return True
    return False


def wants_detail(*, path: str, method: str, autenticado: bool) -> bool:
    p = normalize_path(path)
    m = method.upper()
    if autenticado:
        return True
    if p.startswith("/admin"):
        return True
    if m in _WRITE_METHODS:
        return True
    return False


def client_ip_from_headers(
    *,
    client_host: str | None,
    x_forwarded_for: str | None,
    x_real_ip: str | None,
) -> str:
    if x_forwarded_for:
        return x_forwarded_for
    if x_real_ip:
        return x_real_ip
    return client_host or ""


def status_class(status: int) -> str:
    if status < 200:
        return "1xx"
    if status < 300:
        return "2xx"
    if status < 400:
        return "3xx"
    if status < 500:
        return "4xx"
    return "5xx"


def record_hit(
    *,
    method: str,
    path: str,
    status: int,
    quem: str | None,
    quem_tipo: str,
    ip_raw: str | None,
    ua_raw: str | None,
    autenticado: bool,
    ts: str | None = None,
) -> None:
    """Grava detalhe ou agregado conforme a política. Nunca levanta."""
    try:
        if should_skip(path, method):
            return
        p = normalize_path(path)
        m = method.upper()
        st = int(status)
        agora = ts or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        dia = agora[:10]
        ip = truncate_ip(ip_raw)
        ua = short_ua(ua_raw)
        if wants_detail(path=p, method=m, autenticado=autenticado):
            _insert_detail(
                ts=agora,
                quem=(quem or "—").strip() or "—",
                quem_tipo=quem_tipo or "anon",
                method=m,
                path=p,
                status=st,
                ip_trunc=ip,
                ua_curto=ua,
            )
        else:
            _bump_agg(
                dia=dia,
                method=m,
                path=p,
                status_cls=status_class(st),
            )
    except Exception:
        return


def _insert_detail(
    *,
    ts: str,
    quem: str,
    quem_tipo: str,
    method: str,
    path: str,
    status: int,
    ip_trunc: str,
    ua_curto: str,
) -> None:
    with db.get_db() as conn:
        conn.execute(
            """
            INSERT INTO access_log
              (ts, quem, quem_tipo, method, path, status, ip_trunc, ua_curto)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (ts, quem, quem_tipo, method, path, status, ip_trunc, ua_curto),
        )


def _bump_agg(*, dia: str, method: str, path: str, status_cls: str) -> None:
    with db.get_db() as conn:
        conn.execute(
            """
            INSERT INTO access_log_agg (dia, method, path, status_cls, hits)
            VALUES (?, ?, ?, ?, 1)
            ON CONFLICT(dia, method, path, status_cls)
            DO UPDATE SET hits = hits + 1
            """,
            (dia, method, path, status_cls),
        )


def list_hits(
    *,
    quem: str | None = None,
    path: str | None = None,
    method: str | None = None,
    dia: str | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    args: list[Any] = []
    if quem:
        clauses.append("lower(quem) LIKE ?")
        args.append(f"%{quem.strip().casefold()}%")
    if path:
        clauses.append("path LIKE ?")
        args.append(f"%{path.strip()}%")
    if method:
        clauses.append("method = ?")
        args.append(method.strip().upper())
    if dia:
        clauses.append("substr(ts, 1, 10) = ?")
        args.append(dia.strip()[:10])
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    lim = max(1, min(int(limit), 2000))
    sql = (
        "SELECT id, ts, quem, quem_tipo, method, path, status, ip_trunc, ua_curto "
        f"FROM access_log{where} ORDER BY ts DESC, id DESC LIMIT ?"
    )
    args.append(lim)
    with db.get_db() as conn:
        rows = conn.execute(sql, args).fetchall()
    return [dict(r) for r in rows]


def list_agg(
    *,
    path: str | None = None,
    method: str | None = None,
    dia: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    args: list[Any] = []
    if path:
        clauses.append("path LIKE ?")
        args.append(f"%{path.strip()}%")
    if method:
        clauses.append("method = ?")
        args.append(method.strip().upper())
    if dia:
        clauses.append("dia = ?")
        args.append(dia.strip()[:10])
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    lim = max(1, min(int(limit), 1000))
    sql = (
        "SELECT dia, method, path, status_cls, hits FROM access_log_agg"
        f"{where} ORDER BY dia DESC, hits DESC LIMIT ?"
    )
    args.append(lim)
    with db.get_db() as conn:
        rows = conn.execute(sql, args).fetchall()
    return [dict(r) for r in rows]


def count_hits(
    *,
    quem: str | None = None,
    path: str | None = None,
    method: str | None = None,
    dia: str | None = None,
) -> int:
    clauses: list[str] = []
    args: list[Any] = []
    if quem:
        clauses.append("lower(quem) LIKE ?")
        args.append(f"%{quem.strip().casefold()}%")
    if path:
        clauses.append("path LIKE ?")
        args.append(f"%{path.strip()}%")
    if method:
        clauses.append("method = ?")
        args.append(method.strip().upper())
    if dia:
        clauses.append("substr(ts, 1, 10) = ?")
        args.append(dia.strip()[:10])
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    with db.get_db() as conn:
        row = conn.execute(
            f"SELECT COUNT(*) AS n FROM access_log{where}", args
        ).fetchone()
    return int(row["n"] if row else 0)


def oldest_ts() -> str | None:
    with db.get_db() as conn:
        row = conn.execute("SELECT MIN(ts) AS m FROM access_log").fetchone()
    return row["m"] if row and row["m"] else None


def cutoff_ts(now: datetime | None = None) -> str:
    base = now or datetime.now()
    return (base - timedelta(days=RETENCAO_DIAS)).strftime("%Y-%m-%d %H:%M:%S")


def purge_expired(
    *,
    agora: datetime | None = None,
    por: str = "sistema",
    force_record: bool = False,
) -> dict[str, Any]:
    """Remove hits/agregados mais velhos que a retenção; grava registro auditável."""
    now = agora or datetime.now()
    corte = cutoff_ts(now)
    corte_dia = corte[:10]
    with db.get_db() as conn:
        n_det = conn.execute(
            "SELECT COUNT(*) AS n FROM access_log WHERE ts < ?", (corte,)
        ).fetchone()["n"]
        n_agg = conn.execute(
            "SELECT COUNT(*) AS n FROM access_log_agg WHERE dia < ?", (corte_dia,)
        ).fetchone()["n"]
        registro = {
            "em": now.strftime("%Y-%m-%d %H:%M:%S"),
            "por": por,
            "antes_de": corte,
            "removidos_detalhe": int(n_det),
            "removidos_agregado": int(n_agg),
            "retencao_dias": RETENCAO_DIAS,
        }
        if int(n_det) == 0 and int(n_agg) == 0 and not force_record:
            return registro
        if int(n_det):
            conn.execute("DELETE FROM access_log WHERE ts < ?", (corte,))
        if int(n_agg):
            conn.execute("DELETE FROM access_log_agg WHERE dia < ?", (corte_dia,))
        conn.execute(
            """
            INSERT INTO access_log_purge
              (em, por, antes_de, removidos_detalhe, removidos_agregado, payload_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                registro["em"],
                por,
                corte,
                registro["removidos_detalhe"],
                registro["removidos_agregado"],
                json.dumps(registro, ensure_ascii=False),
            ),
        )
    db.set_meta(PURGE_META, json.dumps(registro, ensure_ascii=False))
    return registro


def ultimo_purge() -> dict[str, Any] | None:
    raw = db.get_meta(PURGE_META)
    if not raw:
        with db.get_db() as conn:
            row = conn.execute(
                "SELECT payload_json FROM access_log_purge ORDER BY id DESC LIMIT 1"
            ).fetchone()
        if not row:
            return None
        raw = row["payload_json"]
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def format_quando(ts: str, *, agora: datetime | None = None) -> dict[str, str]:
    """Célula dd/mm hh:mm:ss + title ISO; relativo só se < 24h."""
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
    for k in ("quem", "path", "metodo", "dia", "view"):
        v = filtros.get(k)
        if v:
            parts[k] = str(v)
    return urlencode(parts)
