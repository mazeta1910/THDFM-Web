"""Sistema do painel: catálogo de rotas (introspecção) e snapshot por deploy."""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from typing import Any

from fastapi import FastAPI
from fastapi.routing import APIRoute

from src import db

SNAPSHOT_META = "sistema_rotas_snapshot"
HTTP_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS")

# Paths sempre públicos (sem sessão).
_PUBLIC_EXACT = frozenset(
    {
        "/",
        "/home",
        "/health",
        "/favicon.ico",
        "/ads.txt",
        "/robots.txt",
        "/sitemap.xml",
        "/privacidade",
        "/termos",
        "/em-desenvolvimento",
        "/login",
        "/entrar",
        "/esqueci-senha",
        "/loguin",
        "/regras",
        "/classificacao",
        "/transparencia",
        "/inscricao",
        "/hall-lendas",
        "/xonhometro",
        "/grid",
        "/grid/ranking",
        "/grid/bugs",
    }
)

_PUBLIC_PREFIXES = (
    "/static/",
    "/acervo/",
    "/grupo/",
    "/confirmar-email/",
    "/redefinir-senha/",
    "/prototipo/",
)

_TOKEN_MARKERS = ("{token}", "/p/{")


def classify_auth(path: str) -> str:
    """Credencial necessária: publico | sessao | token."""
    if any(m in path for m in _TOKEN_MARKERS):
        return "token"
    if path.startswith("/admin"):
        return "sessao"
    if path.startswith("/grid/api/admin"):
        return "sessao"
    if path.startswith("/conta/") or path.startswith("/bolao/") or path.startswith(
        "/meu-perfil"
    ):
        return "sessao"
    if path.startswith("/perfil/") and (
        path.endswith("/karma")
        or "/recados" in path
        or path.endswith("/nutela")
    ):
        return "sessao"
    if path in _PUBLIC_EXACT:
        return "publico"
    if any(path.startswith(p) for p in _PUBLIC_PREFIXES):
        return "publico"
    if path.startswith("/grid/api/"):
        return "sessao"
    # Default conservador: sessão (melhor listar demais do que marcar público à toa).
    return "sessao"


def classify_papel(path: str) -> str:
    """Papel mínimo: dono | admin | —."""
    if path.startswith("/admin/sistema"):
        return "dono"
    if path.startswith("/admin/credenciais"):
        return "dono"
    if path.startswith("/admin/permissoes"):
        return "dono"
    if path.startswith("/admin") or path.startswith("/grid/api/admin"):
        return "admin"
    return "—"


def classify_dominio(path: str) -> str:
    if path.startswith("/admin/sistema"):
        return "sistema"
    if path.startswith("/admin"):
        return "admin"
    if path.startswith("/bolao/") or path.startswith("/p/"):
        return "bolao"
    if path.startswith("/grid"):
        return "grid"
    if path.startswith("/grupo/") or path.startswith("/xonhometro"):
        return "comunidade"
    if path.startswith("/conta/") or path.startswith("/meu-perfil") or path.startswith(
        "/perfil/"
    ):
        return "conta"
    if path.startswith("/static") or path in {
        "/favicon.ico",
        "/robots.txt",
        "/ads.txt",
        "/sitemap.xml",
        "/health",
    }:
        return "sistema"
    return "site"


def _route_methods(route: APIRoute) -> list[str]:
    methods = sorted(
        m for m in (route.methods or set()) if m in HTTP_METHODS and m != "HEAD"
    )
    # Starlette adds HEAD alongside GET; keep HEAD only if alone.
    if not methods and route.methods:
        methods = sorted(m for m in route.methods if m in HTTP_METHODS)
    return methods


def introspect_routes(app: FastAPI) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        path = route.path
        if path.startswith("/openapi") or path in {"/docs", "/redoc", "/docs/oauth2-redirect"}:
            continue
        methods = _route_methods(route)
        if not methods:
            continue
        auth = classify_auth(path)
        papel = classify_papel(path)
        dominio = classify_dominio(path)
        for method in methods:
            rows.append(
                {
                    "method": method,
                    "path": path,
                    "auth": auth,
                    "papel": papel,
                    "dominio": dominio,
                    "name": route.name or "",
                    "sig": f"{method} {path}",
                }
            )
    rows.sort(key=lambda r: (r["path"], r["method"]))
    return rows


def filter_routes(
    rows: list[dict[str, Any]],
    *,
    metodo: str | None = None,
    auth: str | None = None,
    papel: str | None = None,
    dominio: str | None = None,
    q: str | None = None,
    sem_auth: bool = False,
) -> list[dict[str, Any]]:
    out = rows
    if sem_auth:
        out = [r for r in out if r["auth"] == "publico"]
    if metodo:
        m = metodo.strip().upper()
        out = [r for r in out if r["method"] == m]
    if auth:
        a = auth.strip().lower()
        out = [r for r in out if r["auth"] == a]
    if papel:
        p = papel.strip().lower()
        out = [r for r in out if r["papel"] == p]
    if dominio:
        d = dominio.strip().lower()
        out = [r for r in out if r["dominio"] == d]
    if q:
        needle = q.strip().casefold()
        out = [
            r
            for r in out
            if needle in r["path"].casefold()
            or needle in (r["name"] or "").casefold()
            or needle in r["method"].casefold()
        ]
    return out


def snapshot_payload(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "em": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "sigs": sorted(r["sig"] for r in rows),
        "n": len(rows),
    }


def load_snapshot() -> dict[str, Any] | None:
    raw = db.get_meta(SNAPSHOT_META)
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or "sigs" not in data:
        return None
    return data


def save_snapshot(rows: list[dict[str, Any]]) -> dict[str, Any]:
    payload = snapshot_payload(rows)
    db.set_meta(SNAPSHOT_META, json.dumps(payload, ensure_ascii=False))
    return payload


def diff_snapshot(
    current: list[dict[str, Any]], previous: dict[str, Any] | None
) -> dict[str, Any]:
    cur = {r["sig"] for r in current}
    if not previous:
        return {
            "tem_snapshot": False,
            "adicionadas": sorted(cur),
            "removidas": [],
            "em": None,
            "n_antes": 0,
            "n_agora": len(cur),
        }
    prev = set(previous.get("sigs") or [])
    return {
        "tem_snapshot": True,
        "adicionadas": sorted(cur - prev),
        "removidas": sorted(prev - cur),
        "em": previous.get("em"),
        "n_antes": int(previous.get("n") or len(prev)),
        "n_agora": len(cur),
    }


def rows_to_csv(rows: list[dict[str, Any]]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(
        buf,
        fieldnames=["method", "path", "auth", "papel", "dominio", "name"],
        extrasaction="ignore",
    )
    writer.writeheader()
    for r in rows:
        writer.writerow(r)
    return buf.getvalue()


def rows_to_json(rows: list[dict[str, Any]]) -> str:
    slim = [
        {
            "method": r["method"],
            "path": r["path"],
            "auth": r["auth"],
            "papel": r["papel"],
            "dominio": r["dominio"],
            "name": r["name"],
        }
        for r in rows
    ]
    return json.dumps(slim, ensure_ascii=False, indent=2)


def metodos_presentes(rows: list[dict[str, Any]]) -> list[str]:
    found = {r["method"] for r in rows}
    return [m for m in HTTP_METHODS if m in found]
