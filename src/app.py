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
from src.admins import autenticar_admin
from src.config import (
    AVATAR_EXTS,
    AVATAR_MAX_BYTES,
    AVATARES_DIR,
    COMPROVANTE_EXTS,
    COMPROVANTE_MAX_BYTES,
    COMPROVANTES_DIR,
    EMBLEMAS_DIR,
    JANELAS,
    ROOT_DIR,
    SECRET_KEY,
    TAXA_PIX,
    TAXA_VALOR_LABEL,
)
from src.ranking import calcular_classificacao, snapshot_atual
from src.scoring import agregado_empatado
from src.seed_data import emblema_url

load_dotenv(ROOT_DIR / ".env")

app = FastAPI(title="Bolão THDFM — Copa do Brasil")
app.add_middleware(SessionMiddleware, secret_key=os.environ.get("SECRET_KEY", SECRET_KEY))

TEMPLATES = Jinja2Templates(directory=str(ROOT_DIR / "templates"))
TEMPLATES.env.globals["emblema_url"] = emblema_url

STATIC = ROOT_DIR / "static"
STATIC.mkdir(exist_ok=True)
EMBLEMAS_DIR.mkdir(parents=True, exist_ok=True)
COMPROVANTES_DIR.mkdir(parents=True, exist_ok=True)
AVATARES_DIR.mkdir(parents=True, exist_ok=True)

app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")
app.mount("/emblemas", StaticFiles(directory=str(EMBLEMAS_DIR)), name="emblemas")
app.mount("/avatars", StaticFiles(directory=str(AVATARES_DIR)), name="avatars")


@app.on_event("startup")
def _startup() -> None:
    db.init_db()


def admin_ok(request: Request) -> bool:
    return bool(request.session.get("admin_login"))


def admin_nome(request: Request) -> str:
    return request.session.get("admin_nome") or request.session.get("admin_login") or ""


def render(request: Request, name: str, **ctx):
    token = request.session.get("participante_token")
    part_nav = db.get_participante_por_token(token) if token else None
    ctx.setdefault("is_admin", admin_ok(request))
    ctx.setdefault("admin_nome", admin_nome(request))
    ctx.setdefault("participante_nav", part_nav)
    return TEMPLATES.TemplateResponse(request, name, ctx)


def _remember_participante(request: Request, token: str) -> None:
    request.session["participante_token"] = token


def _enrich_confrontos(confrontos: list) -> list:
    for c in confrontos:
        c["ida"] = next((j for j in c["jogos"] if j["perna"] == "ida"), None)
        c["volta"] = next((j for j in c["jogos"] if j["perna"] == "volta"), None)
    return confrontos


def _taxa_ctx() -> dict:
    return {
        "taxa_pix": os.environ.get("TAXA_PIX", TAXA_PIX),
        "taxa_valor_label": os.environ.get("TAXA_VALOR_LABEL", TAXA_VALOR_LABEL),
    }


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return render(request, "home.html", janela=db.get_janela(), **_taxa_ctx())


@app.get("/regras", response_class=HTMLResponse)
def regras(request: Request):
    return render(request, "regras.html", **_taxa_ctx())


@app.get("/classificacao", response_class=HTMLResponse)
def classificacao(request: Request):
    if not admin_ok(request) and not request.session.get("participante_token"):
        return RedirectResponse("/inscricao", status_code=303)
    return render(
        request,
        "classificacao.html",
        linhas=calcular_classificacao(),
        janela=db.get_janela(),
        fase=db.get_meta("fase_atual", "oitavas"),
    )


@app.get("/inscricao", response_class=HTMLResponse)
def inscricao_get(request: Request):
    return render(
        request,
        "inscricao.html",
        msg=request.query_params.get("msg"),
        erro=request.query_params.get("erro"),
        **_taxa_ctx(),
    )


@app.post("/inscricao")
async def inscricao_post(
    request: Request,
    nome: str = Form(...),
    comprovante: UploadFile = File(...),
):
    nome = nome.strip()
    if not nome:
        return RedirectResponse("/inscricao?erro=Informe+seu+nome", status_code=303)

    filename = comprovante.filename or ""
    ext = Path(filename).suffix.lower()
    if ext not in COMPROVANTE_EXTS:
        return RedirectResponse(
            "/inscricao?erro=Envie+jpg,+png,+webp+ou+pdf",
            status_code=303,
        )

    data = await comprovante.read()
    if not data:
        return RedirectResponse("/inscricao?erro=Arquivo+vazio", status_code=303)
    if len(data) > COMPROVANTE_MAX_BYTES:
        return RedirectResponse("/inscricao?erro=Arquivo+maior+que+5MB", status_code=303)

    try:
        part = db.criar_participante(nome, status="pendente")
    except Exception:
        return RedirectResponse(
            "/inscricao?erro=Nome+ja+cadastrado.+Use+seu+link+ou+fale+com+o+admin",
            status_code=303,
        )

    safe = re.sub(r"[^a-zA-Z0-9_-]+", "", nome)[:40] or "user"
    rel = f"{part['id']}_{int(time.time())}_{safe}{ext}"
    dest = COMPROVANTES_DIR / rel
    dest.write_bytes(data)
    db.salvar_comprovante(part["id"], rel)

    return RedirectResponse(
        f"/p/{part['token']}?msg=Comprovante+enviado.+Aguarde+liberacao",
        status_code=303,
    )


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
    return render(
        request,
        "palpites.html",
        participante=part,
        janela=db.get_janela(),
        confrontos=_enrich_confrontos(db.list_confrontos_completos()),
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
    return RedirectResponse("/", status_code=303)


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
    return RedirectResponse("/admin", status_code=303)


@app.get("/admin/logout")
@app.post("/admin/logout")
def admin_logout(request: Request):
    request.session.pop("admin_login", None)
    request.session.pop("admin_nome", None)
    request.session.pop("admin", None)
    return RedirectResponse("/", status_code=303)


@app.get("/admin", response_class=HTMLResponse)
def admin_home(request: Request):
    if not admin_ok(request):
        return RedirectResponse("/admin/login", status_code=303)
    return render(
        request,
        "admin.html",
        janela=db.get_janela(),
        janelas=JANELAS,
        confrontos=_enrich_confrontos(db.list_confrontos_completos()),
        participantes=db.list_participantes(),
        msg=request.query_params.get("msg"),
        erro=request.query_params.get("erro"),
        base_url=str(request.base_url).rstrip("/"),
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


@app.post("/admin/liberar")
def admin_liberar(request: Request, participante_id: int = Form(...)):
    if not admin_ok(request):
        return RedirectResponse("/admin/login", status_code=303)
    db.liberar_participante(participante_id)
    return RedirectResponse("/admin?msg=Inscricao+liberada", status_code=303)


@app.post("/admin/recusar")
def admin_recusar(request: Request, participante_id: int = Form(...)):
    if not admin_ok(request):
        return RedirectResponse("/admin/login", status_code=303)
    old = db.recusar_comprovante(participante_id)
    if old:
        path = COMPROVANTES_DIR / old
        if path.is_file():
            path.unlink(missing_ok=True)
    return RedirectResponse("/admin?msg=Comprovante+recusado", status_code=303)


@app.post("/admin/janela")
def admin_janela(request: Request, janela: str = Form(...)):
    if not admin_ok(request):
        return RedirectResponse("/admin/login", status_code=303)
    try:
        db.set_janela(janela)
    except ValueError:
        return RedirectResponse("/admin?erro=Janela+invalida", status_code=303)
    return RedirectResponse(f"/admin?msg=Janela+{janela}", status_code=303)


@app.post("/admin/participante")
def admin_participante(
    request: Request,
    nome: str = Form(...),
    ja_pago: str = Form(""),
):
    if not admin_ok(request):
        return RedirectResponse("/admin/login", status_code=303)
    status = "liberado" if ja_pago == "1" else "pendente"
    try:
        db.criar_participante(nome, status=status)
    except Exception as exc:
        return RedirectResponse(f"/admin?erro={exc}", status_code=303)
    return RedirectResponse("/admin?msg=Participante+criado", status_code=303)


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


@app.post("/admin/confirmar-rodada")
def admin_confirmar_rodada(request: Request):
    if not admin_ok(request):
        return RedirectResponse("/admin/login", status_code=303)
    db.save_snapshot(snapshot_atual())
    return RedirectResponse("/admin?msg=Rodada+confirmada", status_code=303)
