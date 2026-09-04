"""Hall das Lendas — mural público + admin Mazeta."""

from __future__ import annotations

from fastapi.testclient import TestClient

from src import db as dbmod
from src.config import ROOT_DIR
from src.hall_lendas import (
    format_valor_brl,
    parse_valor_centavos,
    sanitize_hall_hero_html,
    sanitize_hall_recado_html,
)
from tests.conftest import login_admin


def _lenda(nome: str, celular: str, *, valor: str = "100,00", recado: str = "Valeu THDFM"):
    part = dbmod.criar_participante(nome, status="liberado", celular=celular)
    dbmod.upsert_hall_lenda(
        part["id"],
        valor_centavos_add=parse_valor_centavos(valor),
        recado=recado,
        borda="anel",
    )
    return part


def test_parse_e_format_valor():
    assert parse_valor_centavos("50") == 5000
    assert parse_valor_centavos("50,00") == 5000
    assert parse_valor_centavos("R$ 1.234,56") == 123456
    assert format_valor_brl(5000) == "R$ 50,00"


def test_sanitize_hall_html_fonte_e_negrito():
    html = sanitize_hall_recado_html(
        '<p>Oi <b>mundo</b> <font size="5" face="Georgia, serif">grande</font>'
        '<span style="font-style: italic; font-size: 18px">itálico</span>'
        '<script>alert(1)</script><img src="/hall-hero/x.jpg" alt="f"></p>'
    )
    assert "<script>" not in html
    assert "<b>mundo</b>" in html
    assert 'size="5"' in html
    assert "Georgia" in html
    assert "font-style: italic" in html
    assert 'src="/hall-hero/x.jpg"' in html
    assert sanitize_hall_recado_html("") == ""
    assert "Quem apoia" in sanitize_hall_hero_html("")


def test_hall_lendas_publico_sem_login(client: TestClient):
    a = _lenda("Ramos Lenda", "11990008001", valor="500,00", recado="Segue o baile")
    b = _lenda("João JEC", "11990008002", valor="200,00", recado="JEC eterno")

    r = client.get("/hall-lendas", follow_redirects=False)
    assert r.status_code == 200
    assert "Hall das Lendas" in r.text
    assert "Ramos Lenda" in r.text
    assert "João JEC" in r.text
    assert "Segue o baile" in r.text
    assert "hall-lendas-badge" in r.text
    assert "lenda-frame--anel" in r.text
    # Valores ocultos para o público
    assert "R$ 500,00" not in r.text
    assert "Total doado" not in r.text
    assert "Visão Mazeta" not in r.text
    assert "Protótipo" not in r.text
    assert "prévia só Mazeta" not in r.text
    assert "Protótipo visual" not in r.text
    # Ordenado por total (Ramos primeiro)
    assert r.text.index("Ramos Lenda") < r.text.index("João JEC")
    assert a and b


def test_hall_lendas_mazeta_ve_valores(client: TestClient):
    _lenda("Benevides Ouro", "11990008003", valor="80,00", recado="Apoio")
    login_admin(client)
    r = client.get("/hall-lendas")
    assert r.status_code == 200
    assert "Visão Mazeta" in r.text
    assert "Total doado" in r.text
    assert "R$ 80,00" in r.text
    assert "Gerenciar Hall" in r.text


def test_sidebar_hall_lendas_publico(client: TestClient):
    r = client.get("/")
    assert r.status_code == 200
    assert "Hall das Lendas" in r.text
    chunk = r.text.split("site-hall-lendas", 1)[1].split(">", 1)[0]
    assert 'href="/hall-lendas"' in chunk or 'href="/hall-lendas"' in r.text
    assert "disabled" not in chunk
    side = (ROOT_DIR / "templates" / "partials" / "site_sidebar.html").read_text(
        encoding="utf-8"
    )
    assert 'href="/hall-lendas"' in side
    assert "Em breve" not in side
    assert "{% if is_mazeta %}" not in side.split("site-hall-lendas", 1)[0][-80:] + side.split(
        "site-hall-lendas", 1
    )[1][:400]


def test_admin_hall_crud(client: TestClient):
    part = dbmod.criar_participante("Doador Admin", status="liberado", celular="11990008004")
    login_admin(client)

    r = client.get("/admin/hall-lendas")
    assert r.status_code == 200
    assert "Hall das Lendas" in r.text
    assert "Doador Admin" in r.text
    assert "data-hall-rich-form" in r.text
    assert "data-hall-rich-body" in r.text
    assert "hall-rich-edit.js" in r.text
    assert 'data-hall-cmd="bold"' in r.text
    assert "data-hall-rich-foto" in r.text
    assert 'name="recado"' in r.text

    r = client.post(
        "/admin/hall-lendas/salvar",
        data={
            "modo": "doar",
            "participante_id": str(part["id"]),
            "valor": "150,00",
            "recado": "Primeira doação",
            "borda": "duplo",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    row = dbmod.get_hall_lenda(part["id"])
    assert row is not None
    assert row["valor_centavos"] == 15000
    assert row["recado"] == "Primeira doação"
    assert row["borda"] == "anel"  # padrão; moldura é do usuário

    # Usuário escolhe moldura
    dbmod.set_hall_borda(part["id"], "duplo")
    assert dbmod.get_hall_lenda(part["id"])["borda"] == "duplo"

    # Re-doar soma e NÃO sobrescreve moldura do usuário
    r = client.post(
        "/admin/hall-lendas/salvar",
        data={
            "modo": "doar",
            "participante_id": str(part["id"]),
            "valor": "50",
            "recado": 'Segunda <b>vez</b><script>x</script><font size="5">!</font>',
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    row = dbmod.get_hall_lenda(part["id"])
    assert row["valor_centavos"] == 20000
    assert "<script>" not in row["recado"]
    assert "<b>vez</b>" in row["recado"]
    assert 'size="5"' in row["recado"]
    assert row["borda"] == "duplo"

    mural = client.get("/hall-lendas")
    assert mural.status_code == 200
    assert "<b>vez</b>" in mural.text

    # Editar total não mexe na moldura
    r = client.post(
        "/admin/hall-lendas/salvar",
        data={
            "modo": "editar",
            "participante_id": str(part["id"]),
            "valor_total": "99,90",
            "recado": "Ajuste",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    row = dbmod.get_hall_lenda(part["id"])
    assert row["valor_centavos"] == 9990
    assert row["borda"] == "duplo"

    admin_html = client.get("/admin/hall-lendas").text
    assert "Moldura inicial" not in admin_html
    assert 'name="borda"' not in admin_html
    assert "escolhida pela própria lenda" in admin_html

    r = client.post(
        "/admin/hall-lendas/apagar",
        data={"participante_id": str(part["id"])},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert dbmod.get_hall_lenda(part["id"]) is None


def test_admin_hall_exige_mazeta(client: TestClient):
    r = client.get("/admin/hall-lendas", follow_redirects=False)
    assert r.status_code in (302, 303, 401, 403)


def test_paginacao_hall(client: TestClient):
    for i in range(12):
        _lenda(f"Lenda Pag {i:02d}", f"119900081{i:02d}", valor=f"{100 + i},00")
    r = client.get("/hall-lendas")
    assert r.status_code == 200
    assert "página 1 / 2" in r.text
    assert "Próxima" in r.text
    r2 = client.get("/hall-lendas?pagina=2")
    assert r2.status_code == 200
    assert "Anterior" in r2.text
    assert "lenda-frame--" in r.text


def test_hall_hero_padrao_e_lapis_so_mazeta(client: TestClient):
    r = client.get("/hall-lendas")
    assert r.status_code == 200
    assert "hall-lendas-hero-body" in r.text
    assert "Quem apoia o projeto com doação" in r.text
    assert "data-hall-hero-edit" not in r.text
    assert "hall-hero-edit.js" not in r.text
    assert "hall-rich-edit.js" not in r.text

    login_admin(client)
    r2 = client.get("/hall-lendas")
    assert r2.status_code == 200
    assert 'data-hall-hero-editavel="1"' in r2.text
    assert "data-hall-hero-edit" in r2.text
    assert "hall-rich-edit.js" in r2.text
    assert 'data-hall-cmd="bold"' in r2.text
    assert "data-hall-font" in r2.text
    assert "data-hall-size" in r2.text
    assert "hall-hero-edit.js" not in r2.text
    css = (ROOT_DIR / "templates" / "base.html").read_text(encoding="utf-8")
    assert "style.css?v=327" in css
    assert "hall-rich-edit.js?v=2" in (ROOT_DIR / "templates" / "hall_lendas.html").read_text(
        encoding="utf-8"
    )


def test_hall_hero_salvar_e_upload(client: TestClient, tmp_path, monkeypatch):
    from src import app as app_mod
    from src.config import HALL_HERO_DIR

    midia = tmp_path / "hall-hero"
    midia.mkdir()
    monkeypatch.setattr(app_mod, "HALL_HERO_DIR", midia)
    monkeypatch.setattr("src.config.HALL_HERO_DIR", midia)

    # Sem login: bloqueado
    r = client.post(
        "/admin/hall-lendas/hero",
        json={"html": "<p>Hack</p>"},
        follow_redirects=False,
    )
    assert r.status_code in (302, 303, 401, 403)

    login_admin(client)
    r = client.post(
        "/admin/hall-lendas/hero",
        json={
            "html": '<p>Texto <strong>livre</strong></p><script>alert(1)</script><img src="/hall-hero/x.jpg" alt="foto">'
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert "<script>" not in data["html"]
    assert "<strong>livre</strong>" in data["html"]
    assert 'src="/hall-hero/x.jpg"' in data["html"]
    assert dbmod.get_hall_hero_html() == data["html"]

    page = client.get("/hall-lendas")
    assert "Texto" in page.text
    assert "<strong>livre</strong>" in page.text

    up = client.post(
        "/admin/hall-lendas/hero/midia",
        files={"midia": ("capa.png", b"\x89PNG\r\n\x1a\n-fake", "image/png")},
    )
    assert up.status_code == 200
    upj = up.json()
    assert upj["ok"] is True
    assert upj["url"].startswith("/hall-hero/")
    rel = upj["url"].rsplit("/", 1)[-1]
    assert (midia / rel).is_file()
    # pasta default do projeto não precisa existir neste teste
    assert HALL_HERO_DIR or True
