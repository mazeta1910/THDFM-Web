"""Fixtures compartilhados dos testes HTTP."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

import src.db as db
from src.config import ROOT_DIR

DEFAULT_ADMIN_USERS = "mazeta=senha-dono=Mazeta:dono"
_CSRF_META_RE = re.compile(
    r'<meta\s+name=["\']csrf-token["\']\s+content=["\']([^"\']+)["\']',
    re.I,
)


def csrf_token_for(client: TestClient, path: str = "/admin/visao") -> str:
    """Lê o token CSRF da meta do HTML (após login admin)."""
    cached = getattr(client, "_thdfm_csrf", None)
    if cached:
        return str(cached)
    r = client.get(path)
    m = _CSRF_META_RE.search(r.text or "")
    assert m, f"csrf-token meta ausente em {path} (status={r.status_code})"
    token = m.group(1)
    setattr(client, "_thdfm_csrf", token)
    return token


def _inject_csrf(client: TestClient, url: str, data: Any, headers: dict | None) -> tuple[Any, dict]:
    """Injeta csrf_token em POSTs /admin (exceto login/logout)."""
    path = str(url or "")
    if not path.startswith("/admin"):
        return data, headers or {}
    if path.startswith("/admin/login") or path.startswith("/admin/logout"):
        return data, headers or {}
    token = csrf_token_for(client)
    hdrs = dict(headers or {})
    if "x-csrf-token" not in {k.lower() for k in hdrs}:
        hdrs["X-CSRF-Token"] = token
    if data is None:
        return data, hdrs
    if isinstance(data, dict):
        out = dict(data)
        out.setdefault("csrf_token", token)
        return out, hdrs
    return data, hdrs


@pytest.fixture()
def admin_users() -> str:
    """Sobrescreva nos módulos que precisam de mais admins."""
    return DEFAULT_ADMIN_USERS


def confirmar_email_teste(participante_id: int, email: str | None = None) -> None:
    """Marca e-mail confirmado (atalho de testes; o app real exige o link)."""
    part = db.get_participante(participante_id)
    assert part
    dest = email or f"user{participante_id}@thdfm.test"
    db.definir_email_participante(participante_id, dest)


def limpar_email_teste(participante_id: int) -> None:
    """Remove e-mail/confirmação para exercitar o gate nos testes."""
    with db.get_db() as conn:
        conn.execute(
            "UPDATE participantes SET email = NULL, email_confirmado_em = NULL WHERE id = ?",
            (participante_id,),
        )
        conn.execute(
            "UPDATE email_verify_tokens SET usado_em = datetime('now', 'localtime') "
            "WHERE participante_id = ? AND usado_em IS NULL",
            (participante_id,),
        )


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, admin_users: str):
    monkeypatch.chdir(ROOT_DIR)
    if admin_users:
        monkeypatch.setenv("ADMIN_USERS", admin_users)
    monkeypatch.setenv("ACERVO_SKIP_IMPORT", "1")
    db.DB_PATH = tmp_path / "test.db"
    (tmp_path / "avatars").mkdir(exist_ok=True)
    (tmp_path / "comprovantes").mkdir(exist_ok=True)
    db.init_db()
    try:
        import src.app as app_mod

        if hasattr(app_mod, "_AUTH_ATTEMPTS"):
            app_mod._AUTH_ATTEMPTS.clear()
    except Exception:
        pass

    # Demais testes: participante liberado já nasce com e-mail confirmado.
    # Os testes do gate usam limpar_email_teste() depois de criar.
    _criar_orig = db.criar_participante

    def _criar_com_email(*args, **kwargs):
        part = _criar_orig(*args, **kwargs)
        if part and part.get("status") == "liberado" and not part.get("email_confirmado_em"):
            try:
                confirmar_email_teste(int(part["id"]))
                part = db.get_participante(part["id"]) or part
            except Exception:
                pass
        return part

    monkeypatch.setattr(db, "criar_participante", _criar_com_email)

    from src.app import app

    with TestClient(app) as c:
        _orig_post = c.post

        def post_with_csrf(url, content=None, data=None, files=None, json=None, **kwargs):
            headers = kwargs.pop("headers", None)
            if json is None and files is None:
                data, headers = _inject_csrf(c, str(url), data, headers)
            elif json is not None or files is not None:
                # JSON/multipart: só header
                _, headers = _inject_csrf(c, str(url), None, headers)
            if headers is not None:
                kwargs["headers"] = headers
            return _orig_post(url, content=content, data=data, files=files, json=json, **kwargs)

        c.post = post_with_csrf  # type: ignore[method-assign]
        yield c


def login_admin(
    client: TestClient,
    login: str = "mazeta",
    senha: str = "senha-dono",
) -> None:
    r = client.post(
        "/admin/login",
        data={"login": login, "password": senha},
        follow_redirects=False,
    )
    assert r.status_code == 303
    # Admin também passa pelo gate de e-mail — confirma no fixture.
    part = db.garantir_participante_admin(login, login.capitalize())
    confirmar_email_teste(part["id"], f"{login}@thdfm.test")
    # Esquenta CSRF na sessão (meta em /admin/visao).
    setattr(client, "_thdfm_csrf", None)
    csrf_token_for(client)
