"""Hall das Lendas — constantes e formatação."""

from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo

TZ_SP = ZoneInfo("America/Sao_Paulo")

BORDAS: tuple[dict[str, str], ...] = (
    {"id": "anel", "rotulo": "Anel ouro", "sample": "A"},
    {"id": "duplo", "rotulo": "Traço duplo", "sample": "D"},
    {"id": "brilho", "rotulo": "Brilho", "sample": "B"},
    {"id": "laurel", "rotulo": "Laureado", "sample": "L"},
)
BORDA_IDS = frozenset(b["id"] for b in BORDAS)
BORDA_PADRAO = "anel"
HALL_POR_PAGINA = 10


def borda_ok(borda: str | None) -> str:
    b = (borda or "").strip().lower()
    return b if b in BORDA_IDS else BORDA_PADRAO


def borda_rotulo(borda: str | None) -> str:
    bid = borda_ok(borda)
    for item in BORDAS:
        if item["id"] == bid:
            return item["rotulo"]
    return "Anel ouro"


def parse_valor_centavos(raw: str | int | float | None) -> int:
    """Aceita 500, '500', '500,00', 'R$ 500.00' → centavos."""
    if raw is None:
        raise ValueError("informe o valor da doação")
    if isinstance(raw, bool):
        raise ValueError("valor inválido")
    if isinstance(raw, int):
        if raw < 0:
            raise ValueError("valor não pode ser negativo")
        # int já em centavos se >= 1000? Treat plain int as reais when small API...
        # Admin forms send reais as string. If int from JSON, treat as centavos only if explicit.
        return raw
    if isinstance(raw, float):
        if raw < 0:
            raise ValueError("valor não pode ser negativo")
        return int(round(raw * 100))
    s = str(raw).strip()
    if not s:
        raise ValueError("informe o valor da doação")
    s = re.sub(r"[Rr]\$\s*", "", s).strip()
    s = s.replace(" ", "")
    if re.fullmatch(r"\d+", s):
        return int(s) * 100
    if "," in s and "." in s:
        # 1.234,56
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        reais = float(s)
    except ValueError as exc:
        raise ValueError("valor inválido") from exc
    if reais < 0:
        raise ValueError("valor não pode ser negativo")
    return int(round(reais * 100))


def format_valor_brl(centavos: int) -> str:
    v = max(0, int(centavos))
    reais = v // 100
    cents = v % 100
    corpo = f"{reais:,}".replace(",", ".")
    return f"R$ {corpo},{cents:02d}"


def format_quando(iso_local: str | None) -> str:
    raw = (iso_local or "").strip()
    if not raw:
        return "—"
    try:
        # 'YYYY-MM-DD HH:MM:SS' ou ISO
        if "T" in raw:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=TZ_SP)
            else:
                dt = dt.astimezone(TZ_SP)
        else:
            dt = datetime.strptime(raw[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=TZ_SP)
        return dt.strftime("%d/%m/%Y · %H:%M")
    except ValueError:
        return raw


def agora_local_iso() -> str:
    return datetime.now(TZ_SP).strftime("%Y-%m-%d %H:%M:%S")


HALL_HERO_META = "hall_hero_html"
HALL_HERO_DEFAULT = (
    "<p>Quem apoia o projeto com doação entra aqui — para sempre.<br>"
    "Ordenado pelo total doado.</p>"
)
HALL_RECADO_MAX_HTML = 8000

_HALL_HTML_TAGS = frozenset(
    {
        "p",
        "br",
        "strong",
        "b",
        "em",
        "i",
        "u",
        "a",
        "img",
        "ul",
        "ol",
        "li",
        "blockquote",
        "h2",
        "h3",
        "div",
        "span",
        "hr",
        "font",
    }
)
_HALL_HTML_ATTRS = {
    "a": frozenset({"href", "title", "target", "rel"}),
    "img": frozenset({"src", "alt", "width", "height", "loading"}),
    "span": frozenset({"style"}),
    "div": frozenset({"style"}),
    "p": frozenset({"style"}),
    "font": frozenset({"face", "size", "color"}),
}
_HALL_STYLE_PROPS = frozenset(
    {
        "font-family",
        "font-size",
        "font-weight",
        "font-style",
        "text-decoration",
        "color",
    }
)
_HALL_FONT_SIZES = frozenset({"1", "2", "3", "4", "5", "6", "7"})


def _hall_hero_url_ok(attr: str, value: str) -> bool:
    v = (value or "").strip()
    if not v:
        return False
    low = v.lower()
    if attr == "href":
        if low.startswith(("javascript:", "data:", "vbscript:")):
            return False
        return low.startswith(("http://", "https://", "/", "#", "mailto:"))
    if attr == "src":
        if low.startswith(("javascript:", "data:", "vbscript:")):
            return False
        return low.startswith(("/hall-hero/", "/static/", "https://", "http://"))
    return True


def _hall_style_ok(raw: str) -> str:
    """Mantém só propriedades tipográficas seguras."""
    from html import escape

    out: list[str] = []
    for part in (raw or "").split(";"):
        if ":" not in part:
            continue
        prop, _, val = part.partition(":")
        p = prop.strip().lower()
        v = val.strip()
        if p not in _HALL_STYLE_PROPS or not v:
            continue
        low = v.lower()
        if "expression" in low or "url(" in low or "javascript:" in low:
            continue
        if p == "font-size":
            # 12px, 1.2em, 120%, medium…
            if not re.fullmatch(
                r"(\d+(\.\d+)?(px|pt|em|rem|%)|xx-small|x-small|small|medium|large|x-large|xx-large|smaller|larger)",
                low,
            ):
                continue
        if p == "color":
            if not re.fullmatch(
                r"(#[0-9a-f]{3,8}|rgb\(\s*\d+\s*,\s*\d+\s*,\s*\d+\s*\)|[a-z]+)",
                low,
            ):
                continue
        out.append(f"{p}: {escape(v, quote=True)}")
    return "; ".join(out)


def sanitize_hall_html(raw: str | None, *, empty_default: str = "") -> str:
    """HTML permitido no Hall (hero/recado): texto formatado + imagens."""
    from html import escape
    from html.parser import HTMLParser

    class _San(HTMLParser):
        def __init__(self) -> None:
            super().__init__(convert_charrefs=True)
            self.out: list[str] = []

        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            t = tag.lower()
            if t not in _HALL_HTML_TAGS:
                return
            if t == "br":
                self.out.append("<br>")
                return
            if t == "hr":
                self.out.append("<hr>")
                return
            allowed = _HALL_HTML_ATTRS.get(t, frozenset())
            parts = [f"<{t}"]
            for name, val in attrs:
                n = (name or "").lower()
                if n not in allowed or val is None:
                    continue
                if n in ("href", "src") and not _hall_hero_url_ok(n, val):
                    continue
                if n == "target" and val not in ("_blank", "_self"):
                    continue
                if n == "size" and str(val).strip() not in _HALL_FONT_SIZES:
                    continue
                if n == "style":
                    cleaned = _hall_style_ok(val)
                    if not cleaned:
                        continue
                    parts.append(f' style="{cleaned}"')
                    continue
                parts.append(f' {n}="{escape(val, quote=True)}"')
                if t == "a" and n == "href" and 'rel="' not in "".join(parts):
                    parts.append(' rel="noopener noreferrer"')
            if t == "img" and 'loading="' not in "".join(parts):
                parts.append(' loading="lazy"')
            parts.append(">")
            self.out.append("".join(parts))

        def handle_endtag(self, tag: str) -> None:
            t = tag.lower()
            if t in _HALL_HTML_TAGS and t not in ("br", "hr", "img"):
                self.out.append(f"</{t}>")

        def handle_data(self, data: str) -> None:
            self.out.append(escape(data))

        def handle_entityref(self, name: str) -> None:
            self.out.append(f"&{name};")

        def handle_charref(self, name: str) -> None:
            self.out.append(f"&#{name};")

    html = (raw or "").strip()
    if not html:
        return empty_default
    parser = _San()
    try:
        parser.feed(html)
        parser.close()
    except Exception:
        return empty_default
    cleaned = "".join(parser.out).strip()
    cleaned = re.sub(r"(?i)<(p|div|span|font)>\s*</\1>", "", cleaned).strip()
    if len(cleaned) > HALL_RECADO_MAX_HTML:
        cleaned = cleaned[:HALL_RECADO_MAX_HTML]
    return cleaned or empty_default


def sanitize_hall_hero_html(raw: str | None) -> str:
    """HTML do header do Hall (fallback para o texto padrão)."""
    return sanitize_hall_html(raw, empty_default=HALL_HERO_DEFAULT)


def sanitize_hall_recado_html(raw: str | None) -> str:
    """HTML do recado da lenda (pode ficar vazio)."""
    return sanitize_hall_html(raw, empty_default="")
