from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv

# IANA tz database — no Windows o CPython não embute os fusos; o pacote
# `tzdata` (em requirements.txt) fornece America/Sao_Paulo etc.
try:
    import tzdata  # noqa: F401
except ImportError:
    tzdata = None  # type: ignore[assignment]

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

# Encerramento das inscrições do bolão (America/Sao_Paulo).
try:
    _TZ_SP = ZoneInfo("America/Sao_Paulo")
except ZoneInfoNotFoundError as exc:
    raise RuntimeError(
        "Fuso America/Sao_Paulo indisponível. "
        "No Windows, rode: pip install tzdata"
    ) from exc
INSCRICAO_FECHA_EM = datetime(2026, 8, 1, 13, 30, tzinfo=_TZ_SP)

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

# Redes sociais da página THDFM (deixe vazio para ocultar o ícone)
SOCIAL_FACEBOOK = os.environ.get(
    "SOCIAL_FACEBOOK", "https://www.facebook.com/thdfm"
).strip()
SOCIAL_X = os.environ.get("SOCIAL_X", "https://x.com/tecnicoshdfm").strip()
SOCIAL_INSTAGRAM = os.environ.get(
    "SOCIAL_INSTAGRAM", "https://www.instagram.com/thdfm_/"
).strip()
SOCIAL_YOUTUBE = os.environ.get("SOCIAL_YOUTUBE", "").strip()
SOCIAL_TIKTOK = os.environ.get("SOCIAL_TIKTOK", "").strip()
SOCIAL_WHATSAPP = os.environ.get("SOCIAL_WHATSAPP", "").strip() or ADMIN_WHATSAPP

# Convite do grupo da THDFM no WhatsApp
WHATSAPP_GROUP_URL = os.environ.get(
    "WHATSAPP_GROUP_URL",
    "https://chat.whatsapp.com/DQX2VHp6aQl6ILcwHT7nRz",
).strip()

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
NOME_MAX_LEN = 30


def inscricao_aberta(*, agora: datetime | None = None) -> bool:
    """True enquanto ainda dá para se inscrever no bolão."""
    now = agora or datetime.now(_TZ_SP)
    if now.tzinfo is None:
        now = now.replace(tzinfo=_TZ_SP)
    return now < INSCRICAO_FECHA_EM

