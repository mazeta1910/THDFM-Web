"""Reports de bugs do Grid — usuário envia; Mazeta responde no admin."""

from __future__ import annotations

from fastapi.testclient import TestClient

from src import db as dbmod
from src.config import ROOT_DIR
from tests.conftest import login_admin


def _user(client: TestClient, nome: str = "Bug Reporter", cel: str = "11991113301"):
    part = dbmod.criar_participante(nome, status="liberado", celular=cel)
    dbmod.definir_credenciais(part["id"], f"user.{part['id']}", "senha12345")
    client.get(f"/p/{part['token']}")
    return part


def test_botao_reportar_bugs_no_grid(client: TestClient):
    _user(client)
    r = client.get("/grid")
    assert r.status_code == 200
    assert 'href="/grid/bugs"' in r.text
    assert "Reportar Bugs" in r.text
    assert "grid-report-btn" in r.text
    assert "grid-head-title-row" in r.text
    css = (ROOT_DIR / "static" / "style.css").read_text(encoding="utf-8")
    assert ".grid-report-btn" in css
    assert "background: #c92a2a" in css
    assert ".grid-head-title-row" in css
    # Mobile: compacto ao lado do título (não full-width)
    mobile = css.split("@media (max-width: 720px)", 1)[1]
    report_mobile = mobile.split(".grid-report-btn", 1)[1].split("}", 1)[0]
    assert "width: auto" in report_mobile
    assert "width: 100%" not in report_mobile
    assert "font-size: 0.66rem" in report_mobile


def test_grid_bugs_fluxo_usuario_e_admin(client: TestClient):
    part = _user(client)

    page = client.get("/grid/bugs")
    assert page.status_code == 200
    assert "Reportar Bugs" in page.text
    assert "Seus reports" in page.text
    assert "data-grid-bugs-form" in page.text

    envio = client.post(
        "/grid/bugs",
        data={
            "titulo": "Célula travada",
            "mensagem": "Não consigo chutar no mobile.",
        },
        files={"imagem": ("print.png", b"\x89PNG\r\n\x1a\n-fake", "image/png")},
        follow_redirects=False,
    )
    assert envio.status_code == 303
    assert "Bug%20reportado" in (envio.headers.get("location") or "")

    meus = dbmod.listar_bug_reports_usuario(part["id"])
    assert len(meus) == 1
    assert meus[0]["titulo"] == "Célula travada"
    assert meus[0]["status"] == "aberto"
    assert meus[0]["imagem_path"]
    rid = meus[0]["id"]

    # Participante comum não acessa admin reports
    neg = client.get("/admin/reports", follow_redirects=False)
    assert neg.status_code in (303, 302)

    login_admin(client)
    admin_page = client.get("/admin/reports")
    assert admin_page.status_code == 200
    assert "Célula travada" in admin_page.text
    assert 'href="/admin/reports"' in admin_page.text
    assert "Reports" in admin_page.text
    side = (ROOT_DIR / "templates" / "partials" / "admin_sidebar.html").read_text(
        encoding="utf-8"
    )
    assert 'href="/admin/reports"' in side
    assert "{% if is_mazeta %}" in side

    upd = client.post(
        f"/admin/reports/{rid}",
        data={
            "status": "em_analise",
            "resposta": "Estamos olhando isso no layout mobile.",
        },
        follow_redirects=False,
    )
    assert upd.status_code == 303

    rep = dbmod.get_bug_report(rid)
    assert rep is not None
    assert rep["status"] == "em_analise"
    assert "layout mobile" in rep["resposta"]
    assert rep["usuario_leu_resposta"] is False
    assert dbmod.contar_bug_reports_nao_lidos(part["id"]) == 1

    # Sai do admin para simular o jogador (sessão admin sobrescreve o part_nav)
    client.get("/admin/logout", follow_redirects=False)
    client.get(f"/p/{part['token']}")
    assert dbmod.contar_bug_reports_nao_lidos(part["id"]) == 1
    grid = client.get("/grid")
    assert "grid-report-badge" in grid.text

    bugs = client.get("/grid/bugs")
    assert bugs.status_code == 200
    assert "Em Análise" in bugs.text
    assert "Estamos olhando isso no layout mobile." in bugs.text
    assert "Resposta da equipe" in bugs.text
    assert dbmod.contar_bug_reports_nao_lidos(part["id"]) == 0

    login_admin(client)
    done = client.post(
        f"/admin/reports/{rid}",
        data={"status": "resolvido", "resposta": "Corrigido no mobile fit."},
        follow_redirects=False,
    )
    assert done.status_code == 303
    assert dbmod.get_bug_report(rid)["status"] == "resolvido"


def test_admin_reports_exige_login(client: TestClient):
    r = client.get("/admin/reports", follow_redirects=False)
    assert r.status_code in (302, 303, 401, 403)


def test_admin_reports_bloqueia_moderador(client: TestClient, monkeypatch):
    monkeypatch.setenv(
        "ADMIN_USERS",
        "mazeta=senha-dono=Mazeta:dono|ramos=senha-mod=Ramos:moderador",
    )
    r = client.post(
        "/admin/login",
        data={"login": "ramos", "password": "senha-mod"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    denied = client.get("/admin/reports", follow_redirects=False)
    assert denied.status_code in (303, 302)
    assert "/admin" in (denied.headers.get("location") or "")
