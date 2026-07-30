"""THDFM Bolão Copa do Brasil — app FastAPI."""

from __future__ import annotations

import os
import re
import time
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from src import db
from src.admins import autenticar_admin, list_admins
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
    PUBLIC_BASE_URL,
    ROOT_DIR,
    SECRET_KEY,
    TAXA_PIX,
    TAXA_VALOR_LABEL,
)
from src.ranking import calcular_classificacao, confirmar_rodada, desfazer_ultima_rodada, faixa_zonas
from src.scoring import agregado_empatado
from src.seed_data import emblema_url
from src.transparencia import montar_portal

load_dotenv(ROOT_DIR / ".env")

app = FastAPI(title="Bolão THDFM — Copa do Brasil")
app.add_middleware(SessionMiddleware, secret_key=os.environ.get("SECRET_KEY", SECRET_KEY))

TEMPLATES = Jinja2Templates(directory=str(ROOT_DIR / "templates"))

STATIC = ROOT_DIR / "static"
STATIC.mkdir(exist_ok=True)
EMBLEMAS_DIR.mkdir(parents=True, exist_ok=True)
COMPROVANTES_DIR.mkdir(parents=True, exist_ok=True)
AVATARES_DIR.mkdir(parents=True, exist_ok=True)

app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")
app.mount("/emblemas", StaticFiles(directory=str(EMBLEMAS_DIR)), name="emblemas")
app.mount("/avatars", StaticFiles(directory=str(AVATARES_DIR)), name="avatars")


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
TEMPLATES.env.globals["wa_msg_link"] = db.mensagem_whatsapp_link
TEMPLATES.env.globals["avatar_url"] = avatar_url
TEMPLATES.env.globals["avatar_padrao_url"] = avatar_padrao_url
TEMPLATES.env.filters["celular_fmt"] = db.formatar_celular
TEMPLATES.env.filters["celular_wa"] = db.celular_whatsapp


@app.on_event("startup")
def _startup() -> None:
    db.init_db()
    from src.seed_demo import limpar_demo

    limpar_demo()


def admin_ok(request: Request) -> bool:
    return bool(request.session.get("admin_login"))


def admin_nome(request: Request) -> str:
    return request.session.get("admin_nome") or request.session.get("admin_login") or ""


def render(request: Request, name: str, **ctx):
    token = request.session.get("participante_token")
    part_nav = db.get_participante_por_token(token) if token else None
    is_adm = admin_ok(request)
    ctx.setdefault("is_admin", is_adm)
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
    return TEMPLATES.TemplateResponse(request, name, ctx)


def _remember_participante(request: Request, token: str) -> None:
    request.session["participante_token"] = token


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
    return {
        "taxa_pix": os.environ.get("TAXA_PIX", TAXA_PIX),
        "taxa_valor_label": os.environ.get("TAXA_VALOR_LABEL", TAXA_VALOR_LABEL),
        "admin_whatsapp_url": wa_url,
    }


def _destino_entrada(request: Request) -> str:
    """Para onde mandar quem abre / ou /home, conforme sessão."""
    if admin_ok(request):
        return "/admin"
    token = request.session.get("participante_token")
    if token:
        part = db.get_participante_por_token(token)
        if part:
            return f"/p/{part['token']}"
    return "/inscricao"


@app.get("/")
def raiz(request: Request):
    return RedirectResponse(_destino_entrada(request), status_code=303)


@app.get("/home")
def home(request: Request):
    return RedirectResponse(_destino_entrada(request), status_code=303)


@app.get("/regras", response_class=HTMLResponse)
def regras(request: Request):
    return render(request, "regras.html", **_taxa_ctx())


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
    tabelas = [t for t in montar_portal(fase) if t.get("perna") == perna]
    return render(
        request,
        "transparencia.html",
        fase=fase,
        fases=fases_ui,
        perna=perna,
        tabelas=tabelas,
    )


@app.get("/admin/palpites", response_class=HTMLResponse)
def admin_palpites(request: Request):
    if not admin_ok(request):
        return RedirectResponse("/admin/login", status_code=303)

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

    tabelas = [
        t for t in montar_portal(fase, exigir_resultado=False) if t.get("perna") == perna
    ]
    return render(
        request,
        "admin_palpites.html",
        fase=fase,
        fases=fases_ui,
        perna=perna,
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


@app.get("/p/{token}/conta", response_class=HTMLResponse)
def conta_participante(request: Request, token: str):
    part = db.get_participante_por_token(token)
    if not part:
        raise HTTPException(404, "Link inválido")
    _remember_participante(request, token)
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

    try:
        db.atualizar_nome_participante(part["id"], nome)
    except Exception as exc:
        return RedirectResponse(f"/p/{token}/conta?erro={exc}", status_code=303)

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
            return RedirectResponse(
                f"/p/{token}/conta?erro=Foto+deve+ser+jpg/png/webp",
                status_code=303,
            )
        data = await avatar.read()
        if not data or len(data) > AVATAR_MAX_BYTES:
            return RedirectResponse(
                f"/p/{token}/conta?erro=Foto+invalida+ou+maior+que+3MB",
                status_code=303,
            )
        if part.get("avatar_path"):
            old = AVATARES_DIR / part["avatar_path"]
            if old.is_file():
                old.unlink(missing_ok=True)
        rel = f"{part['id']}_{int(time.time())}{ext}"
        (AVATARES_DIR / rel).write_bytes(data)
        db.salvar_avatar(part["id"], rel)

    return RedirectResponse(f"/p/{token}/conta?msg=Dados+atualizados", status_code=303)


@app.post("/conta/sair")
def conta_sair(request: Request):
    request.session.pop("participante_token", None)
    return RedirectResponse("/inscricao", status_code=303)


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
    if admin_ok(request):
        return RedirectResponse("/admin", status_code=303)
    return render(request, "admin_login.html", erro=request.query_params.get("erro"))


@app.post("/admin/login")
def admin_login(
    request: Request,
    login: str = Form(...),
    password: str = Form(...),
):
    admin = autenticar_admin(login, password)
    if not admin:
        return RedirectResponse("/admin/login?erro=Usuario+ou+senha+incorretos", status_code=303)
    request.session["admin_login"] = admin.login
    request.session["admin_nome"] = admin.nome
    request.session.pop("admin", None)  # legado
    # Admin também palpita: vínculo estável por login (não pelo nick)
    token_atual = request.session.get("participante_token")
    part = db.garantir_participante_admin(
        admin.login, admin.nome, token_preferido=token_atual
    )
    request.session["admin_nome"] = part.get("nome") or admin.nome
    _remember_participante(request, part["token"])
    return RedirectResponse("/admin", status_code=303)


@app.get("/admin/logout")
@app.post("/admin/logout")
def admin_logout(request: Request):
    request.session.pop("admin_login", None)
    request.session.pop("admin_nome", None)
    request.session.pop("admin", None)
    return RedirectResponse("/inscricao", status_code=303)


@app.get("/admin", response_class=HTMLResponse)
def admin_home(request: Request):
    if not admin_ok(request):
        return RedirectResponse("/admin/login", status_code=303)
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
        ultima_rodada=db.get_ultima_rodada_historico(),
        msg=request.query_params.get("msg"),
        erro=request.query_params.get("erro"),
        base_url=base,
        inscricao_url=f"{base}/inscricao",
        public_url_configurada=bool(PUBLIC_BASE_URL),
        **_taxa_ctx(),
    )


@app.get("/admin/comprovantes/{participante_id}")
def admin_comprovante(request: Request, participante_id: int):
    if not admin_ok(request):
        return RedirectResponse("/admin/login", status_code=303)
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
        return RedirectResponse("/admin/login", status_code=303)
    db.liberar_participante(participante_id)
    return RedirectResponse(
        "/admin?sec=inscricoes&msg=Inscricao+liberada", status_code=303
    )


@app.get("/admin/avisar-link/{participante_id}")
def admin_avisar_link(request: Request, participante_id: int):
    """Marca link como enviado e abre o WhatsApp com a mensagem pronta."""
    from urllib.parse import quote

    if not admin_ok(request):
        return RedirectResponse("/admin/login", status_code=303)
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
        return RedirectResponse("/admin/login", status_code=303)
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
        return RedirectResponse("/admin/login", status_code=303)
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
    if not admin_ok(request):
        return RedirectResponse("/admin/login", status_code=303)
    part = db.apagar_participante(participante_id)
    if not part:
        return RedirectResponse(
            "/admin?sec=inscricoes&erro=Participante+nao+encontrado", status_code=303
        )
    _limpar_arquivos_participante(part)
    return RedirectResponse(
        "/admin?sec=inscricoes&msg=Inscricao+apagada", status_code=303
    )


@app.post("/admin/recusar")
def admin_recusar(request: Request, participante_id: int = Form(...)):
    """Recusar = marca como recusada (não apaga; use o × para excluir)."""
    if not admin_ok(request):
        return RedirectResponse("/admin/login", status_code=303)
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
        return RedirectResponse("/admin/login", status_code=303)
    if not db.reabrir_participante(participante_id):
        return RedirectResponse(
            "/admin?sec=inscricoes&erro=Nao+foi+possivel+reabrir", status_code=303
        )
    return RedirectResponse(
        "/admin?sec=inscricoes&msg=Inscricao+reaberta", status_code=303
    )


@app.post("/admin/recusar-todos")
def admin_recusar_todos(request: Request):
    if not admin_ok(request):
        return RedirectResponse("/admin/login", status_code=303)
    n = db.recusar_todos_pendentes()
    return RedirectResponse(
        f"/admin?sec=inscricoes&msg={n}+inscricao(oes)+recusada(s)",
        status_code=303,
    )


@app.post("/admin/janela")
def admin_janela(request: Request, janela: str = Form(...)):
    if not admin_ok(request):
        return RedirectResponse("/admin/login", status_code=303)
    try:
        db.set_janela(janela)
    except ValueError:
        return RedirectResponse("/admin?erro=Janela+invalida", status_code=303)
    return RedirectResponse(f"/admin?msg=Janela+{janela}", status_code=303)


@app.post("/admin/fase")
def admin_fase(request: Request, fase: str = Form(...)):
    if not admin_ok(request):
        return RedirectResponse("/admin/login", status_code=303)
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
        return RedirectResponse("/admin/login", status_code=303)
    status = "liberado" if ja_pago == "1" else "pendente"
    celular_ok = None
    if celular.strip():
        try:
            celular_ok = db.normalizar_celular(celular)
        except ValueError:
            return RedirectResponse(
                "/admin?sec=participantes&erro=Celular+invalido",
                status_code=303,
            )
    try:
        db.criar_participante(nome, status=status, celular=celular_ok)
    except Exception as exc:
        return RedirectResponse(
            f"/admin?sec=participantes&erro={exc}", status_code=303
        )
    return RedirectResponse(
        "/admin?sec=participantes&msg=Participante+criado", status_code=303
    )


@app.post("/admin/avatar-padrao")
async def admin_avatar_padrao(
    request: Request,
    avatar: UploadFile = File(...),
):
    if not admin_ok(request):
        return RedirectResponse("/admin/login", status_code=303)
    ext = Path(avatar.filename or "").suffix.lower()
    if ext not in AVATAR_EXTS:
        return RedirectResponse(
            "/admin?sec=participantes&erro=Foto+padrao+deve+ser+jpg/png/webp",
            status_code=303,
        )
    data = await avatar.read()
    if not data or len(data) > AVATAR_MAX_BYTES:
        return RedirectResponse(
            "/admin?sec=participantes&erro=Foto+padrao+invalida+ou+maior+que+3MB",
            status_code=303,
        )
    for old in STATIC.glob(f"{AVATAR_PADRAO_STEM}.*"):
        if old.is_file():
            old.unlink(missing_ok=True)
    dest = STATIC / f"{AVATAR_PADRAO_STEM}{ext}"
    dest.write_bytes(data)
    return RedirectResponse(
        "/admin?sec=participantes&msg=Foto+padrao+atualizada", status_code=303
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
        return RedirectResponse("/admin/login", status_code=303)
    part = db.get_participante(participante_id)
    if not part:
        return RedirectResponse(
            "/admin?sec=participantes&erro=Participante+nao+encontrado",
            status_code=303,
        )
    try:
        db.atualizar_nome_participante(participante_id, nome)
        db.atualizar_celular_participante(participante_id, celular)
    except ValueError as exc:
        return RedirectResponse(
            f"/admin?sec=participantes&erro={quote(str(exc))}", status_code=303
        )
    except Exception as exc:
        return RedirectResponse(
            f"/admin?sec=participantes&erro={quote(str(exc))}", status_code=303
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
                "/admin?sec=participantes&erro=Foto+deve+ser+jpg/png/webp",
                status_code=303,
            )
        data = await avatar.read()
        if not data or len(data) > AVATAR_MAX_BYTES:
            return RedirectResponse(
                "/admin?sec=participantes&erro=Foto+invalida+ou+maior+que+3MB",
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
        "/admin?sec=participantes&msg=Participante+atualizado", status_code=303
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
        return RedirectResponse("/admin/login", status_code=303)
    pen = penaltis_clube_id if penaltis_clube_id in ("a", "b") else None
    db.set_resultado_jogo(jogo_id, gols_mandante, gols_visitante, pen)
    return RedirectResponse("/admin?msg=Resultado+salvo", status_code=303)


@app.post("/admin/resultados")
async def admin_resultados(request: Request):
    if not admin_ok(request):
        return RedirectResponse("/admin/login", status_code=303)
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
        return RedirectResponse("/admin/login", status_code=303)
    hist = confirmar_rodada()
    return RedirectResponse(
        f"/admin?msg=Rodada+{hist['numero']}+confirmada+e+arquivada",
        status_code=303,
    )


@app.post("/admin/desfazer-rodada")
def admin_desfazer_rodada(request: Request):
    if not admin_ok(request):
        return RedirectResponse("/admin/login", status_code=303)
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
        return RedirectResponse("/admin/login", status_code=303)
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
