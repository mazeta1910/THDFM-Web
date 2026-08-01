"""Fixtures compartilhados dos testes HTTP."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import src.db as db
from src.config import ROOT_DIR

DEFAULT_ADMIN_USERS = "mazeta=senha-dono=Mazeta:dono"


@pytest.fixture()
def admin_users() -> str:
    """Sobrescreva nos módulos que precisam de mais admins."""
    return DEFAULT_ADMIN_USERS


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, admin_users: str):
    monkeypatch.chdir(ROOT_DIR)
    if admin_users:
        monkeypatch.setenv("ADMIN_USERS", admin_users)
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

    from src.app import app

    with TestClient(app) as c:
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
