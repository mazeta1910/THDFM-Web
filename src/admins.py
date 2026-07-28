from __future__ import annotations

import os
from dataclasses import dataclass

from src.config import ADMIN_PASSWORD


@dataclass(frozen=True)
class AdminUser:
    login: str
    senha: str
    nome: str


def _parse_admins() -> list[AdminUser]:
    """
    ADMIN_USERS=matheus=senha1=Matheus|gabriel=senha2=Gabriel Ramos|joao=senha3=João Vitor
    """
    raw = (os.environ.get("ADMIN_USERS") or "").strip()
    if not raw:
        # legado: uma senha só
        senha = os.environ.get("ADMIN_PASSWORD", ADMIN_PASSWORD)
        return [AdminUser(login="admin", senha=senha, nome="Admin")]

    out: list[AdminUser] = []
    for chunk in raw.split("|"):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = chunk.split("=", 2)
        if len(parts) < 2:
            continue
        login = parts[0].strip().lower()
        senha = parts[1]
        nome = parts[2].strip() if len(parts) > 2 and parts[2].strip() else login
        if login and senha:
            out.append(AdminUser(login=login, senha=senha, nome=nome))
    return out or [AdminUser(login="admin", senha=ADMIN_PASSWORD, nome="Admin")]


def list_admins() -> list[AdminUser]:
    return _parse_admins()


def autenticar_admin(login: str, senha: str) -> AdminUser | None:
    login_n = (login or "").strip().lower()
    for admin in _parse_admins():
        if admin.login == login_n and admin.senha == senha:
            return admin
    return None
