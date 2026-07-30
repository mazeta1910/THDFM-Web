from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

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

# URL pública do túnel (ex.: https://xxxx.trycloudflare.com). Sem isso, o admin
# mostra o host da requisição atual (pode ser IP da rede local).
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")

# WhatsApp do admin (só dígitos com DDI, ex.: 5511999999999) — botão no modal de inscrição
ADMIN_WHATSAPP = os.environ.get("ADMIN_WHATSAPP", "").strip()
ADMIN_WHATSAPP_MSG = os.environ.get(
    "ADMIN_WHATSAPP_MSG",
    "Olá! Fiz a inscrição no bolão THDFM. Aguardo a confirmação e o meu link.",
)

JANELAS = ("ida", "volta", "fechado")
STATUS_PARTICIPANTE = ("pendente", "comprovante", "liberado")

FASES = (
    {"id": "oitavas", "label": "Oitavas", "slots": 8},
    {"id": "quartas", "label": "Quartas", "slots": 4},
    {"id": "semis", "label": "Semis", "slots": 2},
    {"id": "final", "label": "Final", "slots": 1},
)
FASE_IDS = tuple(f["id"] for f in FASES)

COMPROVANTE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".pdf"}
COMPROVANTE_MAX_BYTES = 5 * 1024 * 1024
AVATAR_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
AVATAR_MAX_BYTES = 3 * 1024 * 1024
AVATAR_PADRAO_STEM = "avatar-padrao"
