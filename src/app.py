"""THDFM Bolão Copa do Brasil — app FastAPI."""

from __future__ import annotations

import os
import re
import time
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    PlainTextResponse,
    RedirectResponse,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from src import db
from src.admins import autenticar_admin, get_admin, list_admins
from src.config import (
    ADMIN_WHATSAPP,
    ADMIN_WHATSAPP_MSG,
    AVATAR_EXTS,
    AVATAR_MAX_BYTES,
    AVATAR_PADRAO_STEM,
    AVATARES_DIR,
    COMPROVANTE_EXTS,
    COMPROVANTE_MAX_BYTES,
    COMPROVANTES_DIR,
    EMBLEMAS_DIR,
    FASES,
    FASE_IDS,
    JANELAS,
    NOME_MAX_LEN,
    PUBLIC_BASE_URL,
    ROOT_DIR,
    SECRET_KEY,
    SOCIAL_FACEBOOK,
    SOCIAL_INSTAGRAM,
    SOCIAL_TIKTOK,
    SOCIAL_WHATSAPP,
    SOCIAL_X,
    SOCIAL_YOUTUBE,
    TAXA_PIX,
    TAXA_VALOR_LABEL,
    WHATSAPP_GROUP_URL,
)
from src.ranking import calcular_classificacao, confirmar_rodada, desfazer_ultima_rodada, faixa_zonas
from src.scoring import agregado_empatado
from src.seed_data import emblema_url, formatar_inicio_jogo, nome_clube_curto
from src.transparencia import montar_portal

load_dotenv(ROOT_DIR / ".env")

app = FastAPI(title="Bolão THDFM — Copa do Brasil")
app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("SECRET_KEY", SECRET_KEY),
    same_site="lax",
    max_age=60 * 60 * 24 * 14,  # 14 dias — evita perder o painel ao fechar a aba
)

TEMPLATES = Jinja2Templates(directory=str(ROOT_DIR / "templates"))

STATIC = ROOT_DIR / "static"
STATIC.mkdir(exist_ok=True)
EMBLEMAS_DIR.mkdir(parents=True, exist_ok=True)
COMPROVANTES_DIR.mkdir(parents=True, exist_ok=True)
AVATARES_DIR.mkdir(parents=True, exist_ok=True)

app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")
app.mount("/emblemas", StaticFiles(directory=str(EMBLEMAS_DIR)), name="emblemas")
app.mount("/avatars", StaticFiles(directory=str(AVATARES_DIR)), name="avatars")

# Rate limit em memória: chave → timestamps de tentativas
_AUTH_ATTEMPTS: dict[str, list[float]] = defaultdict(list)
_AUTH_LIMIT = 8
_AUTH_WINDOW_SEC = 15 * 60


def _auth_rate_ok(key: str) -> bool:
    now = time.time()
    bucket = [t for t in _AUTH_ATTEMPTS.get(key, []) if now - t < _AUTH_WINDOW_SEC]
    _AUTH_ATTEMPTS[key] = bucket
    return len(bucket) < _AUTH_LIMIT


def _auth_rate_hit(key: str) -> None:
    _AUTH_ATTEMPTS[key].append(time.time())


def avatar_padrao_path() -> Path | None:
    for ext in (".jpg", ".jpeg", ".png", ".webp"):
        candidate = STATIC / f"{AVATAR_PADRAO_STEM}{ext}"
        if candidate.is_file():
            return candidate
    return None


def avatar_padrao_url() -> str | None:
    path = avatar_padrao_path()
    if not path:
        return None
    return f"/static/{path.name}?v={int(path.stat().st_mtime)}"


def avatar_url(avatar_path: str | None) -> str | None:
    """URL da foto do participante ou da foto padrão do bolão."""
    if avatar_path:
        return f"/avatars/{avatar_path}"
    return avatar_padrao_url()


TEMPLATES.env.globals["emblema_url"] = emblema_url
TEMPLATES.env.globals["formatar_inicio_jogo"] = formatar_inicio_jogo
TEMPLATES.env.globals["nome_clube_curto"] = nome_clube_curto
TEMPLATES.env.globals["wa_msg_link"] = db.mensagem_whatsapp_link
TEMPLATES.env.globals["avatar_url"] = avatar_url
TEMPLATES.env.globals["avatar_padrao_url"] = avatar_padrao_url
TEMPLATES.env.globals["listra_emoji_efetivo"] = db.listra_emoji_efetivo
TEMPLATES.env.globals["listra_texto_contexto"] = db.listra_texto_contexto
TEMPLATES.env.globals["listra_linha_compartilhar"] = db.listra_linha_compartilhar
TEMPLATES.env.filters["celular_fmt"] = db.formatar_celular
TEMPLATES.env.filters["celular_wa"] = db.celular_whatsapp


def _listra_marcar_destaque(texto: str, destaque: str) -> str:
    """Marca o trecho compartilhável dentro do texto (HTML escapado)."""
    from markupsafe import Markup, escape

    base = texto or ""
    dest = (destaque or "").strip()
    if not dest or dest not in base:
        return Markup(str(escape(base)))
    out: list[str] = []
    cursor = 0
    while True:
        idx = base.find(dest, cursor)
        if idx < 0:
            out.append(str(escape(base[cursor:])))
            break
        out.append(str(escape(base[cursor:idx])))
        out.append(f'<mark class="listra-destaque">{escape(dest)}</mark>')
        cursor = idx + len(dest)
    return Markup("".join(out))


TEMPLATES.env.filters["listra_marcar_destaque"] = _listra_marcar_destaque


@app.on_event("startup")
def _startup() -> None:
    db.init_db()
    from src.seed_demo import limpar_demo

    limpar_demo()


def _promover_admin_da_conta(request: Request) -> bool:
    """Se a conta do bolão está vinculada a um admin do .env, abre o painel.

    Um login basta: quem entrou pelo Entrar com a conta vinculada
    (mazeta/ramos/joaojec) já libera o painel — sem /admin/login.
    """
    if request.session.get("admin_login"):
        return True
    token = request.session.get("participante_token")
    if not token:
        return False
    part = db.get_participante_por_token(token)
    if not part:
        return False
    login = (part.get("admin_login") or "").strip().lower()
    if not login:
        # Username igual ao login do .env (ramos, joaojec, mazeta) também vale.
        username = (part.get("username") or "").strip().lower()
        if username and get_admin(username):
            try:
                db.vincular_admin_login(part["id"], username)
            except Exception:
                pass
            login = username
            part = db.get_participante(part["id"]) or part
    admin = get_admin(login) if login else None
    if not admin:
        return False
    _estabelecer_sessao_admin(request, admin, token_preferido=part.get("token"))
    return True


def admin_ok(request: Request) -> bool:
    if request.session.get("admin_login"):
        return True
    return _promover_admin_da_conta(request)


def admin_nome(request: Request) -> str:
    return request.session.get("admin_nome") or request.session.get("admin_login") or ""


def admin_papel(request: Request) -> str:
    raw = (request.session.get("admin_role") or "").strip().lower()
    if raw in ("dono", "moderador"):
        return raw
    login = (request.session.get("admin_login") or "").strip().lower()
    admin = get_admin(login) if login else None
    if admin:
        return admin.papel
    return "moderador"


def is_dono(request: Request) -> bool:
    return admin_ok(request) and admin_papel(request) == "dono"


def require_dono(request: Request) -> RedirectResponse | None:
    if not admin_ok(request):
        return _redirect_acesso("entrar")
    if not is_dono(request):
        return RedirectResponse(
            "/admin?erro=" + quote("Só o Dono pode fazer isso."),
            status_code=303,
        )
    return None


def get_ui_mode(request: Request) -> str:
    """Chrome Admin vs Site. Só o Dono pode pré-visualizar o site."""
    if not admin_ok(request):
        return "user"
    if not is_dono(request):
        return "admin"
    raw = (request.cookies.get("thdfm_ui_mode") or "admin").strip().lower()
    return raw if raw in ("admin", "user") else "admin"


def render(request: Request, name: str, **ctx):
    token = request.session.get("participante_token")
    part_nav = db.get_participante_por_token(token) if token else None
    is_adm = admin_ok(request)
    path = request.url.path
    # Ao usar o painel (/admin/*), volta o chrome admin — Classificação etc. não trocam o menu
    on_admin_area = path.startswith("/admin") and path != "/admin/login"
    force_admin_cookie = bool(is_adm and on_admin_area)
    ui = "admin" if force_admin_cookie else get_ui_mode(request)

    ctx.setdefault("is_admin", is_adm)
    ctx.setdefault("ui_mode", ui)
    ctx.setdefault("admin_papel", admin_papel(request) if is_adm else "")
    ctx.setdefault("is_dono", is_dono(request) if is_adm else False)
    ctx.setdefault(
        "admin_papel_label",
        {"dono": "Dono", "moderador": "Moderador"}.get(
            admin_papel(request), "Moderador"
        )
        if is_adm
        else "",
    )
    # Admin logado: garante participante pelo login (não pelo nick)
    if is_adm:
        login = (request.session.get("admin_login") or "").strip().lower()
        nome_cfg = admin_nome(request)
        if login:
            try:
                part_nav = db.garantir_participante_admin(
                    login,
                    nome_cfg,
                    token_preferido=(part_nav or {}).get("token") or token,
                )
                _remember_participante(request, part_nav["token"])
                ctx["admin_nome"] = part_nav.get("nome") or nome_cfg
            except Exception:
                # Não derruba o painel inteiro se a migração/vínculo falhar
                ctx.setdefault("admin_nome", nome_cfg)
        else:
            ctx.setdefault("admin_nome", nome_cfg)
    else:
        ctx.setdefault("admin_nome", admin_nome(request))
    ctx.setdefault("participante_nav", part_nav)
    if "social_links" not in ctx:
        ctx.update({k: v for k, v in _taxa_ctx().items() if k == "social_links"})
    if is_adm and "admin_pendentes_count" not in ctx:
        try:
            if "participantes" in ctx:
                ctx["admin_pendentes_count"] = sum(
                    1
                    for p in ctx["participantes"]
                    if p.get("status") != "liberado" and not p.get("recusado_em")
                )
            else:
                ctx["admin_pendentes_count"] = sum(
                    1
                    for p in db.list_participantes()
                    if p.get("status") != "liberado" and not p.get("recusado_em")
                )
        except Exception:
            ctx["admin_pendentes_count"] = 0
    resp = TEMPLATES.TemplateResponse(request, name, ctx)
    if force_admin_cookie:
        resp.set_cookie(
            "thdfm_ui_mode",
            "admin",
            max_age=60 * 60 * 24 * 180,
            httponly=False,
            samesite="lax",
            path="/",
        )
    return resp


def _remember_participante(request: Request, token: str) -> None:
    request.session["participante_token"] = token


def _set_cookie_ui_admin(resp: RedirectResponse) -> RedirectResponse:
    resp.set_cookie(
        "thdfm_ui_mode",
        "admin",
        max_age=60 * 60 * 24 * 180,
        httponly=False,
        samesite="lax",
        path="/",
    )
    return resp


def _estabelecer_sessao_admin(
    request: Request,
    admin,
    *,
    token_preferido: str | None = None,
) -> None:
    """Grava sessão do painel (Dono/Moderador)."""
    request.session["admin_login"] = admin.login
    request.session["admin_nome"] = admin.nome
    request.session["admin_role"] = admin.papel
    request.session.pop("admin", None)
    request.session.pop("admin_opt_out", None)
    try:
        part = db.garantir_participante_admin(
            admin.login,
            admin.nome,
            token_preferido=token_preferido or request.session.get("participante_token"),
        )
        request.session["admin_nome"] = part.get("nome") or admin.nome
        _remember_participante(request, part["token"])
    except Exception:
        pass


def _tentar_admin_com_senha(
    request: Request,
    *,
    usuario: str,
    senha: str,
    part: dict | None = None,
) -> bool:
    """Se usuário/senha baterem com ADMIN_USERS, abre sessão do painel."""
    admin = autenticar_admin(usuario, senha)
    if not admin and part and part.get("admin_login"):
        admin = autenticar_admin(part.get("admin_login") or "", senha)
    if not admin:
        return False
    _estabelecer_sessao_admin(
        request,
        admin,
        token_preferido=(part or {}).get("token"),
    )
    return True


def _redirect_credenciais(token: str) -> RedirectResponse:
    return RedirectResponse(f"/p/{token}/credenciais", status_code=303)


def _gate_credenciais(part: dict) -> RedirectResponse | None:
    """Se liberado sem username/senha, obriga o setup antes de palpites/conta."""
    if db.precisa_credenciais(part):
        return _redirect_credenciais(part["token"])
    return None


def _enrich_confrontos(confrontos: list) -> list:
    for c in confrontos:
        c["ida"] = next((j for j in c["jogos"] if j["perna"] == "ida"), None)
        c["volta"] = next((j for j in c["jogos"] if j["perna"] == "volta"), None)
    return confrontos


def _taxa_ctx() -> dict:
    wa_digits = re.sub(r"\D+", "", ADMIN_WHATSAPP or os.environ.get("ADMIN_WHATSAPP", ""))
    wa_msg = os.environ.get("ADMIN_WHATSAPP_MSG", ADMIN_WHATSAPP_MSG)
    wa_url = ""
    if wa_digits:
        from urllib.parse import quote

        wa_url = f"https://wa.me/{wa_digits}?text={quote(wa_msg)}"
    social_wa = re.sub(r"\D+", "", SOCIAL_WHATSAPP or "")
    social_wa_url = f"https://wa.me/{social_wa}" if social_wa else ""
    group_url = (
        WHATSAPP_GROUP_URL
        or os.environ.get("WHATSAPP_GROUP_URL", "")
        or ""
    ).strip()
    return {
        "taxa_pix": os.environ.get("TAXA_PIX", TAXA_PIX),
        "taxa_valor_label": os.environ.get("TAXA_VALOR_LABEL", TAXA_VALOR_LABEL),
        "admin_whatsapp_url": wa_url,
        "whatsapp_group_url": group_url,
        "social_links": {
            "facebook": SOCIAL_FACEBOOK or os.environ.get("SOCIAL_FACEBOOK", ""),
            "x": SOCIAL_X or os.environ.get("SOCIAL_X", ""),
            "instagram": SOCIAL_INSTAGRAM or os.environ.get("SOCIAL_INSTAGRAM", ""),
            "youtube": SOCIAL_YOUTUBE or os.environ.get("SOCIAL_YOUTUBE", ""),
            "tiktok": SOCIAL_TIKTOK or os.environ.get("SOCIAL_TIKTOK", ""),
            # Preferimos o grupo da THDFM no rodapé; fallback wa.me do admin
            "whatsapp": group_url or social_wa_url,
        },
    }


def _destino_sessao(request: Request) -> str | None:
    """Home/portal nunca redireciona por sessão.

    Admin logado e participante com token continuam em / (portal THDFM).
    O painel fica em /admin; o bolão em /p/{token}.
    """
    return None


def _client_ip(request: Request) -> str:
    forwarded = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    if forwarded:
        return forwarded
    if request.client and request.client.host:
        return request.client.host
    return ""


def _render_home(request: Request):
    return render(
        request,
        "home.html",
        janela=db.get_janela(),
        **_taxa_ctx(),
    )


@app.get("/")
def raiz(request: Request):
    dest = _destino_sessao(request)
    if dest:
        return RedirectResponse(dest, status_code=303)
    return _render_home(request)


@app.get("/home")
def home(request: Request):
    dest = _destino_sessao(request)
    if dest:
        return RedirectResponse(dest, status_code=303)
    return _render_home(request)


def _redirect_acesso(
    modo: str,
    *,
    erro: str | None = None,
    usuario: str | None = None,
    enviado: bool = False,
) -> RedirectResponse:
    parts = [f"acesso={modo}"]
    if erro:
        parts.append(f"erro={quote(erro)}")
    if usuario:
        parts.append(f"usuario={quote(usuario)}")
    if enviado:
        parts.append("enviado=1")
    return RedirectResponse("/?" + "&".join(parts), status_code=303)


def _redirect_loguin(
    *,
    erro: str | None = None,
    usuario: str | None = None,
    sucesso: bool = False,
) -> RedirectResponse:
    parts = ["acesso=loguin"]
    if erro:
        parts.append(f"erro={quote(erro)}")
    if usuario:
        parts.append(f"usuario={quote(usuario)}")
    if sucesso:
        parts.append("sucesso=1")
    return RedirectResponse("/?" + "&".join(parts), status_code=303)


@app.get("/login", response_class=HTMLResponse)
def login_get(request: Request):
    token = request.session.get("participante_token")
    if token:
        part = db.get_participante_por_token(token)
        if part and part.get("status") == "liberado":
            if db.precisa_credenciais(part):
                return _redirect_credenciais(part["token"])
            return RedirectResponse(f"/p/{part['token']}", status_code=303)
    return _redirect_acesso(
        "recuperar",
        erro=request.query_params.get("erro"),
        enviado=request.query_params.get("enviado") == "1",
    )


@app.get("/entrar", response_class=HTMLResponse)
def entrar_get(request: Request):
    token = request.session.get("participante_token")
    if token:
        part = db.get_participante_por_token(token)
        if part and part.get("status") == "liberado":
            if db.precisa_credenciais(part):
                return _redirect_credenciais(part["token"])
            return RedirectResponse(f"/p/{part['token']}", status_code=303)
    return _redirect_acesso(
        "entrar",
        erro=request.query_params.get("erro"),
        usuario=request.query_params.get("usuario") or "",
    )


@app.post("/entrar")
async def entrar_post(
    request: Request,
    usuario: str = Form(""),
    senha: str = Form(""),
):
    usuario = (usuario or "").strip()
    senha = senha or ""
    ip = _client_ip(request)
    rate_key = f"entrar:{ip}:{usuario.casefold()}"

    if not usuario or not senha:
        return _redirect_acesso(
            "entrar",
            erro="Informe usuário e senha",
            usuario=usuario,
        )

    # Credenciais do painel (.env) também funcionam no Entrar → vão direto ao admin
    if _tentar_admin_com_senha(request, usuario=usuario, senha=senha):
        return _set_cookie_ui_admin(RedirectResponse("/admin", status_code=303))

    # Marlon não entra pela porta civilizada — só pelo LOGUIN
    if _tentativa_e_do_marlon(usuario):
        return _redirect_loguin(
            erro=_MSG_MARLON_PORTA_ERRADA,
            usuario=usuario if _eh_marlon(usuario) else "Marlon Wietzikowski",
        )

    if not _auth_rate_ok(rate_key):
        return _redirect_acesso(
            "entrar",
            erro="Muitas tentativas. Aguarde alguns minutos.",
            usuario=usuario,
        )

    part = db.autenticar_por_username(usuario, senha)
    _auth_rate_hit(rate_key)
    if not part:
        return _redirect_acesso(
            "entrar",
            erro="Usuário ou senha incorretos",
            usuario=usuario,
        )

    # Cinto e suspensório: conta do Marlon nunca autentica em /entrar
    if _participante_eh_marlon(part):
        return _redirect_loguin(
            erro=_MSG_MARLON_PORTA_ERRADA,
            usuario="Marlon Wietzikowski",
        )

    _remember_participante(request, part["token"])
    # Conta ligada a um admin: senha do .env → painel; senha do bolão → mesma sessão
    if _tentar_admin_com_senha(request, usuario=usuario, senha=senha, part=part):
        return _set_cookie_ui_admin(RedirectResponse("/admin", status_code=303))
    # Vinculado ao .env: libera o painel na mesma sessão (sem 2º login)
    if _promover_admin_da_conta(request):
        return _set_cookie_ui_admin(RedirectResponse("/admin", status_code=303))
    return RedirectResponse(f"/p/{part['token']}", status_code=303)


_MSG_MARLON_PORTA_ERRADA = (
    "Marlon detectado. Pelo amord, a sua porta é o LOGUIN."
)

_MSG_LOGUIN_SO_MARLON = (
    "Este LOGUIN é exclusivo do Marlon Wietzikowski. Use Entrar."
)


def _eh_marlon(nome: str) -> bool:
    n = re.sub(r"\s+", " ", (nome or "").strip().casefold())
    n = n.replace("ł", "l")
    if not n:
        return False
    if n == "marlon":
        return True
    return "marlon" in n and ("wietz" in n or "wietzikowski" in n)


def _participante_eh_marlon(part: dict | None) -> bool:
    if not part:
        return False
    return _eh_marlon(part.get("nome") or "") or _eh_marlon(part.get("username") or "")


def _tentativa_e_do_marlon(usuario: str) -> bool:
    """True se o campo usuário aponta (ou parece apontar) para o Marlon."""
    if _eh_marlon(usuario):
        return True
    part = db.get_participante_por_username(usuario)
    if _participante_eh_marlon(part):
        return True
    part_nome = db.get_participante_por_nome(usuario)
    if _participante_eh_marlon(part_nome):
        return True
    return False


def _buscar_participante_marlon() -> dict | None:
    """Melhor esforço: acha o participante liberado do Marlon."""
    for nome in ("Marlon Wietzikowski", "Marlon"):
        part = db.get_participante_por_nome(nome)
        if part and part.get("status") == "liberado" and _participante_eh_marlon(part):
            return part
    for part in db.list_participantes():
        if part.get("status") == "liberado" and _participante_eh_marlon(part):
            return part
    return None


@app.get("/loguin", response_class=HTMLResponse)
def loguin_get(request: Request):
    return _redirect_loguin(
        erro=request.query_params.get("erro"),
        usuario=request.query_params.get("usuario") or "",
        sucesso=request.query_params.get("sucesso") == "1",
    )


@app.post("/loguin")
async def loguin_post(
    request: Request,
    usuario: str = Form(""),
    senha: str = Form(""),
):
    usuario = (usuario or "").strip()
    senha = (senha or "").strip()
    if not usuario or not senha:
        return _redirect_loguin(
            erro="Preenche usuário e senha do LOGUIN, Marlon.",
            usuario=usuario,
        )
    if not _eh_marlon(usuario):
        return _redirect_loguin(
            erro=_MSG_LOGUIN_SO_MARLON,
            usuario=usuario,
        )

    # Exclusivo Marlon: se existir conta no bolão, autentica por aqui
    # (nunca pela /entrar). Sem hash ainda: qualquer senha libera o ritual.
    part = _buscar_participante_marlon()
    if part and part.get("password_hash"):
        if not db.verificar_senha(senha, part.get("password_hash")):
            return _redirect_loguin(
                erro="Senha do LOGUIN errada, Marlon.",
                usuario=usuario,
            )
        _remember_participante(request, part["token"])
        request.session["loguin_marlon"] = True
        if db.precisa_credenciais(part):
            return _redirect_credenciais(part["token"])
        return RedirectResponse(
            f"/p/{part['token']}?msg={quote('LOGUIN efetuado. É florida.')}",
            status_code=303,
        )

    if part:
        _remember_participante(request, part["token"])
        request.session["loguin_marlon"] = True
        if db.precisa_credenciais(part):
            return _redirect_credenciais(part["token"])
        return RedirectResponse(
            f"/p/{part['token']}?msg={quote('LOGUIN efetuado. É florida.')}",
            status_code=303,
        )

    request.session["loguin_marlon"] = True
    return _redirect_loguin(sucesso=True)


@app.post("/login")
async def login_post(request: Request, celular: str = Form(...)):
    celular_raw = (celular or "").strip()
    ip = _client_ip(request)

    try:
        celular_ok = db.normalizar_celular(celular_raw)
    except ValueError:
        return _redirect_acesso(
            "recuperar",
            erro="Informe um celular válido com DDD",
        )

    if not db.recuperacao_rate_limit_ok(celular=celular_ok, ip=ip or None):
        # Mesma UX pública — não revela se o número existe
        return _redirect_acesso("recuperar", enviado=True)

    part = db.get_participante_liberado_por_celular(celular_ok)
    if part:
        db.criar_pedido_recuperacao(part["id"], celular_ok, ip=ip or None)

    return _redirect_acesso("recuperar", enviado=True)


@app.get("/regras", response_class=HTMLResponse)
def regras(request: Request):
    return render(request, "regras.html", **_taxa_ctx())


def _pagina_em_breve(request: Request, *, titulo: str, secao: str, lead: str | None = None):
    return render(
        request,
        "em_breve.html",
        titulo=titulo,
        secao=secao,
        lead=lead,
        **_taxa_ctx(),
    )


@app.get("/grupo/bans", response_class=HTMLResponse)
def grupo_bans(request: Request):
    return _pagina_em_breve(
        request,
        titulo="Contador de Bans",
        secao="Grupo do WhatsApp",
        lead="O placar oficial de banimentos do grupo. Em breve.",
    )


def _participante_sessao(request: Request) -> dict | None:
    token = request.session.get("participante_token")
    if not token:
        return None
    return db.get_participante_por_token(token)


def _listra_caps(request: Request) -> dict:
    """Capacidades da Listra para o visitante atual."""
    is_adm = admin_ok(request)
    part = _participante_sessao(request)
    perm = (
        db.get_listra_permissao(part["id"])
        if part and part.get("status") == "liberado"
        else None
    )
    pode_add = is_adm or bool(perm and perm.get("pode_adicionar"))
    pode_env = is_adm or bool(perm and perm.get("pode_enviar"))
    return {
        "is_admin": is_adm,
        "participante": part,
        "pode_adicionar": pode_add,
        "pode_enviar": pode_env,
    }


@app.get("/grupo/listra", response_class=HTMLResponse)
def grupo_listra(request: Request):
    from src.listra_seed import LISTRA_ANO_ATUAL

    caps = _listra_caps(request)
    listras = db.list_listra_por_anos()
    return render(
        request,
        "listra.html",
        listras=listras,
        ano_atual=LISTRA_ANO_ATUAL,
        total_frases=sum(l["total"] for l in listras),
        pode_adicionar=caps["pode_adicionar"],
        pode_enviar=caps["pode_enviar"],
        participante_listra=caps["participante"],
        listra_meliantes=db.list_listra_meliantes(),
        msg=request.query_params.get("msg"),
        erro=request.query_params.get("erro"),
        **_taxa_ctx(),
    )


@app.get("/grupo/listra/export.txt")
def grupo_listra_export(request: Request, ano: int | None = None):
    """Texto da Listra de um ano para o botão Enviar no WhatsApp."""
    from src.listra_seed import LISTRA_ANO_ATUAL, LISTRA_ANOS

    caps = _listra_caps(request)
    if not caps["pode_enviar"]:
        raise HTTPException(status_code=403, detail="Sem permissão para exportar a Listra.")
    ano_ok = int(ano) if ano is not None else LISTRA_ANO_ATUAL
    if ano_ok not in LISTRA_ANOS:
        raise HTTPException(status_code=404, detail="Ano da Listra não encontrado.")
    return PlainTextResponse(
        db.listra_texto_whatsapp(ano=ano_ok),
        media_type="text/plain; charset=utf-8",
        headers={"Cache-Control": "no-store"},
    )


@app.post("/grupo/listra")
def grupo_listra_criar(
    request: Request,
    texto: str = Form(...),
    responsavel: str = Form(...),
    ano: int | None = Form(None),
    emoji: str = Form(""),
    destaque: str = Form(""),
):
    from src.listra_seed import LISTRA_ANO_ATUAL

    caps = _listra_caps(request)
    if not caps["pode_adicionar"]:
        return RedirectResponse(
            "/grupo/listra?erro="
            + quote("Você não tem permissão para adicionar frases na Listra."),
            status_code=303,
        )
    part = caps["participante"]
    try:
        frase = db.criar_listra_frase(
            texto,
            responsavel,
            criado_por_id=part["id"] if part else None,
            ano=ano if ano is not None else LISTRA_ANO_ATUAL,
            emoji=emoji,
            destaque=destaque,
        )
    except ValueError as exc:
        return RedirectResponse(
            f"/grupo/listra?erro={quote(str(exc))}",
            status_code=303,
        )
    return RedirectResponse(
        f"/grupo/listra?msg={quote('Frase adicionada à Listra')}"
        f"#listra-frase-{frase['id']}",
        status_code=303,
    )


@app.post("/grupo/listra/atualizar")
def grupo_listra_atualizar(
    request: Request,
    frase_id: int = Form(...),
    texto: str = Form(...),
    responsavel: str = Form(""),
    emoji: str = Form(""),
    destaque: str = Form(""),
):
    if not admin_ok(request):
        return RedirectResponse(
            "/grupo/listra?erro="
            + quote("Só a administração pode editar frases."),
            status_code=303,
        )
    try:
        db.atualizar_listra_frase(
            frase_id,
            texto=texto,
            responsavel=responsavel,
            emoji=emoji,
            destaque=destaque,
        )
    except ValueError as exc:
        return RedirectResponse(
            f"/grupo/listra?erro={quote(str(exc))}#listra-frase-{int(frase_id)}",
            status_code=303,
        )
    return RedirectResponse(
        f"/grupo/listra?msg={quote('Edição feita com sucesso')}"
        f"#listra-frase-{int(frase_id)}",
        status_code=303,
    )


@app.post("/grupo/listra/apagar")
def grupo_listra_apagar(request: Request, frase_id: int = Form(...)):
    if not admin_ok(request):
        return RedirectResponse(
            "/grupo/listra?erro=" + quote("Só a administração pode apagar frases."),
            status_code=303,
        )
    frase = db.get_listra_frase(frase_id)
    if not frase or not db.apagar_listra_frase(frase_id):
        return RedirectResponse(
            f"/grupo/listra?erro={quote('Frase não encontrada')}",
            status_code=303,
        )
    ano = frase.get("ano")
    ancora = f"#listra-ano-{ano}" if ano else ""
    return RedirectResponse(
        f"/grupo/listra?msg={quote('Frase removida')}{ancora}",
        status_code=303,
    )


@app.get("/admin/listra", response_class=HTMLResponse)
def admin_listra(request: Request):
    if not admin_ok(request):
        return _redirect_acesso("entrar")
    return render(
        request,
        "admin_listra.html",
        participantes=db.list_listra_permissoes_com_participantes(),
        meliantes=db.list_listra_meliantes_detalhe(),
        total_frases=len(db.list_listra_frases()),
        msg=request.query_params.get("msg"),
        erro=request.query_params.get("erro"),
        **_taxa_ctx(),
    )


@app.post("/admin/listra/meliantes")
def admin_listra_meliante_criar(request: Request, nome: str = Form(...)):
    if not admin_ok(request):
        return _redirect_acesso("entrar")
    try:
        criado = db.criar_listra_meliante(nome)
    except ValueError as exc:
        return RedirectResponse(
            f"/admin/listra?erro={quote(str(exc))}#meliantes",
            status_code=303,
        )
    return RedirectResponse(
        f"/admin/listra?msg={quote(f'Meliante {criado} adicionado')}#meliantes",
        status_code=303,
    )


@app.post("/admin/listra/meliantes/apagar")
def admin_listra_meliante_apagar(request: Request, nome: str = Form(...)):
    if not admin_ok(request):
        return _redirect_acesso("entrar")
    if not db.apagar_listra_meliante(nome):
        return RedirectResponse(
            f"/admin/listra?erro={quote('Meliante não encontrado')}#meliantes",
            status_code=303,
        )
    return RedirectResponse(
        f"/admin/listra?msg={quote('Meliante removido da lista')}#meliantes",
        status_code=303,
    )


@app.post("/admin/listra/permissoes")
async def admin_listra_permissoes(request: Request):
    if not admin_ok(request):
        return _redirect_acesso("entrar")
    form = await request.form()
    participantes = db.list_listra_permissoes_com_participantes()
    itens: list[tuple[int, bool, bool]] = []
    for p in participantes:
        pid = int(p["id"])
        add = form.get(f"add_{pid}") == "1"
        env = form.get(f"env_{pid}") == "1"
        itens.append((pid, add, env))
    try:
        db.salvar_listra_permissoes_lote(itens)
    except ValueError as exc:
        return RedirectResponse(
            f"/admin/listra?erro={quote(str(exc))}",
            status_code=303,
        )
    return RedirectResponse(
        f"/admin/listra?msg={quote('Permissões da Listra atualizadas')}",
        status_code=303,
    )


@app.get("/grupo/copypastas", response_class=HTMLResponse)
def grupo_copypastas(request: Request):
    return _pagina_em_breve(
        request,
        titulo="Copypastas",
        secao="Grupo do WhatsApp",
        lead="O acervo de copypastas chega em breve.",
    )


@app.get("/grupo/cardapio", response_class=HTMLResponse)
def grupo_cardapio(request: Request):
    return _pagina_em_breve(
        request,
        titulo="Cardápio",
        secao="Acervo Xonha",
        lead="O cardápio do Xonha ainda não abriu. Em breve.",
    )


@app.get("/xonhometro", response_class=HTMLResponse)
def xonhometro(request: Request):
    return render(
        request,
        "xonhometro.html",
        eventos=db.list_xonha_eventos(),
        stats=db.xonha_stats(),
        **_taxa_ctx(),
    )


@app.get("/admin/xonhometro", response_class=HTMLResponse)
def admin_xonhometro(request: Request):
    if not admin_ok(request):
        return _redirect_acesso("entrar")
    return render(
        request,
        "admin_xonhometro.html",
        eventos=db.list_xonha_eventos(),
        stats=db.xonha_stats(),
        msg=request.query_params.get("msg"),
        erro=request.query_params.get("erro"),
        **_taxa_ctx(),
    )


@app.post("/admin/xonhometro")
def admin_xonhometro_criar(
    request: Request,
    tipo: str = Form(...),
    data: str = Form(...),
    hora: str = Form(""),
    motivo: str = Form(""),
):
    if not admin_ok(request):
        return _redirect_acesso("entrar")
    try:
        db.criar_xonha_evento(tipo, data, motivo, hora=hora)
    except ValueError as exc:
        return RedirectResponse(
            f"/admin/xonhometro?erro={quote(str(exc))}",
            status_code=303,
        )
    tipo_n = (tipo or "").strip().lower()
    label = {"saida": "Saída", "volta": "Volta", "banimento": "Banimento"}.get(
        tipo_n, "Registro"
    )
    return RedirectResponse(
        f"/admin/xonhometro?msg={quote(label + ' registrado')}",
        status_code=303,
    )


@app.post("/admin/xonhometro/atualizar")
def admin_xonhometro_atualizar(
    request: Request,
    evento_id: int = Form(...),
    tipo: str = Form(...),
    data: str = Form(...),
    hora: str = Form(""),
    motivo: str = Form(""),
):
    if not admin_ok(request):
        return _redirect_acesso("entrar")
    try:
        db.atualizar_xonha_evento(
            evento_id, tipo=tipo, data=data, motivo=motivo, hora=hora
        )
    except ValueError as exc:
        return RedirectResponse(
            f"/admin/xonhometro?erro={quote(str(exc))}",
            status_code=303,
        )
    return RedirectResponse(
        f"/admin/xonhometro?msg={quote('Evento atualizado')}",
        status_code=303,
    )


@app.post("/admin/xonhometro/apagar")
def admin_xonhometro_apagar(request: Request, evento_id: int = Form(...)):
    if not admin_ok(request):
        return _redirect_acesso("entrar")
    if not db.apagar_xonha_evento(evento_id):
        return RedirectResponse(
            f"/admin/xonhometro?erro={quote('Evento não encontrado')}",
            status_code=303,
        )
    return RedirectResponse(
        f"/admin/xonhometro?msg={quote('Evento apagado')}",
        status_code=303,
    )


@app.get("/transparencia", response_class=HTMLResponse)
def transparencia(request: Request):
    fase_atual = db.get_fase_atual()
    fase_idx = FASE_IDS.index(fase_atual) if fase_atual in FASE_IDS else 0
    fases_ui = [
        {
            **f,
            "unlocked": FASE_IDS.index(f["id"]) <= fase_idx,
            "ativa": f["id"] == fase_atual,
        }
        for f in FASES
    ]

    fase = request.query_params.get("fase") or fase_atual
    if fase not in FASE_IDS:
        fase = fase_atual
    # Fases futuras bloqueadas — igual Resultados / Meus Palpites
    if FASE_IDS.index(fase) > fase_idx:
        return RedirectResponse(
            f"/transparencia?fase={fase_atual}&perna=ida",
            status_code=303,
        )

    perna = request.query_params.get("perna") or "ida"
    if perna not in ("ida", "volta"):
        perna = "ida"
    janela = db.get_janela()
    volta_liberada = janela != "ida"
    if perna == "volta" and not volta_liberada:
        return RedirectResponse(
            f"/transparencia?fase={fase}&perna=ida",
            status_code=303,
        )
    tabelas = [t for t in montar_portal(fase) if t.get("perna") == perna]
    return render(
        request,
        "transparencia.html",
        fase=fase,
        fases=fases_ui,
        perna=perna,
        janela=janela,
        volta_liberada=volta_liberada,
        tabelas=tabelas,
    )


@app.get("/admin/palpites", response_class=HTMLResponse)
def admin_palpites(request: Request):
    if not admin_ok(request):
        return _redirect_acesso("entrar")

    fase_atual = db.get_fase_atual()
    fase_idx = FASE_IDS.index(fase_atual) if fase_atual in FASE_IDS else 0
    fases_ui = [
        {
            **f,
            "unlocked": FASE_IDS.index(f["id"]) <= fase_idx,
            "ativa": f["id"] == fase_atual,
        }
        for f in FASES
    ]

    fase = request.query_params.get("fase") or fase_atual
    if fase not in FASE_IDS:
        fase = fase_atual
    if FASE_IDS.index(fase) > fase_idx:
        return RedirectResponse(
            f"/admin/palpites?fase={fase_atual}&perna=ida",
            status_code=303,
        )

    perna = request.query_params.get("perna") or "ida"
    if perna not in ("ida", "volta"):
        perna = "ida"
    janela = db.get_janela()
    volta_liberada = janela != "ida"
    if perna == "volta" and not volta_liberada:
        return RedirectResponse(
            f"/admin/palpites?fase={fase}&perna=ida",
            status_code=303,
        )

    tabelas = [
        t for t in montar_portal(fase, exigir_resultado=False) if t.get("perna") == perna
    ]
    return render(
        request,
        "admin_palpites.html",
        fase=fase,
        fases=fases_ui,
        perna=perna,
        janela=janela,
        volta_liberada=volta_liberada,
        tabelas=tabelas,
    )


@app.get("/classificacao", response_class=HTMLResponse)
def classificacao(request: Request):
    if not admin_ok(request) and not request.session.get("participante_token"):
        return RedirectResponse("/inscricao", status_code=303)

    historico = db.list_rodadas_historico()
    rodada_param = (request.query_params.get("rodada") or "atual").strip()
    rodada_sel = None
    modo_historico = False

    if rodada_param not in ("", "atual"):
        try:
            rid = int(rodada_param)
        except ValueError:
            rid = None
        if rid is not None:
            rodada_sel = db.get_rodada_historico(rid)
        if not rodada_sel:
            return RedirectResponse("/classificacao", status_code=303)
        linhas = rodada_sel["linhas"]
        modo_historico = True
        fase = rodada_sel["fase"]
        janela = rodada_sel["janela"]
    else:
        linhas = calcular_classificacao()
        fase = db.get_meta("fase_atual", "oitavas")
        janela = db.get_janela()

    return render(
        request,
        "classificacao.html",
        linhas=linhas,
        zona_faixa=faixa_zonas(len(linhas)),
        janela=janela,
        fase=fase,
        historico=historico,
        modo_historico=modo_historico,
        rodada_atual_id=rodada_sel["id"] if rodada_sel else None,
        rodada_sel=rodada_sel,
    )


@app.get("/inscricao", response_class=HTMLResponse)
def inscricao_get(request: Request):
    draft = request.session.pop("inscricao_draft", None) or {}
    return render(
        request,
        "inscricao.html",
        msg=request.query_params.get("msg"),
        erro=request.query_params.get("erro"),
        sucesso=request.query_params.get("sucesso") == "1",
        form_nome=draft.get("nome") or "",
        form_celular=draft.get("celular") or "",
        **_taxa_ctx(),
    )


def _inscricao_erro(request: Request, erro: str, *, nome: str = "", celular: str = ""):
    from urllib.parse import quote

    request.session["inscricao_draft"] = {
        "nome": (nome or "").strip(),
        "celular": (celular or "").strip(),
    }
    return RedirectResponse(f"/inscricao?erro={quote(erro)}", status_code=303)


@app.post("/inscricao")
async def inscricao_post(
    request: Request,
    nome: str = Form(...),
    celular: str = Form(...),
    comprovante: UploadFile = File(...),
):
    nome = nome.strip()
    celular_raw = (celular or "").strip()
    if not nome:
        return _inscricao_erro(
            request, "Informe seu nome", nome=nome, celular=celular_raw
        )
    if len(nome) > NOME_MAX_LEN:
        return _inscricao_erro(
            request,
            f"Nome com no máximo {NOME_MAX_LEN} caracteres",
            nome=nome[:NOME_MAX_LEN],
            celular=celular_raw,
        )
    if nome.casefold() == "daniel":
        return TEMPLATES.TemplateResponse(request, "acesso_proibido.html", {})

    try:
        celular_ok = db.normalizar_celular(celular_raw)
    except ValueError:
        return _inscricao_erro(
            request,
            "Informe um celular valido com DDD",
            nome=nome,
            celular=celular_raw,
        )

    filename = comprovante.filename or ""
    ext = Path(filename).suffix.lower()
    if ext not in COMPROVANTE_EXTS:
        return _inscricao_erro(
            request,
            "Envie jpg, png, webp ou pdf",
            nome=nome,
            celular=celular_raw,
        )

    data = await comprovante.read()
    if not data:
        return _inscricao_erro(
            request, "Arquivo vazio", nome=nome, celular=celular_raw
        )
    if len(data) > COMPROVANTE_MAX_BYTES:
        return _inscricao_erro(
            request, "Arquivo maior que 5MB", nome=nome, celular=celular_raw
        )

    try:
        part = db.criar_participante(nome, status="pendente", celular=celular_ok)
    except Exception:
        return _inscricao_erro(
            request,
            "Nome ja cadastrado. Fale com o admin",
            nome=nome,
            celular=celular_raw,
        )

    safe = re.sub(r"[^a-zA-Z0-9_-]+", "", nome)[:40] or "user"
    rel = f"{part['id']}_{int(time.time())}_{safe}{ext}"
    dest = COMPROVANTES_DIR / rel
    dest.write_bytes(data)
    db.salvar_comprovante(part["id"], rel)

    request.session.pop("inscricao_draft", None)
    return RedirectResponse("/inscricao?sucesso=1", status_code=303)


@app.get("/p/{token}", response_class=HTMLResponse)
def pagina_palpites(request: Request, token: str):
    part = db.get_participante_por_token(token)
    if not part:
        raise HTTPException(404, "Link inválido")
    _remember_participante(request, token)

    if part.get("status") != "liberado":
        return render(
            request,
            "aguardando.html",
            participante=part,
            msg=request.query_params.get("msg"),
            erro=request.query_params.get("erro"),
            **_taxa_ctx(),
        )

    gate = _gate_credenciais(part)
    if gate:
        return gate

    palpites = db.palpites_do_participante(part["id"])
    fase_atual = db.get_fase_atual()
    fase_idx = FASE_IDS.index(fase_atual) if fase_atual in FASE_IDS else 0
    fases_ui = [
        {
            **f,
            "unlocked": FASE_IDS.index(f["id"]) <= fase_idx,
            "ativa": f["id"] == fase_atual,
        }
        for f in FASES
    ]
    return render(
        request,
        "palpites.html",
        participante=part,
        janela=db.get_janela(),
        fase_atual=fase_atual,
        fases=fases_ui,
        confrontos=_enrich_confrontos(db.list_confrontos_completos(fase_atual)),
        palpites_jogo=palpites["jogos"],
        palpites_pen=palpites["penaltis"],
        msg=request.query_params.get("msg"),
        erro=request.query_params.get("erro"),
    )


@app.get("/p/{token}/credenciais", response_class=HTMLResponse)
def credenciais_get(request: Request, token: str):
    part = db.get_participante_por_token(token)
    if not part:
        raise HTTPException(404, "Link inválido")
    _remember_participante(request, token)

    if part.get("status") != "liberado":
        return RedirectResponse(f"/p/{token}", status_code=303)
    if not db.precisa_credenciais(part):
        return RedirectResponse(f"/p/{token}", status_code=303)

    return render(
        request,
        "credenciais_setup.html",
        participante=part,
        erro=request.query_params.get("erro"),
        form_usuario=request.query_params.get("usuario") or "",
        **_taxa_ctx(),
    )


@app.post("/p/{token}/credenciais")
async def credenciais_post(
    request: Request,
    token: str,
    usuario: str = Form(""),
    senha: str = Form(""),
    senha2: str = Form(""),
):
    part = db.get_participante_por_token(token)
    if not part:
        raise HTTPException(404, "Link inválido")
    _remember_participante(request, token)

    if part.get("status") != "liberado":
        return RedirectResponse(f"/p/{token}", status_code=303)
    if not db.precisa_credenciais(part):
        return RedirectResponse(f"/p/{token}", status_code=303)

    usuario = (usuario or "").strip()
    senha = senha or ""
    senha2 = senha2 or ""
    ip = _client_ip(request)
    rate_key = f"cred:{ip}:{part['id']}"

    def _erro(msg: str) -> RedirectResponse:
        return RedirectResponse(
            f"/p/{token}/credenciais?erro={quote(msg)}&usuario={quote(usuario)}",
            status_code=303,
        )

    if not _auth_rate_ok(rate_key):
        return _erro("Muitas tentativas. Aguarde alguns minutos.")

    if not usuario or not senha or not senha2:
        _auth_rate_hit(rate_key)
        return _erro("Preencha usuário, senha e confirmação.")
    if senha != senha2:
        _auth_rate_hit(rate_key)
        return _erro("As senhas não conferem.")

    try:
        db.definir_credenciais(part["id"], usuario, senha)
    except ValueError as exc:
        _auth_rate_hit(rate_key)
        return _erro(str(exc))

    return RedirectResponse(
        f"/p/{token}?msg={quote('Username e senha criados. Guarde bem!')}",
        status_code=303,
    )


def _redirect_conta_drawer(token: str, *, msg: str | None = None, erro: str | None = None) -> RedirectResponse:
    """Após salvar conta, reabre o drawer Minha conta sobre a área do participante."""
    parts = ["conta=1"]
    if msg:
        parts.append(f"msg={quote(msg)}")
    if erro:
        parts.append(f"erro={quote(erro)}")
    return RedirectResponse(f"/p/{token}?{'&'.join(parts)}", status_code=303)


@app.get("/p/{token}/conta", response_class=HTMLResponse)
def conta_participante(request: Request, token: str):
    part = db.get_participante_por_token(token)
    if not part:
        raise HTTPException(404, "Link inválido")
    _remember_participante(request, token)
    gate = _gate_credenciais(part)
    if gate:
        return gate
    # Preferência: drawer (mesmo padrão do Entrar / LOGUIN)
    if request.query_params.get("page") != "1":
        msg = request.query_params.get("msg")
        erro = request.query_params.get("erro")
        return _redirect_conta_drawer(token, msg=msg, erro=erro)
    return render(
        request,
        "conta.html",
        participante=part,
        msg=request.query_params.get("msg"),
        erro=request.query_params.get("erro"),
    )


@app.post("/p/{token}/conta")
async def conta_salvar(
    request: Request,
    token: str,
    nome: str = Form(...),
    avatar: UploadFile = File(None),
):
    part = db.get_participante_por_token(token)
    if not part:
        raise HTTPException(404, "Link inválido")
    _remember_participante(request, token)
    gate = _gate_credenciais(part)
    if gate:
        return gate

    try:
        db.atualizar_nome_participante(part["id"], nome)
    except Exception as exc:
        return _redirect_conta_drawer(token, erro=str(exc))

    # Se for o participante do admin logado, atualiza o nick da sessão
    if (
        admin_ok(request)
        and (part.get("admin_login") or "").strip().lower()
        == (request.session.get("admin_login") or "").strip().lower()
    ):
        request.session["admin_nome"] = nome.strip()

    if avatar is not None and getattr(avatar, "filename", None):
        ext = Path(avatar.filename or "").suffix.lower()
        if ext not in AVATAR_EXTS:
            return _redirect_conta_drawer(token, erro="Foto deve ser jpg/png/webp")
        data = await avatar.read()
        if not data or len(data) > AVATAR_MAX_BYTES:
            return _redirect_conta_drawer(token, erro="Foto invalida ou maior que 3MB")
        if part.get("avatar_path"):
            old = AVATARES_DIR / part["avatar_path"]
            if old.is_file():
                old.unlink(missing_ok=True)
        rel = f"{part['id']}_{int(time.time())}{ext}"
        (AVATARES_DIR / rel).write_bytes(data)
        db.salvar_avatar(part["id"], rel)

    return _redirect_conta_drawer(token, msg="Dados atualizados")


@app.post("/p/{token}/conta/senha")
async def conta_alterar_senha(
    request: Request,
    token: str,
    senha_atual: str = Form(""),
    senha_nova: str = Form(""),
    senha_nova2: str = Form(""),
):
    part = db.get_participante_por_token(token)
    if not part:
        raise HTTPException(404, "Link inválido")
    _remember_participante(request, token)
    gate = _gate_credenciais(part)
    if gate:
        return gate

    ip = _client_ip(request)
    rate_key = f"senha:{ip}:{part['id']}"

    def _erro(msg: str) -> RedirectResponse:
        return _redirect_conta_drawer(token, erro=msg)

    if not _auth_rate_ok(rate_key):
        return _erro("Muitas tentativas. Aguarde alguns minutos.")

    if not senha_atual or not senha_nova or not senha_nova2:
        _auth_rate_hit(rate_key)
        return _erro("Preencha todos os campos de senha.")
    if senha_nova != senha_nova2:
        _auth_rate_hit(rate_key)
        return _erro("A confirmação da nova senha não confere.")

    try:
        db.alterar_senha(part["id"], senha_atual, senha_nova)
    except ValueError as exc:
        _auth_rate_hit(rate_key)
        return _erro(str(exc))

    return _redirect_conta_drawer(token, msg="Senha atualizada")


@app.post("/conta/sair")
def conta_sair(request: Request):
    request.session.pop("participante_token", None)
    request.session.pop("admin_login", None)
    request.session.pop("admin_nome", None)
    request.session.pop("admin_role", None)
    request.session.pop("admin", None)
    request.session.pop("admin_opt_out", None)
    return _redirect_acesso("entrar")


@app.post("/p/{token}/comprovante")
async def reenviar_comprovante(
    request: Request,
    token: str,
    comprovante: UploadFile = File(...),
):
    part = db.get_participante_por_token(token)
    if not part:
        raise HTTPException(404, "Link inválido")
    if part.get("status") == "liberado":
        return RedirectResponse(f"/p/{token}", status_code=303)

    filename = comprovante.filename or ""
    ext = Path(filename).suffix.lower()
    if ext not in COMPROVANTE_EXTS:
        return RedirectResponse(
            f"/p/{token}?erro=Envie+jpg,+png,+webp+ou+pdf",
            status_code=303,
        )
    data = await comprovante.read()
    if not data or len(data) > COMPROVANTE_MAX_BYTES:
        return RedirectResponse(f"/p/{token}?erro=Arquivo+invalido", status_code=303)

    if part.get("comprovante_path"):
        old = COMPROVANTES_DIR / part["comprovante_path"]
        if old.is_file():
            old.unlink(missing_ok=True)

    safe = re.sub(r"[^a-zA-Z0-9_-]+", "", part["nome"])[:40] or "user"
    rel = f"{part['id']}_{int(time.time())}_{safe}{ext}"
    (COMPROVANTES_DIR / rel).write_bytes(data)
    db.salvar_comprovante(part["id"], rel)
    return RedirectResponse(
        f"/p/{token}?msg=Comprovante+atualizado",
        status_code=303,
    )


@app.post("/p/{token}/salvar")
async def salvar_palpites(request: Request, token: str):
    part = db.get_participante_por_token(token)
    if not part:
        raise HTTPException(404, "Link inválido")
    if part.get("status") != "liberado":
        return RedirectResponse(f"/p/{token}?erro=Inscricao+nao+liberada", status_code=303)
    gate = _gate_credenciais(part)
    if gate:
        return gate

    janela = db.get_janela()
    if janela == "fechado":
        return RedirectResponse(f"/p/{token}?erro=Janela+fechada", status_code=303)

    form = await request.form()
    confrontos = db.list_confrontos_completos()

    try:
        for c in confrontos:
            ida = next(j for j in c["jogos"] if j["perna"] == "ida")
            volta = next(j for j in c["jogos"] if j["perna"] == "volta")

            if janela == "ida":
                gm = form.get(f"ida_{c['id']}_m")
                gv = form.get(f"ida_{c['id']}_v")
                if gm is None or gv is None or str(gm) == "" or str(gv) == "":
                    continue
                db.salvar_palpite_jogo(part["id"], ida["id"], int(gm), int(gv))

            elif janela == "volta":
                gm = form.get(f"volta_{c['id']}_m")
                gv = form.get(f"volta_{c['id']}_v")
                if gm is None or gv is None or str(gm) == "" or str(gv) == "":
                    continue
                db.salvar_palpite_jogo(part["id"], volta["id"], int(gm), int(gv))

                palpites = db.palpites_do_participante(part["id"])
                pj_ida = palpites["jogos"].get(ida["id"])
                if not pj_ida:
                    continue
                empate = agregado_empatado(
                    pj_ida["gols_mandante"],
                    pj_ida["gols_visitante"],
                    int(gm),
                    int(gv),
                )
                pen = form.get(f"pen_{c['id']}")
                if empate:
                    if pen not in ("a", "b"):
                        return RedirectResponse(
                            f"/p/{token}?erro=Escolha+os+penaltis+no+confronto+{c['id']}",
                            status_code=303,
                        )
                    db.salvar_palpite_penaltis(part["id"], c["id"], str(pen))
                else:
                    db.limpar_palpite_penaltis(part["id"], c["id"])
    except ValueError:
        return RedirectResponse(f"/p/{token}?erro=Placar+invalido", status_code=303)

    return RedirectResponse(f"/p/{token}?msg=Palpites+salvos", status_code=303)


@app.get("/admin/login", response_class=HTMLResponse)
def admin_login_page(request: Request):
    """Login do painel é o mesmo Entrar da home — sem formulário separado."""
    if admin_ok(request):
        return RedirectResponse("/admin", status_code=303)
    return _redirect_acesso("entrar", erro=request.query_params.get("erro"))


@app.post("/admin/login")
def admin_login(
    request: Request,
    login: str = Form(...),
    password: str = Form(...),
):
    """Compat: POST antigo do painel. Preferir /entrar."""
    admin = autenticar_admin(login, password)
    if not admin:
        return _redirect_acesso(
            "entrar",
            erro="Usuario ou senha incorretos",
            usuario=login,
        )
    _estabelecer_sessao_admin(request, admin)
    return _set_cookie_ui_admin(RedirectResponse("/admin", status_code=303))


@app.get("/admin/logout")
@app.post("/admin/logout")
def admin_logout(request: Request):
    """Sai de tudo (painel + bolão) — um Sair, um próximo Entrar."""
    request.session.pop("admin_login", None)
    request.session.pop("admin_nome", None)
    request.session.pop("admin_role", None)
    request.session.pop("admin", None)
    request.session.pop("admin_opt_out", None)
    request.session.pop("participante_token", None)
    request.session.pop("loguin_marlon", None)
    return _redirect_acesso("entrar")


@app.get("/admin", response_class=HTMLResponse)
def admin_home(request: Request):
    if not admin_ok(request):
        return _redirect_acesso("entrar")
    # Só garante o admin da sessão atual. Os outros nascem no próprio login —
    # senão apagar "João JEC" / "Mazeta" recria na hora.
    token_atual = request.session.get("participante_token")
    login_atual = (request.session.get("admin_login") or "").strip().lower()
    if login_atual:
        try:
            admin_atual = next(
                (a for a in list_admins() if a.login == login_atual), None
            )
            nome_cfg = admin_atual.nome if admin_atual else admin_nome(request)
            if admin_atual:
                request.session["admin_role"] = admin_atual.papel
            part = db.garantir_participante_admin(
                login_atual, nome_cfg, token_preferido=token_atual
            )
            _remember_participante(request, part["token"])
            request.session["admin_nome"] = part.get("nome") or nome_cfg
        except Exception:
            pass
    base = PUBLIC_BASE_URL or str(request.base_url).rstrip("/")
    fase_atual = db.get_fase_atual()
    fase_idx = FASE_IDS.index(fase_atual) if fase_atual in FASE_IDS else 0
    fases_ui = [
        {
            **f,
            "unlocked": FASE_IDS.index(f["id"]) <= fase_idx,
            "ativa": f["id"] == fase_atual,
        }
        for f in FASES
    ]
    confrontos_por_fase = {
        f["id"]: _enrich_confrontos(db.list_confrontos_completos(f["id"]))
        for f in FASES
    }
    return render(
        request,
        "admin.html",
        janela=db.get_janela(),
        janelas=JANELAS,
        fase_atual=fase_atual,
        fases=fases_ui,
        confrontos_por_fase=confrontos_por_fase,
        participantes=db.list_participantes(),
        recuperacao_pedidos=db.list_pedidos_recuperacao_pendentes(),
        ultima_rodada=db.get_ultima_rodada_historico(),
        msg=request.query_params.get("msg"),
        erro=request.query_params.get("erro"),
        base_url=base,
        inscricao_url=f"{base}/inscricao",
        public_url_configurada=bool(PUBLIC_BASE_URL),
        **_taxa_ctx(),
    )


@app.get("/admin/credenciais", response_class=HTMLResponse)
def admin_credenciais(request: Request):
    negado = require_dono(request)
    if negado:
        return negado
    partes = [
        p
        for p in db.list_participantes()
        if p.get("status") == "liberado"
    ]
    return render(
        request,
        "admin_credenciais.html",
        participantes=partes,
        msg=request.query_params.get("msg"),
        erro=request.query_params.get("erro"),
        **_taxa_ctx(),
    )


@app.post("/admin/credenciais/redefinir")
def admin_credenciais_redefinir(
    request: Request,
    participante_id: int = Form(...),
    username: str = Form(""),
    senha_nova: str = Form(...),
):
    negado = require_dono(request)
    if negado:
        return negado
    try:
        updated = db.admin_redefinir_credenciais(
            participante_id,
            senha_nova=senha_nova,
            username=username.strip() or None,
        )
    except ValueError as e:
        return RedirectResponse(
            f"/admin/credenciais?erro={quote(str(e))}",
            status_code=303,
        )
    nome = updated.get("nome") or "participante"
    user = updated.get("username") or "(sem username)"
    return RedirectResponse(
        f"/admin/credenciais?msg={quote(f'Credenciais de {nome} ({user}) redefinidas. Passe a senha nova no Zap.')}",
        status_code=303,
    )


@app.get("/admin/comprovantes/{participante_id}")
def admin_comprovante(request: Request, participante_id: int):
    if not admin_ok(request):
        return _redirect_acesso("entrar")
    part = db.get_participante(participante_id)
    if not part or not part.get("comprovante_path"):
        raise HTTPException(404, "Comprovante não encontrado")
    path = COMPROVANTES_DIR / part["comprovante_path"]
    if not path.is_file():
        raise HTTPException(404, "Arquivo ausente")
    return FileResponse(path)


def _limpar_arquivos_participante(part: dict) -> None:
    for key, folder in (
        ("comprovante_path", COMPROVANTES_DIR),
        ("avatar_path", AVATARES_DIR),
    ):
        rel = part.get(key)
        if rel:
            path = folder / rel
            if path.is_file():
                path.unlink(missing_ok=True)


@app.post("/admin/liberar")
def admin_liberar(request: Request, participante_id: int = Form(...)):
    if not admin_ok(request):
        return _redirect_acesso("entrar")
    db.liberar_participante(participante_id)
    return RedirectResponse(
        "/admin?sec=inscricoes&msg=Inscricao+liberada", status_code=303
    )


@app.get("/admin/avisar-link/{participante_id}")
def admin_avisar_link(request: Request, participante_id: int):
    """Marca link como enviado e abre o WhatsApp com a mensagem pronta."""
    from urllib.parse import quote

    if not admin_ok(request):
        return _redirect_acesso("entrar")
    part = db.get_participante(participante_id)
    if not part or part.get("status") != "liberado":
        return RedirectResponse(
            "/admin?sec=inscricoes&erro=Participante+nao+liberado", status_code=303
        )
    wa = db.celular_whatsapp(part.get("celular"))
    if not wa:
        return RedirectResponse(
            "/admin?sec=inscricoes&erro=Participante+sem+celular", status_code=303
        )
    base = PUBLIC_BASE_URL or str(request.base_url).rstrip("/")
    msg = db.mensagem_whatsapp_link(part["nome"], base, part["token"])
    db.marcar_link_enviado(participante_id, enviado=True)
    db.marcar_pedidos_recuperacao_atendidos_participante(participante_id)
    return RedirectResponse(
        f"https://wa.me/{wa}?text={quote(msg)}", status_code=303
    )


@app.get("/admin/recuperacao/{pedido_id}/atender")
def admin_recuperacao_atender(request: Request, pedido_id: int):
    """Fecha o pedido de recuperação e abre o WhatsApp com o link."""
    from urllib.parse import quote

    if not admin_ok(request):
        return _redirect_acesso("entrar")
    pedido = db.get_pedido_recuperacao(pedido_id)
    if not pedido:
        return RedirectResponse(
            "/admin?sec=inscricoes&erro=Pedido+nao+encontrado", status_code=303
        )
    if pedido.get("status") != "liberado":
        return RedirectResponse(
            "/admin?sec=inscricoes&erro=Participante+nao+liberado", status_code=303
        )
    wa = db.celular_whatsapp(pedido.get("celular"))
    if not wa:
        return RedirectResponse(
            "/admin?sec=inscricoes&erro=Participante+sem+celular", status_code=303
        )
    base = PUBLIC_BASE_URL or str(request.base_url).rstrip("/")
    msg = db.mensagem_whatsapp_link(pedido["nome"], base, pedido["token"])
    db.marcar_pedido_recuperacao_atendido(pedido_id)
    db.marcar_pedidos_recuperacao_atendidos_participante(pedido["participante_id"])
    db.marcar_link_enviado(pedido["participante_id"], enviado=True)
    return RedirectResponse(
        f"https://wa.me/{wa}?text={quote(msg)}", status_code=303
    )


@app.get("/admin/marcar-link/{participante_id}")
def admin_marcar_link(
    request: Request,
    participante_id: int,
    enviado: int = 1,
):
    """Marca/desmarca link enviado e volta ao painel (GET — evita 404 de POST antigo)."""
    if not admin_ok(request):
        return _redirect_acesso("entrar")
    part = db.get_participante(participante_id)
    if not part or part.get("status") != "liberado":
        return RedirectResponse(
            "/admin?sec=inscricoes&erro=Participante+nao+liberado", status_code=303
        )
    db.marcar_link_enviado(participante_id, enviado=bool(enviado))
    msg = "Link+marcado+como+enviado" if enviado else "Link+marcado+como+pendente"
    return RedirectResponse(f"/admin?sec=inscricoes&msg={msg}", status_code=303)


@app.post("/admin/link-enviado")
def admin_link_enviado(
    request: Request,
    participante_id: int = Form(...),
    enviado: str = Form("1"),
):
    if not admin_ok(request):
        return _redirect_acesso("entrar")
    part = db.get_participante(participante_id)
    if not part or part.get("status") != "liberado":
        return RedirectResponse(
            "/admin?sec=inscricoes&erro=Participante+nao+liberado", status_code=303
        )
    db.marcar_link_enviado(participante_id, enviado=enviado == "1")
    msg = "Link+marcado+como+enviado" if enviado == "1" else "Link+marcado+como+pendente"
    return RedirectResponse(f"/admin?sec=inscricoes&msg={msg}", status_code=303)


@app.post("/admin/apagar")
def admin_apagar(request: Request, participante_id: int = Form(...)):
    negado = require_dono(request)
    if negado:
        return negado
    part = db.get_participante(participante_id)
    if not part:
        return RedirectResponse(
            "/admin?sec=inscricoes&erro=Participante+nao+encontrado", status_code=303
        )
    # Não deixa o admin apagar a própria conta da sessão (quebraria o painel)
    login_atual = (request.session.get("admin_login") or "").strip().lower()
    part_login = (part.get("admin_login") or "").strip().lower()
    if part_login and login_atual and part_login == login_atual:
        return RedirectResponse(
            "/admin?sec=inscricoes&erro=Nao+da+para+apagar+o+admin+logado",
            status_code=303,
        )
    apagado = db.apagar_participante(participante_id)
    if not apagado:
        return RedirectResponse(
            "/admin?sec=inscricoes&erro=Participante+nao+encontrado", status_code=303
        )
    _limpar_arquivos_participante(apagado)
    msg = "Inscricao+apagada"
    if part_login:
        msg = "Admin+removido+do+bolao.+So+volta+se+ele+entrar+de+novo+no+admin"
    return RedirectResponse(f"/admin?sec=inscricoes&msg={msg}", status_code=303)


@app.post("/admin/recusar")
def admin_recusar(request: Request, participante_id: int = Form(...)):
    """Recusar = marca como recusada (não apaga; use o × para excluir)."""
    if not admin_ok(request):
        return _redirect_acesso("entrar")
    if not db.recusar_participante(participante_id):
        return RedirectResponse(
            "/admin?sec=inscricoes&erro=Nao+foi+possivel+recusar", status_code=303
        )
    return RedirectResponse(
        "/admin?sec=inscricoes&msg=Inscricao+recusada", status_code=303
    )


@app.post("/admin/reabrir")
def admin_reabrir(request: Request, participante_id: int = Form(...)):
    if not admin_ok(request):
        return _redirect_acesso("entrar")
    if not db.reabrir_participante(participante_id):
        return RedirectResponse(
            "/admin?sec=inscricoes&erro=Nao+foi+possivel+reabrir", status_code=303
        )
    return RedirectResponse(
        "/admin?sec=inscricoes&msg=Inscricao+reaberta", status_code=303
    )


@app.post("/admin/recusar-todos")
def admin_recusar_todos(request: Request):
    negado = require_dono(request)
    if negado:
        return negado
    n = db.recusar_todos_pendentes()
    return RedirectResponse(
        f"/admin?sec=inscricoes&msg={n}+inscricao(oes)+recusada(s)",
        status_code=303,
    )


@app.post("/admin/janela")
def admin_janela(request: Request, janela: str = Form(...)):
    if not admin_ok(request):
        return _redirect_acesso("entrar")
    try:
        db.set_janela(janela)
    except ValueError:
        return RedirectResponse("/admin?erro=Janela+invalida", status_code=303)
    return RedirectResponse(f"/admin?msg=Janela+{janela}", status_code=303)


@app.post("/admin/fase")
def admin_fase(request: Request, fase: str = Form(...)):
    if not admin_ok(request):
        return _redirect_acesso("entrar")
    try:
        db.set_fase_atual(fase)
    except ValueError:
        return RedirectResponse("/admin?erro=Fase+invalida", status_code=303)
    return RedirectResponse(f"/admin?msg=Fase+{fase}", status_code=303)


@app.post("/admin/participante")
def admin_participante(
    request: Request,
    nome: str = Form(...),
    celular: str = Form(""),
    ja_pago: str = Form(""),
):
    if not admin_ok(request):
        return _redirect_acesso("entrar")
    status = "liberado" if ja_pago == "1" else "pendente"
    celular_ok = None
    if celular.strip():
        try:
            celular_ok = db.normalizar_celular(celular)
        except ValueError:
            return RedirectResponse(
                "/admin?sec=inscricoes&erro=Celular+invalido",
                status_code=303,
            )
    try:
        db.criar_participante(nome, status=status, celular=celular_ok)
    except Exception as exc:
        return RedirectResponse(
            f"/admin?sec=inscricoes&erro={exc}", status_code=303
        )
    return RedirectResponse(
        "/admin?sec=inscricoes&msg=Participante+criado", status_code=303
    )


@app.post("/admin/avatar-padrao")
async def admin_avatar_padrao(
    request: Request,
    avatar: UploadFile = File(...),
):
    if not admin_ok(request):
        return _redirect_acesso("entrar")
    ext = Path(avatar.filename or "").suffix.lower()
    if ext not in AVATAR_EXTS:
        return RedirectResponse(
            "/admin?sec=inscricoes&erro=Foto+padrao+deve+ser+jpg/png/webp",
            status_code=303,
        )
    data = await avatar.read()
    if not data or len(data) > AVATAR_MAX_BYTES:
        return RedirectResponse(
            "/admin?sec=inscricoes&erro=Foto+padrao+invalida+ou+maior+que+3MB",
            status_code=303,
        )
    for old in STATIC.glob(f"{AVATAR_PADRAO_STEM}.*"):
        if old.is_file():
            old.unlink(missing_ok=True)
    dest = STATIC / f"{AVATAR_PADRAO_STEM}{ext}"
    dest.write_bytes(data)
    return RedirectResponse(
        "/admin?sec=inscricoes&msg=Foto+padrao+atualizada", status_code=303
    )


@app.post("/admin/participante/atualizar")
async def admin_atualizar_participante(
    request: Request,
    participante_id: int = Form(...),
    nome: str = Form(...),
    celular: str = Form(""),
    remover_avatar: str = Form(""),
    avatar: UploadFile = File(None),
):
    from urllib.parse import quote

    if not admin_ok(request):
        return _redirect_acesso("entrar")
    part = db.get_participante(participante_id)
    if not part:
        return RedirectResponse(
            "/admin?sec=inscricoes&erro=Participante+nao+encontrado",
            status_code=303,
        )
    try:
        db.atualizar_nome_participante(participante_id, nome)
        db.atualizar_celular_participante(participante_id, celular)
    except ValueError as exc:
        return RedirectResponse(
            f"/admin?sec=inscricoes&erro={quote(str(exc))}", status_code=303
        )
    except Exception as exc:
        return RedirectResponse(
            f"/admin?sec=inscricoes&erro={quote(str(exc))}", status_code=303
        )

    if (
        (part.get("admin_login") or "").strip().lower()
        == (request.session.get("admin_login") or "").strip().lower()
    ):
        request.session["admin_nome"] = nome.strip()

    if remover_avatar == "1" and part.get("avatar_path"):
        old = AVATARES_DIR / part["avatar_path"]
        if old.is_file():
            old.unlink(missing_ok=True)
        db.salvar_avatar(participante_id, None)
        part["avatar_path"] = None

    if avatar is not None and getattr(avatar, "filename", None):
        ext = Path(avatar.filename or "").suffix.lower()
        if ext not in AVATAR_EXTS:
            return RedirectResponse(
                "/admin?sec=inscricoes&erro=Foto+deve+ser+jpg/png/webp",
                status_code=303,
            )
        data = await avatar.read()
        if not data or len(data) > AVATAR_MAX_BYTES:
            return RedirectResponse(
                "/admin?sec=inscricoes&erro=Foto+invalida+ou+maior+que+3MB",
                status_code=303,
            )
        if part.get("avatar_path"):
            old = AVATARES_DIR / part["avatar_path"]
            if old.is_file():
                old.unlink(missing_ok=True)
        rel = f"{participante_id}_{int(time.time())}{ext}"
        (AVATARES_DIR / rel).write_bytes(data)
        db.salvar_avatar(participante_id, rel)

    return RedirectResponse(
        "/admin?sec=inscricoes&msg=Participante+atualizado", status_code=303
    )


@app.post("/admin/resultado")
def admin_resultado(
    request: Request,
    jogo_id: int = Form(...),
    gols_mandante: int = Form(...),
    gols_visitante: int = Form(...),
    penaltis_clube_id: str = Form(""),
):
    if not admin_ok(request):
        return _redirect_acesso("entrar")
    pen = penaltis_clube_id if penaltis_clube_id in ("a", "b") else None
    db.set_resultado_jogo(jogo_id, gols_mandante, gols_visitante, pen)
    return RedirectResponse("/admin?msg=Resultado+salvo", status_code=303)


@app.post("/admin/resultados")
async def admin_resultados(request: Request):
    if not admin_ok(request):
        return _redirect_acesso("entrar")
    form = await request.form()
    fase = str(form.get("fase") or db.get_fase_atual())
    if fase not in FASE_IDS:
        return RedirectResponse("/admin?erro=Fase+invalida", status_code=303)
    confrontos = db.list_confrontos_completos(fase)
    salvos = 0
    try:
        for c in confrontos:
            for jogo in c.get("jogos") or []:
                jid = jogo["id"]
                gm = form.get(f"jogo_{jid}_m")
                gv = form.get(f"jogo_{jid}_v")
                if gm is None or gv is None or str(gm) == "" or str(gv) == "":
                    continue
                pen_raw = form.get(f"jogo_{jid}_pen") or ""
                pen = pen_raw if pen_raw in ("a", "b") else None
                db.set_resultado_jogo(jid, int(gm), int(gv), pen)
                salvos += 1
    except ValueError:
        return RedirectResponse("/admin?erro=Placar+invalido", status_code=303)
    if salvos == 0:
        return RedirectResponse("/admin?erro=Nenhum+resultado+para+salvar", status_code=303)
    return RedirectResponse(f"/admin?msg={salvos}+resultado(s)+salvo(s)", status_code=303)


@app.post("/admin/confirmar-rodada")
def admin_confirmar_rodada(request: Request):
    if not admin_ok(request):
        return _redirect_acesso("entrar")
    hist = confirmar_rodada()
    return RedirectResponse(
        f"/admin?msg=Rodada+{hist['numero']}+confirmada+e+arquivada",
        status_code=303,
    )


@app.post("/admin/desfazer-rodada")
def admin_desfazer_rodada(request: Request):
    if not admin_ok(request):
        return _redirect_acesso("entrar")
    try:
        hist = desfazer_ultima_rodada()
    except ValueError as e:
        return RedirectResponse(
            f"/admin?erro={str(e).replace(' ', '+')}",
            status_code=303,
        )
    return RedirectResponse(
        f"/admin?msg={hist['rotulo'].replace(' ', '+')}+desfeita.+Classificacao+ao+vivo+restaurada",
        status_code=303,
    )


@app.post("/admin/zerar-resultados")
def admin_zerar_resultados(
    request: Request,
    fase: str = Form(...),
    perna: str = Form(...),
):
    if not admin_ok(request):
        return _redirect_acesso("entrar")
    if fase not in FASE_IDS:
        return RedirectResponse("/admin?erro=Fase+invalida", status_code=303)
    if perna not in ("ida", "volta"):
        return RedirectResponse("/admin?erro=Perna+invalida", status_code=303)
    try:
        n = db.limpar_resultados_oficiais(fase=fase, perna=perna)
    except ValueError:
        return RedirectResponse("/admin?erro=Nao+foi+possivel+zerar", status_code=303)
    label = "Ida" if perna == "ida" else "Volta"
    return RedirectResponse(
        f"/admin?msg={n}+placar(es)+zerado(s)+em+{fase}+({label})",
        status_code=303,
    )
