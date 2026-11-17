"""CSRF para POSTs do painel admin (token na sessão)."""

from __future__ import annotations

import secrets
from urllib.parse import parse_qs

from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

SESSION_KEY = "csrf_token"
FORM_FIELD = "csrf_token"
HEADER_NAME = "x-csrf-token"

# Paths admin que mutam sem exigir CSRF (auth de entrada/saída).
_CSRF_EXEMPT_PREFIXES: tuple[str, ...] = (
    "/admin/login",
    "/admin/logout",
)


def ensure_csrf_token(request: Request) -> str:
    token = (request.session.get(SESSION_KEY) or "").strip()
    if not token:
        token = secrets.token_urlsafe(32)
        request.session[SESSION_KEY] = token
    return token


def csrf_ok(request: Request, form_token: str | None = None) -> bool:
    expected = (request.session.get(SESSION_KEY) or "").strip()
    got = (form_token or "").strip()
    if not got:
        got = (request.headers.get(HEADER_NAME) or request.headers.get("X-CSRF-Token") or "").strip()
    if not got:
        got = (request.query_params.get(FORM_FIELD) or "").strip()
    if not expected or not got:
        return False
    return secrets.compare_digest(expected, got)


def csrf_exempt(path: str) -> bool:
    path = path or ""
    return any(path == p or path.startswith(p + "/") for p in _CSRF_EXEMPT_PREFIXES)


def requires_csrf(method: str, path: str) -> bool:
    method = (method or "GET").upper()
    if method in ("GET", "HEAD", "OPTIONS", "TRACE"):
        return False
    if not path.startswith("/admin"):
        return False
    return not csrf_exempt(path)


def _token_from_urlencoded(body: bytes) -> str | None:
    try:
        parsed = parse_qs(body.decode("utf-8", errors="ignore"), keep_blank_values=True)
    except Exception:
        return None
    vals = parsed.get(FORM_FIELD) or []
    return vals[0] if vals else None


def _token_from_multipart(body: bytes, content_type: str) -> str | None:
    """Extrai csrf_token de multipart sem depender de boundary parser completo.

    Procura o campo nomeado; suficiente para o token ascii.
    """
    marker = f'name="{FORM_FIELD}"'.encode("ascii")
    idx = body.find(marker)
    if idx < 0:
        marker = f"name='{FORM_FIELD}'".encode("ascii")
        idx = body.find(marker)
    if idx < 0:
        return None
    # após headers do part, corpo começa depois de \r\n\r\n
    start = body.find(b"\r\n\r\n", idx)
    if start < 0:
        return None
    start += 4
    end = body.find(b"\r\n", start)
    if end < 0:
        end = len(body)
    raw = body[start:end].decode("utf-8", errors="ignore").strip()
    return raw or None


class AdminCsrfMiddleware:
    """Valida CSRF em métodos mutáveis sob /admin (exceto login/logout).

    Relê o body e o reapresenta ao app para Form()/JSON continuarem funcionando.
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method") or "GET"
        path = scope.get("path") or ""
        if not requires_csrf(method, path):
            await self.app(scope, receive, send)
            return

        body = b""
        while True:
            message = await receive()
            if message["type"] != "http.request":
                continue
            body += message.get("body", b"")
            if not message.get("more_body"):
                break

        async def receive_replay() -> Message:
            return {"type": "http.request", "body": body, "more_body": False}

        request = Request(scope, receive_replay)

        form_token: str | None = None
        content_type = (request.headers.get("content-type") or "").lower()
        if "application/x-www-form-urlencoded" in content_type:
            form_token = _token_from_urlencoded(body)
        elif "multipart/form-data" in content_type:
            form_token = _token_from_multipart(body, content_type)

        sent = False

        async def receive_once() -> Message:
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            return {"type": "http.request", "body": b"", "more_body": False}

        if csrf_ok(request, form_token):
            await self.app(scope, receive_once, send)
            return

        accept = (request.headers.get("accept") or "").lower()
        qs = (scope.get("query_string") or b"").decode("latin-1", errors="ignore")
        wants_json = "application/json" in accept or "format=json" in qs
        if wants_json:
            resp: Response = JSONResponse(
                {"ok": False, "erro": "CSRF inválido ou ausente"},
                status_code=403,
            )
        else:
            # Volta para a área admin com flash leve via query.
            referer = request.headers.get("referer") or "/admin"
            sep = "&" if "?" in referer else "?"
            if "erro=" not in referer:
                referer = f"{referer}{sep}erro=csrf"
            resp = RedirectResponse(referer, status_code=303)
        await resp(scope, receive_once, send)
