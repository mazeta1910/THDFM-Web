from __future__ import annotations

import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
DB_PATH = DATA_DIR / "bolao.db"
EMBLEMAS_DIR = DATA_DIR / "emblemas"
COMPROVANTES_DIR = DATA_DIR / "comprovantes"
AVATARES_DIR = DATA_DIR / "avatars"

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "troque-esta-senha")
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")

TAXA_PIX = os.environ.get("TAXA_PIX", "matheuscps110@gmail.com")
TAXA_VALOR = os.environ.get("TAXA_VALOR", "5.00")
TAXA_VALOR_LABEL = os.environ.get("TAXA_VALOR_LABEL", "R$ 5,00")

JANELAS = ("ida", "volta", "fechado")
STATUS_PARTICIPANTE = ("pendente", "comprovante", "liberado")

COMPROVANTE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".pdf"}
COMPROVANTE_MAX_BYTES = 5 * 1024 * 1024
AVATAR_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
AVATAR_MAX_BYTES = 3 * 1024 * 1024
