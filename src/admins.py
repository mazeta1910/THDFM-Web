from __future__ import annotations

import os
from dataclasses import dataclass

from src.config import ADMIN_PASSWORD

# Papéis do painel
# - dono: Mazeta — acesso total + gestão de username/senha
# - moderador: Ramos / João JEC — operação do bolão (Adminzinho)
PAPEIS = ("dono", "moderador")
PAPEL_LABEL = {
    "dono": "Dono",
    "moderador": "Moderador",
}
PAPEL_ALIASES = {
    "dono": "dono",
    "sagrado": "dono",
    "root": "dono",
    "owner": "dono",
    "calvo": "dono",
    "moderador": "moderador",
    "adminzinho": "moderador",
    "mod": "moderador",
    "staff": "moderador",
    "auxiliar": "moderador",
}


@dataclass(frozen=True)
class AdminUser:
    login: str
    senha: str
    nome: str
    papel: str = "moderador"

    @property
    def papel_label(self) -> str:
        return PAPEL_LABEL.get(self.papel, self.papel)

    @property
    def is_dono(self) -> bool:
        return self.papel == "dono"


def _normalizar_papel(raw: str, *, login: str) -> str:
    p = (raw or "").strip().casefold()
    if p in PAPEL_ALIASES:
        return PAPEL_ALIASES[p]
    # Padrão: mazeta = Dono; demais = Moderador (Adminzinho)
    if login.strip().lower() == "mazeta":
        return "dono"
    return "moderador"


def _split_nome_papel(nome_raw: str, *, login: str) -> tuple[str, str]:
    """Aceita 'Mazeta', 'Mazeta:dono' ou 'Ramos:adminzinho'."""
    raw = (nome_raw or "").strip()
    if ":" in raw:
        nome, talvez_papel = raw.rsplit(":", 1)
        chave = talvez_papel.strip().casefold()
        if chave in PAPEL_ALIASES:
            return (nome.strip() or login), PAPEL_ALIASES[chave]
    return raw or login, _normalizar_papel("", login=login)


def _parse_admins() -> list[AdminUser]:
    """
    ADMIN_USERS=mazeta=senha1=Mazeta:dono|ramos=senha2=Ramos:moderador|joaojec=senha3=João JEC:adminzinho

    Formato: login=senha=Nome[:papel]
    Papéis: dono | moderador (aliases: sagrado/root, adminzinho/mod/staff)
    Sem papel explícito: mazeta→dono; demais→moderador.
    """
    raw = (os.environ.get("ADMIN_USERS") or "").strip()
    if not raw:
        senha = os.environ.get("ADMIN_PASSWORD", ADMIN_PASSWORD)
        return [AdminUser(login="admin", senha=senha, nome="Admin", papel="dono")]

    out: list[AdminUser] = []
    for chunk in raw.split("|"):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = chunk.split("=", 2)
        if len(parts) < 2:
            continue
        login = parts[0].strip().lower()
        senha = parts[1].strip()
        nome_raw = parts[2].strip() if len(parts) > 2 and parts[2].strip() else login
        nome, papel = _split_nome_papel(nome_raw, login=login)
        if login and senha:
            out.append(AdminUser(login=login, senha=senha, nome=nome, papel=papel))
    return out or [
        AdminUser(login="admin", senha=ADMIN_PASSWORD, nome="Admin", papel="dono")
    ]


def list_admins() -> list[AdminUser]:
    return _parse_admins()


def get_admin(login: str) -> AdminUser | None:
    login_n = (login or "").strip().lower()
    for admin in _parse_admins():
        if admin.login == login_n:
            return admin
    return None


def autenticar_admin(login: str, senha: str) -> AdminUser | None:
    login_n = (login or "").strip().lower()
    for admin in _parse_admins():
        if admin.login == login_n and admin.senha == senha:
            return admin
    return None
