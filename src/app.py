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
    JSONResponse,
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
    BANDEIRAS_UF_DIR,
    CLUBES_DIR,
    COMPROVANTE_EXTS,
    COMPROVANTE_MAX_BYTES,
    COMPROVANTES_DIR,
    EMBLEMAS_DIR,
    EMBLEMAS_FM_DIR,
    FASES,
    FASE_IDS,
    ADSENSE_CLIENT,
    INSCRICAO_FECHA_EM,
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
    TRAVA_PALPITE_ANTES_MIN,
    WHATSAPP_GROUP_URL,
    fase_anterior,
    inscricao_aberta,
)
from src.estilo_palpites import trofeus_hall
from src.ranking import (
    calcular_classificacao,
    confirmar_rodada,
    desfazer_ultima_rodada,
    faixa_zonas,
    resumo_pontuacao_por_participante,
)
from src.scoring import agregado_empatado
from src.seed_data import emblema_url, formatar_inicio_jogo, inicio_em_input_value, nome_clube_curto
from src.transparencia import metricas_gerais, montar_portal, ranking_apostadores

load_dotenv(ROOT_DIR / ".env")

app = FastAPI(title="Bolão THDFM — Copa do Brasil")


def _path_publico(path: str) -> bool:
    """Rotas acessíveis sem sessão (home + login + assets + link mágico)."""
    if path in ("/", "/home", "/favicon.ico", "/ads.txt"):
        return True
    if path.startswith("/static/") or path.startswith("/emblemas/") or path.startswith("/emblemas-fm/") or path.startswith("/avatars/") or path.startswith("/bandeiras-uf/"):
        return True
    # Perfil (handler ainda exige liberado/admin)
    if path.startswith("/meu-perfil") or path.startswith("/perfil/") or path.startswith("/prototipo/"):
        return True
    # Link mágico do participante
    if path.startswith("/p/"):
        return True
    # Auth / logout
    if path in (
        "/entrar",
        "/login",
        "/loguin",
        "/admin/login",
        "/admin/logout",
        "/conta/sair",
    ):
        return True
    # Inscrição: página só mostra “encerrada”; POST também precisa chegar no handler
    if path == "/inscricao":
        return True
    return False


@app.middleware("http")
async def gate_login_middleware(request: Request, call_next):
    path = request.url.path
    if _path_publico(path):
        return await call_next(request)
    # Sessão de participante ou admin (SessionMiddleware roda por fora).
    if request.session.get("participante_token") or request.session.get("admin_login"):
        return await call_next(request)
    return RedirectResponse("/?acesso=entrar", status_code=303)


# Session por fora do gate (último add_middleware = mais externo).
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
BANDEIRAS_UF_DIR.mkdir(parents=True, exist_ok=True)
CLUBES_DIR.mkdir(parents=True, exist_ok=True)
EMBLEMAS_FM_DIR.mkdir(parents=True, exist_ok=True)
COMPROVANTES_DIR.mkdir(parents=True, exist_ok=True)
AVATARES_DIR.mkdir(parents=True, exist_ok=True)

app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")
app.mount("/emblemas", StaticFiles(directory=str(EMBLEMAS_DIR)), name="emblemas")
app.mount("/emblemas-fm", StaticFiles(directory=str(EMBLEMAS_FM_DIR)), name="emblemas_fm")
app.mount("/bandeiras-uf", StaticFiles(directory=str(BANDEIRAS_UF_DIR)), name="bandeiras_uf")
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
TEMPLATES.env.globals["inicio_em_input_value"] = inicio_em_input_value
TEMPLATES.env.globals["nome_clube_curto"] = nome_clube_curto
TEMPLATES.env.globals["wa_msg_link"] = db.mensagem_whatsapp_link
TEMPLATES.env.globals["url_whatsapp_chat"] = db.url_whatsapp_chat
TEMPLATES.env.globals["avatar_url"] = avatar_url
TEMPLATES.env.globals["avatar_padrao_url"] = avatar_padrao_url
TEMPLATES.env.globals["listra_emoji_efetivo"] = db.listra_emoji_efetivo
TEMPLATES.env.globals["listra_texto_contexto"] = db.listra_texto_contexto
TEMPLATES.env.globals["listra_linha_compartilhar"] = db.listra_linha_compartilhar
TEMPLATES.env.globals["ADSENSE_CLIENT"] = ADSENSE_CLIENT
TEMPLATES.env.filters["celular_fmt"] = db.formatar_celular
TEMPLATES.env.filters["celular_wa"] = db.celular_whatsapp
TEMPLATES.env.filters["wa_chat"] = db.url_whatsapp_chat


def _listra_marcar_destaque(texto: str, destaque: str) -> str:
    """Marca o trecho compartilhável dentro do texto (HTML escapado)."""
    from markupsafe import Markup

    return Markup(db.listra_marcar_destaque_html(texto, destaque))


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
    if is_adm and "admin_cobranca_count" not in ctx:
        try:
            fase_meta = db.get_fase_atual()
            janela_meta = db.get_janela()
            perna_meta = "volta" if janela_meta == "volta" else "ida"
            st = db.status_palpites_liberados(
                fase_meta, perna_meta, so_abertos=True, janela=janela_meta
            )
            ctx["admin_cobranca_count"] = int(st.get("n_incompletos") or 0)
        except Exception:
            ctx["admin_cobranca_count"] = 0
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


def _enrich_confrontos(confrontos: list, *, janela: str | None = None) -> list:
    from src.seed_data import jogo_palpite_travado

    j = janela if janela is not None else db.get_janela()
    for c in confrontos:
        c["ida"] = next((jogo for jogo in c["jogos"] if jogo["perna"] == "ida"), None)
        c["volta"] = next((jogo for jogo in c["jogos"] if jogo["perna"] == "volta"), None)
        if c["ida"] is not None:
            c["ida"]["travado"] = jogo_palpite_travado(c["ida"].get("inicio_em"), janela=j)
            c["ida"]["confirmado"] = db.jogo_confirmado(c["ida"])
        if c["volta"] is not None:
            c["volta"]["travado"] = jogo_palpite_travado(c["volta"].get("inicio_em"), janela=j)
            c["volta"]["confirmado"] = db.jogo_confirmado(c["volta"])
    return confrontos


def _perna_default_confrontos(confrontos: list) -> str:
    """Volta se todos os jogos de ida da fase já têm placar oficial."""
    idas = [c.get("ida") for c in confrontos if c.get("ida")]
    if not idas:
        return "ida"
    if all(
        j.get("gols_mandante") is not None and j.get("gols_visitante") is not None
        for j in idas
    ):
        return "volta"
    return "ida"


def _volta_liberada(janela: str | None = None) -> bool:
    """Volta liberada junto com a Ida — os confrontos da fase já são conhecidos.

    A janela ``fechado`` ainda trava edição nos formulários; a aba Volta
    permanece disponível para consulta.
    """
    j = janela if janela is not None else db.get_janela()
    return j in ("ida", "volta", "fechado")


def _admin_wants_json(request: Request) -> bool:
    accept = (request.headers.get("accept") or "").lower()
    return "application/json" in accept or request.query_params.get("format") == "json"


def _taxa_ctx() -> dict:
    wa_msg = os.environ.get("ADMIN_WHATSAPP_MSG", ADMIN_WHATSAPP_MSG)
    wa_url = db.url_whatsapp_chat(ADMIN_WHATSAPP or os.environ.get("ADMIN_WHATSAPP", ""), wa_msg) or ""
    social_wa_url = db.url_whatsapp_chat(SOCIAL_WHATSAPP or "") or ""
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


@app.get("/ads.txt", response_class=PlainTextResponse)
def ads_txt():
    """Autorização de vendedores para o Google AdSense."""
    if not ADSENSE_CLIENT:
        return PlainTextResponse("", status_code=404)
    pub = ADSENSE_CLIENT.removeprefix("ca-")
    # ID de certificação do Google AdSense (padrão ads.txt).
    body = f"google.com, {pub}, DIRECT, f08c47fec0942fa0\n"
    return PlainTextResponse(body, media_type="text/plain; charset=utf-8")


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
    return RedirectResponse("/bolao/meus-palpites", status_code=303)


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


def _karma_cats_demo() -> list[dict]:
    """Karma estilo Orkut (1–3 ícones). Textos para o usuário reescrever."""
    return [
        {
            "id": "confiavel",
            "nome": "Confiável",
            "icon": "😊",
            "labels": ["confiável", "muito confiável", "super confiável"],
            "demo": 2,
        },
        {
            "id": "legal",
            "nome": "Legal",
            "icon": "🧊",
            "labels": ["legal", "muito legal", "super legal"],
            "demo": 3,
        },
        {
            "id": "sexy",
            "nome": "Sexy",
            "icon": "❤️",
            "labels": ["sexy", "muito sexy", "super sexy"],
            "demo": 1,
        },
        {
            "id": "burro",
            "nome": "Burro",
            "icon": "🫏",
            "labels": ["burro", "muito burro", "super burro"],
            "demo": 1,
        },
    ]


def _amizade_niveis_demo() -> list[dict]:
    """Esquema de amizade do protótipo (textos para reescrever)."""
    return [
        {"id": "nao_conheco", "nome": "quem é vc", "icone": "·"},
        {"id": "conhecido", "nome": "conhecido", "icone": "○"},
        {"id": "amigo", "nome": "amigo", "icone": "◐"},
        {"id": "bom_amigo", "nome": "bom amigo", "icone": "●"},
        {"id": "melhor_amigo", "nome": "mais que amigos, irmães", "icone": "★"},
    ]


def _banner_presets_demo() -> list[dict]:
    """Banners/presets de fundo do perfil (protótipo)."""
    return [
        {"id": "padrao", "nome": "Padrão"},
        {"id": "laranja", "nome": "Laranja THDFM"},
        {"id": "gramado", "nome": "Gramado"},
        {"id": "noite", "nome": "Noite de jogo"},
        {"id": "carbono", "nome": "Carbono"},
        {"id": "ouro", "nome": "Final"},
    ]


def _prototipo_times_ctx() -> dict:
    import json

    from src.clubes_catalogo import carregar_clubes, contagem_por_uf

    ufs_meta_path = BANDEIRAS_UF_DIR / "ufs.json"
    ufs_meta = (
        json.loads(ufs_meta_path.read_text(encoding="utf-8"))
        if ufs_meta_path.is_file()
        else {"ufs": []}
    )
    por_uf = contagem_por_uf()
    ufs = []
    for u in ufs_meta.get("ufs", []):
        code = u.get("uf") or ""
        ufs.append(
            {
                **u,
                "n_clubes": por_uf.get(code, 0),
                "bandeira": f"/bandeiras-uf/{u.get('arquivo') or (code + '.svg')}",
            }
        )
    clubes = [c for c in carregar_clubes() if c.get("tem_emblema")]
    return {
        "ufs": ufs,
        "clubes_json": json.dumps(clubes, ensure_ascii=False),
        "n_clubes": len(clubes),
        "karma_cats": _karma_cats_demo(),
        "amizade_niveis": _amizade_niveis_demo(),
        "banner_presets": _banner_presets_demo(),
    }


def _require_perfil(request: Request) -> RedirectResponse | None:
    """Perfil: participante liberado na sessão (admin também, via vínculo no render)."""
    if admin_ok(request):
        return None
    token = request.session.get("participante_token")
    if not token:
        return RedirectResponse("/?acesso=entrar", status_code=303)
    part = db.get_participante_por_token(token)
    if not part:
        request.session.pop("participante_token", None)
        return RedirectResponse("/?acesso=entrar", status_code=303)
    if part.get("status") != "liberado":
        return RedirectResponse(f"/p/{part['token']}", status_code=303)
    return None


def _voter_sessao(request: Request) -> dict | None:
    """Participante da sessão (libera admin sem token via vínculo estável)."""
    part = _participante_sessao(request)
    if part:
        return part
    if not admin_ok(request):
        return None
    login = (request.session.get("admin_login") or "").strip().lower()
    if not login:
        return None
    try:
        part = db.garantir_participante_admin(login, admin_nome(request))
        _remember_participante(request, part["token"])
        return part
    except Exception:
        return None


def _perfil_publico_payload(part: dict, *, voter_id: int | None = None) -> dict:
    """Dados públicos de um participante para a página de perfil."""
    nome = (part.get("nome") or "").strip() or "Participante"
    iniciais = (nome[:2] if nome else "??").upper()
    karma = db.karma_resumo(part["id"], voter_id=voter_id)
    nutela = db.nutela_resumo(part["id"], voter_id=voter_id)
    return {
        "slug": str(part["id"]),
        "nome": nome,
        "participante_id": part["id"],
        "avatar_url": avatar_url(part.get("avatar_path")),
        "frase": "",
        "relacionamento": "",
        "aniversario": "",
        "times": [],
        "karma": karma["medias"],
        "karma_counts": karma["counts"],
        "karma_meu_voto": karma["meu_voto"],
        "nutela": nutela["media"],
        "nutela_count": nutela["count"],
        "nutela_meu_voto": nutela["meu_voto"],
        "iniciais": iniciais,
    }


_ZONA_LABEL_PERFIL = {
    "campeao": "Campeão",
    "podio": "Zona de cima",
    "meio": "Meio de tabela",
    "risco": "Zona de risco",
}


def _bolao_resumo_perfil(participante_id: int | None) -> dict | None:
    """Recorte seguro do bolão para o perfil público (posição, pts, estilo)."""
    if not participante_id:
        return None
    try:
        pid = int(participante_id)
    except (TypeError, ValueError):
        return None

    part = db.get_participante(pid)
    if not part:
        return None
    if part.get("status") != "liberado":
        return {
            "disponivel": False,
            "motivo": "pendente",
            "nome": part.get("nome") or "",
            "classificacao_url": "/classificacao",
        }

    try:
        linhas = calcular_classificacao()
    except Exception:
        return {
            "disponivel": False,
            "motivo": "erro",
            "nome": part.get("nome") or "",
            "classificacao_url": "/classificacao",
        }

    linha = next((r for r in linhas if int(r.get("participante_id") or 0) == pid), None)
    if not linha:
        return {
            "disponivel": False,
            "motivo": "fora",
            "nome": part.get("nome") or "",
            "classificacao_url": "/classificacao",
        }

    estilo = None
    try:
        from src.estilo_palpites import perfil_participante

        estilo = perfil_participante(pid)
    except Exception:
        estilo = None

    rodadas: list[dict] = []
    try:
        hist = resumo_pontuacao_por_participante(linhas).get(pid) or []
        for entrada in hist[-6:]:
            curto = (entrada.get("rotulo_curto") or "").strip()
            fase_full = (entrada.get("fase_label") or "").strip()
            janela = (entrada.get("janela_label") or "").strip()
            if curto and fase_full and janela:
                titulo = f"{curto} · {fase_full} ({janela})"
            elif curto and fase_full:
                titulo = f"{curto} · {fase_full}"
            else:
                titulo = (entrada.get("rotulo") or curto or "Rodada").strip()
            rodadas.append(
                {
                    "titulo": titulo,
                    "rotulo": entrada.get("rotulo") or titulo,
                    "pts": entrada.get("rod") or 0,
                    "soma": entrada.get("soma") or 0,
                    "posicao": entrada.get("posicao"),
                    "movimento": entrada.get("movimento"),
                    "ao_vivo": bool(entrada.get("ao_vivo")),
                    "jogos": entrada.get("jogos") or [],
                }
            )
    except Exception:
        rodadas = []

    badges = []
    if estilo and isinstance(estilo.get("badges"), list):
        badges = [
            {
                "id": b.get("id"),
                "titulo": b.get("titulo") or "",
                "explicacao": b.get("explicacao") or "",
            }
            for b in estilo["badges"][:4]
            if isinstance(b, dict) and b.get("titulo")
        ]

    assin_raw = (estilo or {}).get("placar_assinatura")
    assinatura = None
    if isinstance(assin_raw, dict) and assin_raw.get("placar"):
        n_assin = assin_raw.get("n") or 0
        assinatura = f"{assin_raw['placar']} ({n_assin}×)"
    elif isinstance(assin_raw, str) and assin_raw.strip():
        assinatura = assin_raw.strip()

    zona = linha.get("zona") or ""
    mov = linha.get("movimento")
    return {
        "disponivel": True,
        "participante_id": pid,
        "nome": linha.get("participante") or part.get("nome") or "",
        "username": (part.get("username") or "").strip() or None,
        "posicao": linha.get("posicao"),
        "total": len(linhas),
        "soma": linha.get("soma") or 0,
        "rod": linha.get("rod") or 0,
        "placar": linha.get("placar") or 0,
        "vencedor": linha.get("vencedor") or 0,
        "gols": linha.get("gols") or 0,
        "fidelidade": linha.get("fidelidade") or 0,
        "zona": zona,
        "zona_label": _ZONA_LABEL_PERFIL.get(zona, ""),
        "movimento": mov,
        "badges": badges,
        "palpites": (estilo or {}).get("n") or 0,
        "pct_casa": (estilo or {}).get("pct_casa"),
        "pct_empate": (estilo or {}).get("pct_empate"),
        "pct_fora": (estilo or {}).get("pct_fora"),
        "media_gols": (estilo or {}).get("media_gols"),
        "assinatura": assinatura,
        "acertos_vencedor": (estilo or {}).get("acertos_vencedor") or 0,
        "acertos_placar": (estilo or {}).get("acertos_placar") or 0,
        "rodadas": rodadas,
        "classificacao_url": "/classificacao",
    }


@app.get("/meu-perfil", response_class=HTMLResponse)
def meu_perfil(request: Request):
    """Visão pública do próprio perfil. Use ?como=visitante para simular outro usuário."""
    import json

    neg = _require_perfil(request)
    if neg:
        return neg
    como = (request.query_params.get("como") or "").strip().lower()
    is_own_view = como != "visitante"
    part = _voter_sessao(request)
    karma = db.karma_resumo(part["id"], voter_id=part["id"]) if part else None
    nutela = db.nutela_resumo(part["id"], voter_id=part["id"]) if part else None
    return render(
        request,
        "meu_perfil.html",
        **_prototipo_times_ctx(),
        **_taxa_ctx(),
        is_own_view=is_own_view,
        perfil_fixado=None,
        bolao_perfil=_bolao_resumo_perfil(part["id"] if part else None),
        perfil_target_id=part["id"] if part else None,
        perfil_viewer_id=part["id"] if part else None,
        karma_resumo=karma,
        karma_resumo_json=json.dumps(karma, ensure_ascii=False) if karma else "null",
        nutela_resumo=nutela,
        nutela_resumo_json=json.dumps(nutela, ensure_ascii=False) if nutela else "null",
        pode_votar_karma=False,
    )


@app.get("/meu-perfil/editar", response_class=HTMLResponse)
def meu_perfil_editar(request: Request):
    """Edição do próprio perfil (sobre + times + banner)."""
    neg = _require_perfil(request)
    if neg:
        return neg
    return render(request, "meu_perfil_editar.html", **_prototipo_times_ctx(), **_taxa_ctx())


@app.get("/perfil/{participante_id:int}", response_class=HTMLResponse)
def perfil_participante(request: Request, participante_id: int):
    """Perfil público de qualquer participante liberado."""
    import json

    neg = _require_perfil(request)
    if neg:
        return neg
    part = db.get_participante(participante_id)
    if not part or part.get("status") != "liberado":
        return RedirectResponse("/classificacao", status_code=303)
    sess = _voter_sessao(request)
    if sess and int(sess["id"]) == int(participante_id):
        return RedirectResponse("/meu-perfil", status_code=303)
    voter_id = int(sess["id"]) if sess else None
    fixado = _perfil_publico_payload(part, voter_id=voter_id)
    karma = db.karma_resumo(part["id"], voter_id=voter_id)
    nutela = db.nutela_resumo(part["id"], voter_id=voter_id)
    return render(
        request,
        "meu_perfil.html",
        **_prototipo_times_ctx(),
        **_taxa_ctx(),
        is_own_view=False,
        perfil_fixado=fixado,
        perfil_fixado_json=json.dumps(fixado, ensure_ascii=False),
        bolao_perfil=_bolao_resumo_perfil(part["id"]),
        perfil_target_id=part["id"],
        perfil_viewer_id=voter_id,
        karma_resumo=karma,
        karma_resumo_json=json.dumps(karma, ensure_ascii=False),
        nutela_resumo=nutela,
        nutela_resumo_json=json.dumps(nutela, ensure_ascii=False),
        pode_votar_karma=bool(karma.get("pode_votar")),
    )


@app.get("/perfil/{participante_id:int}/karma")
def perfil_karma_get(request: Request, participante_id: int):
    neg = _require_perfil(request)
    if neg:
        return JSONResponse({"erro": "Não autorizado"}, status_code=401)
    part = db.get_participante(participante_id)
    if not part or part.get("status") != "liberado":
        return JSONResponse({"erro": "Perfil não encontrado"}, status_code=404)
    voter = _voter_sessao(request)
    return JSONResponse(db.karma_resumo(participante_id, voter_id=voter["id"] if voter else None))


@app.put("/perfil/{participante_id:int}/karma")
async def perfil_karma_put(request: Request, participante_id: int):
    neg = _require_perfil(request)
    if neg:
        return JSONResponse({"erro": "Não autorizado"}, status_code=401)
    part = db.get_participante(participante_id)
    if not part or part.get("status") != "liberado":
        return JSONResponse({"erro": "Perfil não encontrado"}, status_code=404)
    voter = _voter_sessao(request)
    if not voter:
        return JSONResponse({"erro": "Não autorizado"}, status_code=401)
    if int(voter["id"]) == int(participante_id):
        return JSONResponse({"erro": "Não pode votar no próprio karma"}, status_code=403)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"erro": "JSON inválido"}, status_code=400)
    categoria = (body or {}).get("categoria")
    nivel = (body or {}).get("nivel")
    try:
        db.salvar_karma_voto(voter["id"], participante_id, categoria, nivel)
    except (TypeError, ValueError) as exc:
        return JSONResponse({"erro": str(exc)}, status_code=400)
    return JSONResponse(db.karma_resumo(participante_id, voter_id=voter["id"]))


@app.get("/perfil/{participante_id:int}/nutela")
def perfil_nutela_get(request: Request, participante_id: int):
    neg = _require_perfil(request)
    if neg:
        return JSONResponse({"erro": "Não autorizado"}, status_code=401)
    part = db.get_participante(participante_id)
    if not part or part.get("status") != "liberado":
        return JSONResponse({"erro": "Perfil não encontrado"}, status_code=404)
    voter = _voter_sessao(request)
    return JSONResponse(db.nutela_resumo(participante_id, voter_id=voter["id"] if voter else None))


@app.put("/perfil/{participante_id:int}/nutela")
async def perfil_nutela_put(request: Request, participante_id: int):
    neg = _require_perfil(request)
    if neg:
        return JSONResponse({"erro": "Não autorizado"}, status_code=401)
    part = db.get_participante(participante_id)
    if not part or part.get("status") != "liberado":
        return JSONResponse({"erro": "Perfil não encontrado"}, status_code=404)
    voter = _voter_sessao(request)
    if not voter:
        return JSONResponse({"erro": "Não autorizado"}, status_code=401)
    if int(voter["id"]) == int(participante_id):
        return JSONResponse({"erro": "Não pode votar no próprio nutela"}, status_code=403)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"erro": "JSON inválido"}, status_code=400)
    valor = (body or {}).get("valor")
    try:
        db.salvar_nutela_voto(voter["id"], participante_id, valor)
    except (TypeError, ValueError) as exc:
        return JSONResponse({"erro": str(exc)}, status_code=400)
    return JSONResponse(db.nutela_resumo(participante_id, voter_id=voter["id"]))


@app.get("/meu-perfil/clubes.json")
def meu_perfil_clubes_json(request: Request):
    neg = _require_perfil(request)
    if neg:
        return neg
    from src.clubes_catalogo import carregar_clubes

    clubes = [c for c in carregar_clubes() if c.get("tem_emblema")]
    return JSONResponse({"clubes": clubes, "total": len(clubes)})


@app.get("/prototipo/perfil", include_in_schema=False)
@app.get("/prototipo/perfil/publico", include_in_schema=False)
@app.get("/prototipo/perfil/benevides", include_in_schema=False)
@app.get("/prototipo/times", include_in_schema=False)
@app.get("/prototipo/times/clubes.json", include_in_schema=False)
def legado_prototipo_perfil(request: Request):
    """Redirects das rotas antigas de protótipo."""
    path = request.url.path.rstrip("/")
    q = request.url.query
    suffix = f"?{q}" if q else ""
    if path.endswith("/benevides"):
        part = db.get_participante_por_nome("Benevides")
        if part:
            return RedirectResponse(f"/perfil/{part['id']}{suffix}", status_code=301)
        return RedirectResponse(f"/meu-perfil{suffix}", status_code=301)
    if path.endswith("/publico"):
        return RedirectResponse(f"/meu-perfil{suffix}", status_code=301)
    if path.endswith("/clubes.json"):
        return RedirectResponse("/meu-perfil/clubes.json", status_code=301)
    if path.endswith("/times"):
        return RedirectResponse("/meu-perfil/editar#times", status_code=301)
    return RedirectResponse(f"/meu-perfil/editar{suffix}", status_code=301)


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
    # First paint leve: só cascas dos anos. Frases vêm de /grupo/listra/{ano}.json
    # ao abrir cada <details> (ano atual carrega sozinho por já nascer aberto).
    listras = db.resumo_listra_anos()
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


@app.get("/grupo/listra/{ano}.json")
def grupo_listra_ano_json(request: Request, ano: int):
    """Frases de um ano — consumidas sob demanda pelo front."""
    from src.listra_seed import LISTRA_ANOS, listra_titulo

    if ano not in LISTRA_ANOS:
        raise HTTPException(status_code=404, detail="Ano da Listra não encontrado.")
    frases = db.list_listra_frases(ano)
    return JSONResponse(
        {
            "ano": ano,
            "titulo": listra_titulo(ano),
            "total": len(frases),
            "frases": [db.listra_frase_api(f) for f in frases],
        },
        headers={"Cache-Control": "private, max-age=60"},
    )


@app.get("/grupo/listra/frase/{frase_id}.json")
def grupo_listra_frase_json(request: Request, frase_id: int):
    """Lookup de uma frase (deep-link #listra-frase-ID)."""
    frase = db.get_listra_frase(frase_id)
    if not frase:
        raise HTTPException(status_code=404, detail="Frase não encontrada.")
    return JSONResponse(
        db.listra_frase_api(frase),
        headers={"Cache-Control": "private, max-age=60"},
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
async def grupo_listra_criar(request: Request):
    """Cria uma ou várias frases (campos repetidos no form)."""
    from src.listra_seed import LISTRA_ANO_ATUAL

    caps = _listra_caps(request)
    if not caps["pode_adicionar"]:
        return RedirectResponse(
            "/grupo/listra?erro="
            + quote("Você não tem permissão para adicionar frases na Listra."),
            status_code=303,
        )
    form = await request.form()
    textos = [str(v) for v in form.getlist("texto")]
    responsaveis = [str(v) for v in form.getlist("responsavel")]
    emojis = [str(v) for v in form.getlist("emoji")]
    destaques = [str(v) for v in form.getlist("destaque")]
    ano_raw = form.get("ano")
    try:
        ano = int(ano_raw) if ano_raw not in (None, "") else LISTRA_ANO_ATUAL
    except (TypeError, ValueError):
        ano = LISTRA_ANO_ATUAL

    part = caps["participante"]
    criadas: list[dict] = []
    primeiro_erro: str | None = None
    for i, texto in enumerate(textos):
        if not (texto or "").strip():
            continue
        responsavel = responsaveis[i] if i < len(responsaveis) else ""
        emoji = emojis[i] if i < len(emojis) else ""
        destaque = destaques[i] if i < len(destaques) else ""
        try:
            frase = db.criar_listra_frase(
                texto,
                responsavel,
                criado_por_id=part["id"] if part else None,
                ano=ano,
                emoji=emoji,
                destaque=destaque,
            )
            criadas.append(frase)
        except ValueError as exc:
            if primeiro_erro is None:
                primeiro_erro = str(exc)

    if not criadas:
        return RedirectResponse(
            f"/grupo/listra?erro={quote(primeiro_erro or 'Informe ao menos uma frase.')}",
            status_code=303,
        )
    if len(criadas) == 1:
        msg = "Frase adicionada à Listra"
    else:
        msg = f"{len(criadas)} frases adicionadas à Listra"
        if primeiro_erro:
            msg += f" (algumas falharam: {primeiro_erro})"
    ultima = criadas[-1]
    return RedirectResponse(
        f"/grupo/listra?msg={quote(msg)}#listra-frase-{ultima['id']}",
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
        candidatos_meliante=db.list_participantes_candidatos_meliante(),
        candidatos_vincular=db.list_participantes_para_vincular_meliante(),
        total_frases=len(db.list_listra_frases()),
        msg=request.query_params.get("msg"),
        erro=request.query_params.get("erro"),
        **_taxa_ctx(),
    )


@app.post("/admin/listra/meliantes")
def admin_listra_meliante_criar(
    request: Request,
    nome: str = Form(""),
    participante_id: str = Form(""),
):
    if not admin_ok(request):
        return _redirect_acesso("entrar")
    try:
        pid_raw = (participante_id or "").strip()
        if pid_raw.isdigit() and int(pid_raw) > 0:
            criado = db.criar_listra_meliante(participante_id=int(pid_raw))
        else:
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


@app.post("/admin/listra/meliantes/vincular")
def admin_listra_meliante_vincular(
    request: Request,
    nome: str = Form(...),
    participante_id: str = Form(""),
):
    if not admin_ok(request):
        return _redirect_acesso("entrar")
    pid_raw = (participante_id or "").strip()
    if not pid_raw.isdigit() or int(pid_raw) <= 0:
        return RedirectResponse(
            f"/admin/listra?erro={quote('Selecione um usuário para vincular')}#meliantes",
            status_code=303,
        )
    try:
        vinculado = db.vincular_listra_meliante(nome, int(pid_raw))
    except ValueError as exc:
        return RedirectResponse(
            f"/admin/listra?erro={quote(str(exc))}#meliantes",
            status_code=303,
        )
    return RedirectResponse(
        f"/admin/listra?msg={quote(f'{vinculado} vinculado ao usuário')}#meliantes",
        status_code=303,
    )


@app.post("/admin/listra/meliantes/desvincular")
def admin_listra_meliante_desvincular(request: Request, nome: str = Form(...)):
    if not admin_ok(request):
        return _redirect_acesso("entrar")
    try:
        livre = db.desvincular_listra_meliante(nome)
    except ValueError as exc:
        return RedirectResponse(
            f"/admin/listra?erro={quote(str(exc))}#meliantes",
            status_code=303,
        )
    return RedirectResponse(
        f"/admin/listra?msg={quote(f'{livre} agora é nome livre')}#meliantes",
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
    # Página pública: stats + cascas dos anos. A timeline completa só carrega
    # ao abrir o <details> (evita ~1,5k nós / ~2MB de HTML no first paint).
    eventos = db.list_xonha_eventos(com_motivo=False)
    return render(
        request,
        "xonhometro.html",
        total_eventos=len(eventos),
        timeline_anos=db.resumo_xonha_anos(eventos),
        stats=db.xonha_stats(eventos),
        **_taxa_ctx(),
    )


@app.get("/xonhometro/timeline.json")
def xonhometro_timeline_json(request: Request):
    """Payload da linha do tempo — consumido sob demanda pelo front."""
    eventos = db.list_xonha_eventos(com_motivo=True)
    anos = db.agrupar_xonha_eventos_por_ano(eventos)
    payload = [
        {
            "ano": g["ano"],
            "quantidade": g["quantidade"],
            "eventos": [
                {
                    "id": e["id"],
                    "tipo": e["tipo"],
                    "data": e["data"],
                    "hora": e.get("hora"),
                    "motivo": e.get("motivo") or "",
                }
                for e in g["eventos"]
            ],
        }
        for g in anos
    ]
    return JSONResponse(
        payload,
        headers={"Cache-Control": "private, max-age=60"},
    )


@app.get("/admin/xonhometro", response_class=HTMLResponse)
def admin_xonhometro(request: Request):
    if not admin_ok(request):
        return _redirect_acesso("entrar")
    # First paint leve: stats + cascas dos anos. Formulários só sob demanda.
    import_meta = None
    try:
        from src.xonhometro_seed import meta_eventos_import

        import_meta = meta_eventos_import()
    except Exception:
        import_meta = None
    eventos = db.list_xonha_eventos(com_motivo=False)
    return render(
        request,
        "admin_xonhometro.html",
        timeline_anos=db.resumo_xonha_anos(eventos),
        stats=db.xonha_stats(eventos),
        import_meta=import_meta,
        msg=request.query_params.get("msg"),
        erro=request.query_params.get("erro"),
        **_taxa_ctx(),
    )


@app.get("/admin/xonhometro/anos/{ano}.json")
def admin_xonhometro_ano_json(request: Request, ano: str):
    """Registros de um ano para edição — carregados ao abrir o <details>."""
    if not admin_ok(request):
        return JSONResponse({"erro": "Não autorizado"}, status_code=401)
    eventos = db.list_xonha_eventos_ano(ano, com_motivo=True)
    payload = {
        "ano": str(ano),
        "quantidade": len(eventos),
        "eventos": [
            {
                "id": e["id"],
                "tipo": e["tipo"],
                "data": e["data"],
                "hora": e.get("hora") or "",
                "motivo": e.get("motivo") or "",
            }
            for e in eventos
        ],
    }
    return JSONResponse(
        payload,
        headers={"Cache-Control": "private, max-age=30"},
    )


@app.post("/admin/xonhometro/importar-whatsapp")
def admin_xonhometro_importar_whatsapp(request: Request):
    if not admin_ok(request):
        return _redirect_acesso("entrar")
    try:
        resultado = db.importar_xonha_eventos_whatsapp(substituir=True)
    except (FileNotFoundError, ValueError) as exc:
        return RedirectResponse(
            f"/admin/xonhometro?erro={quote(str(exc))}",
            status_code=303,
        )
    msg = (
        f"Importados {resultado['inseridos']} eventos do WhatsApp "
        f"({resultado['total_atual']} no total)"
    )
    return RedirectResponse(
        f"/admin/xonhometro?msg={quote(msg)}",
        status_code=303,
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
    janela = db.get_janela()
    volta_liberada = _volta_liberada(janela)
    perna_default = "volta" if janela == "volta" else "ida"
    if FASE_IDS.index(fase) > fase_idx:
        return RedirectResponse(
            f"/transparencia?fase={fase_atual}&perna={perna_default}",
            status_code=303,
        )

    perna = request.query_params.get("perna") or perna_default
    if perna not in ("ida", "volta"):
        perna = perna_default
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
    janela = db.get_janela()
    volta_liberada = _volta_liberada(janela)
    perna_default = "volta" if janela == "volta" else "ida"
    if FASE_IDS.index(fase) > fase_idx:
        return RedirectResponse(
            f"/admin/palpites?fase={fase_atual}&perna={perna_default}",
            status_code=303,
        )

    perna = request.query_params.get("perna") or perna_default
    if perna not in ("ida", "volta"):
        perna = perna_default
    if perna == "volta" and not volta_liberada:
        return RedirectResponse(
            f"/admin/palpites?fase={fase}&perna=ida",
            status_code=303,
        )

    tabelas = [
        t for t in montar_portal(fase, exigir_resultado=False) if t.get("perna") == perna
    ]
    tabelas_geral: list = []
    for fase_id in FASE_IDS:
        tabelas_geral.extend(montar_portal(fase_id, exigir_resultado=False))
    return render(
        request,
        "admin_palpites.html",
        fase=fase,
        fases=fases_ui,
        perna=perna,
        janela=janela,
        volta_liberada=volta_liberada,
        tabelas=tabelas,
        metricas_gerais=metricas_gerais(tabelas),
        ranking=ranking_apostadores(tabelas_geral),
    )


@app.get("/admin/cobranca", response_class=HTMLResponse)
def admin_cobranca(request: Request):
    """Quem já/não palpitou na fase+perna atual, com WhatsApp individual."""
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
            f"/admin/cobranca?fase={fase_atual}",
            status_code=303,
        )

    janela = db.get_janela()
    volta_liberada = _volta_liberada(janela)
    perna_default = "volta" if janela == "volta" else "ida"
    perna = request.query_params.get("perna") or perna_default
    if perna not in ("ida", "volta"):
        perna = perna_default
    if perna == "volta" and not volta_liberada:
        return RedirectResponse(
            f"/admin/cobranca?fase={fase}&perna=ida",
            status_code=303,
        )

    status = db.status_palpites_liberados(
        fase, perna, so_abertos=True, janela=janela
    )
    fase_label = next((f["label"] for f in FASES if f["id"] == fase), fase)
    perna_label = "Ida" if perna == "ida" else "Volta"
    base = PUBLIC_BASE_URL or str(request.base_url).rstrip("/")
    n_sem_wa = 0
    for p in status["incompletos"]:
        msg = db.mensagem_whatsapp_cobranca_palpite(
            p["nome"],
            base,
            p["token"],
            fase_label=fase_label,
            perna_label=perna_label,
            n_feitos=int(p["n_feitos"]),
            n_jogos=int(p["n_jogos"]),
            trava_min=TRAVA_PALPITE_ANTES_MIN,
            jogos=p.get("faltando_jogos") or [],
        )
        diag = db.diagnostico_celular_whatsapp(p.get("celular"))
        p["wa_msg"] = msg
        p["wa_diag"] = diag
        p["wa_url"] = db.url_whatsapp_chat(p.get("celular"), msg) if diag["ok"] else None
        p["wa_url_me"] = (
            db.url_whatsapp_chat_me(p.get("celular"), msg) if diag["ok"] else None
        )
        if not diag["ok"]:
            n_sem_wa += 1

    return render(
        request,
        "admin_cobranca.html",
        fase=fase,
        fases=fases_ui,
        perna=perna,
        janela=janela,
        volta_liberada=volta_liberada,
        fase_label=fase_label,
        perna_label=perna_label,
        status=status,
        trava_antes_min=TRAVA_PALPITE_ANTES_MIN,
        admin_cobranca_count=status.get("n_incompletos") or 0,
        n_sem_wa=n_sem_wa,
        base_url=base,
        msg=request.query_params.get("msg"),
        erro=request.query_params.get("erro"),
    )


@app.post("/admin/cobranca/celular/{participante_id}")
def admin_cobranca_celular(
    request: Request,
    participante_id: int,
    celular: str = Form(""),
    fase: str = Form(""),
    perna: str = Form(""),
):
    """Corrige o celular direto na página Quem palpitou."""
    if not admin_ok(request):
        return _redirect_acesso("entrar")
    fase_atual = db.get_fase_atual()
    if fase not in FASE_IDS:
        fase = fase_atual
    if perna not in ("ida", "volta"):
        perna = "volta" if db.get_janela() == "volta" else "ida"
    part = db.get_participante(participante_id)
    if not part or part.get("status") != "liberado":
        return RedirectResponse(
            f"/admin/cobranca?fase={fase}&perna={perna}&erro={quote('Participante não liberado')}",
            status_code=303,
        )
    try:
        db.atualizar_celular_participante(participante_id, celular)
    except ValueError as exc:
        return RedirectResponse(
            f"/admin/cobranca?fase={fase}&perna={perna}&erro={quote(str(exc))}",
            status_code=303,
        )
    return RedirectResponse(
        f"/admin/cobranca?fase={fase}&perna={perna}&msg={quote('Celular atualizado')}",
        status_code=303,
    )


@app.get("/admin/cobranca/avisar/{participante_id}")
def admin_cobranca_avisar(request: Request, participante_id: int):
    """Abre o WhatsApp com lembrete de palpites pendentes."""
    if not admin_ok(request):
        return _redirect_acesso("entrar")

    fase_atual = db.get_fase_atual()
    fase = request.query_params.get("fase") or fase_atual
    if fase not in FASE_IDS:
        fase = fase_atual
    janela = db.get_janela()
    perna_default = "volta" if janela == "volta" else "ida"
    perna = request.query_params.get("perna") or perna_default
    if perna not in ("ida", "volta"):
        perna = perna_default

    part = db.get_participante(participante_id)
    if not part or part.get("status") != "liberado":
        return RedirectResponse(
            f"/admin/cobranca?fase={fase}&perna={perna}&erro={quote('Participante não liberado')}",
            status_code=303,
        )

    status = db.status_palpites_liberados(
        fase, perna, so_abertos=True, janela=janela
    )
    row = next(
        (p for p in status["incompletos"] if p["id"] == participante_id),
        None,
    )
    if not row:
        return RedirectResponse(
            f"/admin/cobranca?fase={fase}&perna={perna}&msg={quote('Esse participante já completou os palpites')}",
            status_code=303,
        )

    fase_label = next((f["label"] for f in FASES if f["id"] == fase), fase)
    perna_label = "Ida" if perna == "ida" else "Volta"
    base = PUBLIC_BASE_URL or str(request.base_url).rstrip("/")
    msg = db.mensagem_whatsapp_cobranca_palpite(
        part["nome"],
        base,
        part["token"],
        fase_label=fase_label,
        perna_label=perna_label,
        n_feitos=int(row["n_feitos"]),
        n_jogos=int(row["n_jogos"]),
        trava_min=TRAVA_PALPITE_ANTES_MIN,
        jogos=row.get("faltando_jogos") or [],
    )
    wa_url = db.url_whatsapp_chat(part.get("celular"), msg)
    if not wa_url:
        return RedirectResponse(
            f"/admin/cobranca?fase={fase}&perna={perna}&erro={quote('Celular inválido para WhatsApp')}",
            status_code=303,
        )
    return RedirectResponse(wa_url, status_code=303)


@app.get("/classificacao", response_class=HTMLResponse)
def classificacao(request: Request):
    if not admin_ok(request) and not request.session.get("participante_token"):
        return RedirectResponse("/?acesso=entrar", status_code=303)

    from src.ranking import _rodada_historico_vazia

    historico_all = db.list_rodadas_historico()
    # Esconde fechamentos fantasma (ninguém pontuou) na nav da Classificação.
    historico = []
    for h in historico_all:
        full = db.get_rodada_historico(int(h["id"]))
        if full and not _rodada_historico_vazia(full):
            historico.append(h)
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
        if not rodada_sel or _rodada_historico_vazia(rodada_sel):
            return RedirectResponse("/classificacao", status_code=303)
        linhas = rodada_sel["linhas"]
        modo_historico = True
        fase = rodada_sel["fase"]
        janela = rodada_sel["janela"]
    else:
        linhas = calcular_classificacao()
        fase = db.get_meta("fase_atual", "oitavas")
        janela = db.get_janela()

    hall_data = trofeus_hall(fase if not modo_historico else fase)
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
        hall=hall_data.get("cards") or [],
    )


@app.get("/inscricao", response_class=HTMLResponse)
def inscricao_get(request: Request):
    if not inscricao_aberta():
        return render(
            request,
            "inscricao.html",
            inscricao_encerrada=True,
            inscricao_fecha_em=INSCRICAO_FECHA_EM.strftime("%d/%m/%Y às %H:%M"),
            **_taxa_ctx(),
        )
    draft = request.session.pop("inscricao_draft", None) or {}
    return render(
        request,
        "inscricao.html",
        inscricao_encerrada=False,
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
    if not inscricao_aberta():
        return RedirectResponse(
            "/inscricao?erro=" + quote("Inscrições encerradas."),
            status_code=303,
        )
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

    return _render_meus_palpites(request, part)


@app.get("/bolao/meus-palpites", response_class=HTMLResponse)
@app.get("/bolao/meuspalpites", response_class=HTMLResponse)
def pagina_meus_palpites(request: Request):
    """Rota limpa: usa a sessão. O link mágico /p/{token} continua valendo."""
    token = request.session.get("participante_token")
    if not token:
        return RedirectResponse("/?acesso=entrar", status_code=303)
    part = db.get_participante_por_token(token)
    if not part:
        request.session.pop("participante_token", None)
        return RedirectResponse("/?acesso=entrar", status_code=303)
    if part.get("status") != "liberado":
        return RedirectResponse(f"/p/{part['token']}", status_code=303)
    gate = _gate_credenciais(part)
    if gate:
        return gate
    return _render_meus_palpites(request, part)


def _render_meus_palpites(request: Request, part: dict):
    palpites = db.palpites_do_participante(part["id"])
    fase_atual = db.get_fase_atual()
    fase_idx = FASE_IDS.index(fase_atual) if fase_atual in FASE_IDS else 0
    fases_ui = [
        {
            **f,
            "unlocked": FASE_IDS.index(f["id"]) <= fase_idx,
            "encerrada": FASE_IDS.index(f["id"]) < fase_idx,
            "ativa": f["id"] == fase_atual,
        }
        for f in FASES
    ]
    janela = db.get_janela()
    # Ida só editável na fase atual e quando a janela ainda é ida.
    perna_default = "volta" if janela == "volta" else "ida"
    return render(
        request,
        "palpites.html",
        participante=part,
        janela=janela,
        fase_atual=fase_atual,
        fases=fases_ui,
        perna_default=perna_default,
        confrontos=_enrich_confrontos(
            db.list_confrontos_completos(fase_atual), janela=janela
        ),
        palpites_jogo=palpites["jogos"],
        palpites_pen=palpites["penaltis"],
        trava_antes_min=TRAVA_PALPITE_ANTES_MIN,
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


def _safe_conta_next(next_url: str | None) -> str | None:
    """Permite voltar a páginas internas conhecidas após salvar a conta."""
    n = (next_url or "").strip()
    if n in {"/meu-perfil", "/meu-perfil/editar", "/prototipo/perfil", "/prototipo/perfil/publico"}:
        if n.startswith("/prototipo/perfil/publico"):
            return "/meu-perfil"
        if n.startswith("/prototipo/perfil"):
            return "/meu-perfil/editar"
        return n
    return None


def _redirect_after_conta(
    token: str,
    *,
    next_url: str | None = None,
    msg: str | None = None,
    erro: str | None = None,
) -> RedirectResponse:
    dest = _safe_conta_next(next_url)
    if dest:
        parts: list[str] = []
        if msg:
            parts.append(f"msg={quote(msg)}")
        if erro:
            parts.append(f"erro={quote(erro)}")
        suffix = f"?{'&'.join(parts)}" if parts else ""
        return RedirectResponse(dest + suffix, status_code=303)
    return _redirect_conta_drawer(token, msg=msg, erro=erro)


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
    next_url: str = Form("", alias="next"),
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
        return _redirect_after_conta(token, next_url=next_url, erro=str(exc))

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
            return _redirect_after_conta(token, next_url=next_url, erro="Foto deve ser jpg/png/webp")
        data = await avatar.read()
        if not data or len(data) > AVATAR_MAX_BYTES:
            return _redirect_after_conta(token, next_url=next_url, erro="Foto invalida ou maior que 3MB")
        if part.get("avatar_path"):
            old = AVATARES_DIR / part["avatar_path"]
            if old.is_file():
                old.unlink(missing_ok=True)
        rel = f"{part['id']}_{int(time.time())}{ext}"
        (AVATARES_DIR / rel).write_bytes(data)
        db.salvar_avatar(part["id"], rel)

    return _redirect_after_conta(token, next_url=next_url, msg="Dados atualizados")


@app.post("/p/{token}/conta/senha")
async def conta_alterar_senha(
    request: Request,
    token: str,
    senha_atual: str = Form(""),
    senha_nova: str = Form(""),
    senha_nova2: str = Form(""),
    next_url: str = Form("", alias="next"),
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
        return _redirect_after_conta(token, next_url=next_url, erro=msg)

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

    return _redirect_after_conta(token, next_url=next_url, msg="Senha atualizada")


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
    fase_atual = db.get_fase_atual()
    # Só aceita palpites da fase liberada atual (fases anteriores ficam fechadas).
    confrontos = db.list_confrontos_completos(fase_atual)
    from src.seed_data import jogo_palpite_travado

    faltando_penaltis: list[int] = []
    try:
        for c in confrontos:
            ida = next(j for j in c["jogos"] if j["perna"] == "ida")
            volta = next(j for j in c["jogos"] if j["perna"] == "volta")

            # Ida editável só na janela "ida". Volta (e pênaltis) liberada
            # junto — os confrontos da fase já são conhecidos.
            if janela == "ida":
                gm = form.get(f"ida_{c['id']}_m")
                gv = form.get(f"ida_{c['id']}_v")
                if gm is not None and gv is not None and str(gm) != "" and str(gv) != "":
                    if not jogo_palpite_travado(ida.get("inicio_em"), janela=janela):
                        db.salvar_palpite_jogo(part["id"], ida["id"], int(gm), int(gv))

            if janela in ("ida", "volta"):
                gm = form.get(f"volta_{c['id']}_m")
                gv = form.get(f"volta_{c['id']}_v")
                if gm is None or gv is None or str(gm) == "" or str(gv) == "":
                    continue
                if jogo_palpite_travado(volta.get("inicio_em"), janela=janela):
                    continue
                # Sempre grava o placar antes de validar pênaltis, para não
                # descartar o restante do formulário se faltar uma escolha.
                db.salvar_palpite_jogo(part["id"], volta["id"], int(gm), int(gv))

                # Agregado para pênaltis = resultado oficial da Ida + palpite da Volta.
                if (
                    ida.get("gols_mandante") is None
                    or ida.get("gols_visitante") is None
                ):
                    db.limpar_palpite_penaltis(part["id"], c["id"])
                    continue
                empate = agregado_empatado(
                    int(ida["gols_mandante"]),
                    int(ida["gols_visitante"]),
                    int(gm),
                    int(gv),
                )
                pen = form.get(f"pen_{c['id']}")
                if empate:
                    if pen not in ("a", "b"):
                        faltando_penaltis.append(int(c["id"]))
                    else:
                        db.salvar_palpite_penaltis(part["id"], c["id"], str(pen))
                else:
                    db.limpar_palpite_penaltis(part["id"], c["id"])
    except ValueError:
        return RedirectResponse(
            f"/p/{token}?erro={quote('Placar inválido')}",
            status_code=303,
        )

    if faltando_penaltis:
        n = len(faltando_penaltis)
        if n == 1:
            aviso = (
                "Placares salvos. Ainda falta escolher quem passa nos pênaltis "
                f"no jogo ({faltando_penaltis[0]})."
            )
        else:
            aviso = (
                "Placares salvos. Ainda falta escolher quem passa nos pênaltis "
                f"em {n} jogos empatados."
            )
        return RedirectResponse(
            f"/p/{token}?erro={quote(aviso)}",
            status_code=303,
        )

    return RedirectResponse(
        f"/p/{token}?msg={quote('Palpites salvos')}",
        status_code=303,
    )


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
            "encerrada": FASE_IDS.index(f["id"]) < fase_idx,
            "ativa": f["id"] == fase_atual,
        }
        for f in FASES
    ]
    confrontos_por_fase = {
        f["id"]: _enrich_confrontos(db.list_confrontos_completos(f["id"]))
        for f in FASES
    }
    perna_default_por_fase = {
        f["id"]: _perna_default_confrontos(confrontos_por_fase.get(f["id"]) or [])
        for f in FASES
    }
    perna_default = perna_default_por_fase.get(fase_atual, "ida")
    proxima_fase = None
    if fase_idx + 1 < len(FASE_IDS):
        pid = FASE_IDS[fase_idx + 1]
        proxima_fase = next((f for f in FASES if f["id"] == pid), None)
    arvore_fases = []
    for f in FASES:
        if f["id"] == "oitavas":
            continue
        origem = fase_anterior(f["id"])
        classificados = db.classificados_da_fase(origem) if origem else []
        n_chaves = int(f["slots"])
        existentes = confrontos_por_fase.get(f["id"]) or []
        pronto = len(classificados) >= n_chaves * 2
        # Só mostra bloco com ação possível (montar/remontar) ou já cadastrado.
        if not pronto and not existentes:
            continue
        arvore_fases.append(
            {
                "fase": f,
                "origem": origem,
                "classificados": classificados,
                "n_chaves": n_chaves,
                "n_clubes": n_chaves * 2,
                "pronto": pronto,
                "existentes": existentes,
            }
        )
    return render(
        request,
        "admin.html",
        janela=db.get_janela(),
        janelas=JANELAS,
        fase_atual=fase_atual,
        fases=fases_ui,
        confrontos_por_fase=confrontos_por_fase,
        perna_default=perna_default,
        perna_default_por_fase=perna_default_por_fase,
        proxima_fase=proxima_fase,
        arvore_fases=arvore_fases,
        trava_antes_min=TRAVA_PALPITE_ANTES_MIN,
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
    acao: str = Form("senha"),
    username: str = Form(""),
    senha_nova: str = Form(""),
):
    negado = require_dono(request)
    if negado:
        return negado
    acao_ok = (acao or "").strip().lower()
    try:
        if acao_ok == "username":
            updated = db.admin_redefinir_credenciais(
                participante_id,
                username=username.strip() or None,
                senha_nova=None,
            )
            nome = updated.get("nome") or "participante"
            user = updated.get("username") or "(sem username)"
            msg = f"Username de {nome} atualizado para {user}."
        elif acao_ok == "senha":
            updated = db.admin_redefinir_credenciais(
                participante_id,
                senha_nova=senha_nova,
                username=None,
            )
            nome = updated.get("nome") or "participante"
            user = updated.get("username") or "(sem username)"
            msg = (
                f"Senha de {nome} ({user}) redefinida. "
                "Passe a senha nova no Zap."
            )
        else:
            updated = db.admin_redefinir_credenciais(
                participante_id,
                senha_nova=senha_nova or None,
                username=username.strip() or None,
            )
            nome = updated.get("nome") or "participante"
            user = updated.get("username") or "(sem username)"
            msg = (
                f"Credenciais de {nome} ({user}) redefinidas. "
                "Passe a senha nova no Zap."
            )
    except ValueError as e:
        return RedirectResponse(
            f"/admin/credenciais?erro={quote(str(e))}",
            status_code=303,
        )
    return RedirectResponse(
        f"/admin/credenciais?msg={quote(msg)}",
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
    if not admin_ok(request):
        return _redirect_acesso("entrar")
    part = db.get_participante(participante_id)
    if not part or part.get("status") != "liberado":
        return RedirectResponse(
            "/admin?sec=inscricoes&erro=Participante+nao+liberado", status_code=303
        )
    base = PUBLIC_BASE_URL or str(request.base_url).rstrip("/")
    msg = db.mensagem_whatsapp_link(part["nome"], base, part["token"])
    wa_url = db.url_whatsapp_chat(part.get("celular"), msg)
    if not wa_url:
        return RedirectResponse(
            "/admin?sec=inscricoes&erro=Celular+invalido+para+WhatsApp",
            status_code=303,
        )
    db.marcar_link_enviado(participante_id, enviado=True)
    db.marcar_pedidos_recuperacao_atendidos_participante(participante_id)
    return RedirectResponse(wa_url, status_code=303)


@app.get("/admin/recuperacao/{pedido_id}/atender")
def admin_recuperacao_atender(request: Request, pedido_id: int):
    """Fecha o pedido de recuperação e abre o WhatsApp com o link."""
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
    base = PUBLIC_BASE_URL or str(request.base_url).rstrip("/")
    msg = db.mensagem_whatsapp_link(pedido["nome"], base, pedido["token"])
    wa_url = db.url_whatsapp_chat(pedido.get("celular"), msg)
    if not wa_url:
        return RedirectResponse(
            "/admin?sec=inscricoes&erro=Celular+invalido+para+WhatsApp",
            status_code=303,
        )
    db.marcar_pedido_recuperacao_atendido(pedido_id)
    db.marcar_pedidos_recuperacao_atendidos_participante(pedido["participante_id"])
    db.marcar_link_enviado(pedido["participante_id"], enviado=True)
    return RedirectResponse(wa_url, status_code=303)


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
    try:
        db.set_resultado_jogo(jogo_id, gols_mandante, gols_visitante, pen)
    except ValueError as e:
        if _admin_wants_json(request):
            from fastapi.responses import JSONResponse

            return JSONResponse({"ok": False, "erro": str(e)}, status_code=400)
        return RedirectResponse(
            f"/admin?erro={str(e).replace(' ', '+')}", status_code=303
        )
    if _admin_wants_json(request):
        from fastapi.responses import JSONResponse

        return JSONResponse({"ok": True, "msg": "Resultado salvo"})
    return RedirectResponse("/admin?msg=Resultado+salvo", status_code=303)


@app.post("/admin/avancar-fase")
def admin_avancar_fase(request: Request):
    """Fecha a fase atual (confirma placares) e libera a próxima."""
    if not admin_ok(request):
        return _redirect_acesso("entrar")
    from urllib.parse import quote

    atual = db.get_fase_atual()
    if atual not in FASE_IDS:
        return RedirectResponse("/admin?erro=Fase+atual+invalida", status_code=303)
    idx = FASE_IDS.index(atual)
    if idx + 1 >= len(FASE_IDS):
        return RedirectResponse("/admin?erro=Nao+ha+proxima+fase", status_code=303)
    proxima = FASE_IDS[idx + 1]
    n = db.confirmar_jogos_da_fase(atual)
    db.set_fase_atual(proxima)
    db.set_janela("ida")
    label = next((f["label"] for f in FASES if f["id"] == proxima), proxima)
    return RedirectResponse(
        f"/admin?msg={quote(f'{atual} fechada ({n} jogos). {label} liberada')}",
        status_code=303,
    )


@app.post("/admin/resultados")
async def admin_resultados(request: Request):
    if not admin_ok(request):
        return _redirect_acesso("entrar")
    from src.seed_data import normalizar_inicio_em
    from fastapi.responses import JSONResponse
    from urllib.parse import quote

    form = await request.form()
    fase = str(form.get("fase") or db.get_fase_atual())
    perna = str(form.get("perna") or "").strip().lower()
    if fase not in FASE_IDS:
        if _admin_wants_json(request):
            return JSONResponse({"ok": False, "erro": "Fase inválida"}, status_code=400)
        return RedirectResponse("/admin?erro=Fase+invalida", status_code=303)
    fase_atual = db.get_fase_atual()
    if fase in FASE_IDS and fase_atual in FASE_IDS:
        if FASE_IDS.index(fase) < FASE_IDS.index(fase_atual):
            erro = "Fase encerrada — avance só pela próxima ou desfaça o avanço"
            if _admin_wants_json(request):
                return JSONResponse({"ok": False, "erro": erro}, status_code=400)
            return RedirectResponse(f"/admin?erro={quote(erro)}", status_code=303)
    if perna and perna not in ("ida", "volta"):
        if _admin_wants_json(request):
            return JSONResponse({"ok": False, "erro": "Perna inválida"}, status_code=400)
        return RedirectResponse("/admin?erro=Perna+invalida", status_code=303)
    confrontos = db.list_confrontos_completos(fase)
    salvos = 0
    horarios = 0
    ignorados_confirmados = 0
    try:
        for c in confrontos:
            for jogo in c.get("jogos") or []:
                if perna and jogo.get("perna") != perna:
                    continue
                jid = jogo["id"]
                confirmado = db.jogo_confirmado(jogo)
                inicio_raw = form.get(f"jogo_{jid}_inicio")
                if inicio_raw is not None:
                    novo = normalizar_inicio_em(str(inicio_raw) if inicio_raw != "" else None)
                    atual = jogo.get("inicio_em") or None
                    if (novo or None) != (atual or None):
                        if confirmado:
                            ignorados_confirmados += 1
                        else:
                            db.set_inicio_jogo(jid, novo)
                            horarios += 1
                gm = form.get(f"jogo_{jid}_m")
                gv = form.get(f"jogo_{jid}_v")
                if gm is None or gv is None or str(gm) == "" or str(gv) == "":
                    continue
                if confirmado:
                    ignorados_confirmados += 1
                    continue
                pen_raw = form.get(f"jogo_{jid}_pen") or ""
                pen = pen_raw if pen_raw in ("a", "b") else None
                db.set_resultado_jogo(jid, int(gm), int(gv), pen)
                salvos += 1
    except ValueError as e:
        msg = str(e) or "Placar inválido"
        if _admin_wants_json(request):
            return JSONResponse({"ok": False, "erro": msg}, status_code=400)
        return RedirectResponse(f"/admin?erro={quote(msg)}", status_code=303)
    if salvos == 0 and horarios == 0:
        erro = (
            "Nenhum resultado editável para salvar"
            if ignorados_confirmados
            else "Nenhum resultado para salvar"
        )
        if _admin_wants_json(request):
            return JSONResponse({"ok": False, "erro": erro}, status_code=400)
        return RedirectResponse(f"/admin?erro={quote(erro)}", status_code=303)
    bits = []
    if salvos:
        bits.append(f"{salvos} resultado(s)")
    if horarios:
        bits.append(f"{horarios} horario(s)")
    msg = " + ".join(bits) + " salvo(s)"
    if _admin_wants_json(request):
        return JSONResponse(
            {
                "ok": True,
                "msg": msg,
                "salvos": salvos,
                "horarios": horarios,
                "ignorados_confirmados": ignorados_confirmados,
            }
        )
    return RedirectResponse(f"/admin?msg={quote(msg)}", status_code=303)


def _fase_do_jogo(jogo_id: int) -> str | None:
    jogo = db.get_jogo(jogo_id)
    if not jogo:
        return None
    with db.get_db() as conn:
        row = conn.execute(
            "SELECT fase FROM confrontos WHERE id = ?", (jogo["confronto_id"],)
        ).fetchone()
        return str(row["fase"]) if row else None


def _fase_admin_encerrada(fase: str | None) -> bool:
    if not fase or fase not in FASE_IDS:
        return False
    atual = db.get_fase_atual()
    if atual not in FASE_IDS:
        return False
    return FASE_IDS.index(fase) < FASE_IDS.index(atual)


@app.post("/admin/jogo/{jogo_id}/confirmar")
def admin_confirmar_jogo(request: Request, jogo_id: int):
    if not admin_ok(request):
        return _redirect_acesso("entrar")
    from fastapi.responses import JSONResponse
    from urllib.parse import quote

    if _fase_admin_encerrada(_fase_do_jogo(jogo_id)):
        erro = "Fase encerrada"
        if _admin_wants_json(request):
            return JSONResponse({"ok": False, "erro": erro}, status_code=400)
        return RedirectResponse(f"/admin?erro={quote(erro)}", status_code=303)
    try:
        db.confirmar_jogo(jogo_id)
    except ValueError as e:
        if _admin_wants_json(request):
            return JSONResponse({"ok": False, "erro": str(e)}, status_code=400)
        return RedirectResponse(f"/admin?erro={quote(str(e))}", status_code=303)
    if _admin_wants_json(request):
        return JSONResponse({"ok": True, "msg": "Jogo confirmado", "jogo_id": jogo_id})
    return RedirectResponse("/admin?msg=Jogo+confirmado", status_code=303)


@app.post("/admin/jogo/{jogo_id}/desfazer-confirmacao")
def admin_desfazer_confirmacao_jogo(request: Request, jogo_id: int):
    if not admin_ok(request):
        return _redirect_acesso("entrar")
    from fastapi.responses import JSONResponse
    from urllib.parse import quote

    if _fase_admin_encerrada(_fase_do_jogo(jogo_id)):
        erro = "Fase encerrada"
        if _admin_wants_json(request):
            return JSONResponse({"ok": False, "erro": erro}, status_code=400)
        return RedirectResponse(f"/admin?erro={quote(erro)}", status_code=303)
    try:
        db.desfazer_confirmacao_jogo(jogo_id)
    except ValueError as e:
        if _admin_wants_json(request):
            return JSONResponse({"ok": False, "erro": str(e)}, status_code=400)
        return RedirectResponse(f"/admin?erro={quote(str(e))}", status_code=303)
    if _admin_wants_json(request):
        return JSONResponse(
            {"ok": True, "msg": "Confirmação desfeita", "jogo_id": jogo_id}
        )
    return RedirectResponse("/admin?msg=Confirmacao+desfeita", status_code=303)


@app.post("/admin/arvore/montar")
async def admin_arvore_montar(request: Request):
    """Monta confrontos de uma fase (quartas/semis/final) a partir do sorteio."""
    if not admin_ok(request):
        return _redirect_acesso("entrar")
    from src.seed_data import normalizar_inicio_em

    form = await request.form()
    fase = str(form.get("fase") or "").strip()
    meta = next((f for f in FASES if f["id"] == fase), None)
    if not meta or fase == "oitavas":
        return RedirectResponse("/admin?erro=Fase+invalida+para+montar", status_code=303)
    n_chaves = int(meta["slots"])
    origem = fase_anterior(fase)
    classificados = {
        c["clube"] for c in (db.classificados_da_fase(origem) if origem else [])
    }
    pares: list[dict] = []
    usados: set[str] = set()
    try:
        for i in range(n_chaves):
            a = str(form.get(f"chave_{i}_a") or "").strip()
            b = str(form.get(f"chave_{i}_b") or "").strip()
            if not a or not b:
                return RedirectResponse(
                    f"/admin?erro=Preencha+todos+os+pares+de+{fase}",
                    status_code=303,
                )
            if a == b:
                return RedirectResponse(
                    "/admin?erro=Clube+repetido+no+mesmo+confronto",
                    status_code=303,
                )
            if a in usados or b in usados:
                return RedirectResponse(
                    "/admin?erro=Clube+usado+em+mais+de+uma+chave",
                    status_code=303,
                )
            if classificados and (a not in classificados or b not in classificados):
                return RedirectResponse(
                    "/admin?erro=Clube+fora+dos+classificados",
                    status_code=303,
                )
            usados.add(a)
            usados.add(b)
            pares.append(
                {
                    "clube_a": a,
                    "clube_b": b,
                    "ida_em": normalizar_inicio_em(str(form.get(f"chave_{i}_ida") or "")),
                    "volta_em": normalizar_inicio_em(
                        str(form.get(f"chave_{i}_volta") or "")
                    ),
                }
            )
        db.substituir_confrontos_fase(fase, pares)
        # Liberar a fase montada (substitui o card "Fase liberada").
        atual = db.get_fase_atual()
        if fase in FASE_IDS and atual in FASE_IDS:
            if FASE_IDS.index(fase) > FASE_IDS.index(atual):
                db.set_fase_atual(fase)
                db.set_janela("ida")
    except ValueError as e:
        from urllib.parse import quote

        return RedirectResponse(f"/admin?erro={quote(str(e))}", status_code=303)
    return RedirectResponse(
        f"/admin?msg={n_chaves}+confronto(s)+de+{fase}+montados",
        status_code=303,
    )


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
