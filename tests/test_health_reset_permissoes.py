"""Healthcheck, reset de senha e capabilities admin."""

from __future__ import annotations

from urllib.parse import unquote

from src import db
from tests.conftest import login_admin


def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["db"] is True


def test_em_desenvolvimento_publico(client):
    r = client.get("/em-desenvolvimento")
    assert r.status_code == 200
    assert "Público" in r.text
    assert "Grupo do WhatsApp" in r.text


def test_reset_senha_por_email(client):
    part = db.criar_participante("Reset Fan", status="liberado", celular="11990001111")
    db.definir_credenciais(part["id"], "reset.fan", "senhaantiga1")
    db.definir_email_participante(part["id"], "reset.fan@example.com")

    r = client.post("/esqueci-senha", data={"usuario": "reset.fan"}, follow_redirects=False)
    assert r.status_code == 303
    assert "enviamos" in unquote(r.headers["location"]).casefold() or "msg=" in r.headers["location"]

    with db.get_db() as conn:
        row = conn.execute(
            "SELECT token FROM senha_reset_tokens WHERE participante_id = ? "
            "AND usado_em IS NULL ORDER BY criado_em DESC LIMIT 1",
            (part["id"],),
        ).fetchone()
    assert row
    token = row["token"]

    r2 = client.post(
        f"/redefinir-senha/{token}",
        data={"senha_nova": "senhanova99", "senha_nova2": "senhanova99"},
        follow_redirects=False,
    )
    assert r2.status_code == 303
    assert db.autenticar_por_username("reset.fan", "senhanova99")
    assert db.autenticar_por_username("reset.fan", "senhaantiga1") is None


def test_admin_permissoes_concede_acervo(client, monkeypatch):
    monkeypatch.setenv(
        "ADMIN_USERS",
        "mazeta=senha-dono=Mazeta:dono|ramos=senha-mod=Ramos:moderador",
    )
    login_admin(client)
    # Antes: moderador sem acervo (só defaults)
    assert not db.admin_tem_capability("ramos", "acervo.gestir")
    r = client.post(
        "/admin/permissoes",
        data={
            "admin_login": "ramos",
            "cap_acervo.gestir": "1",
            "cap_bolao.resultados": "1",
            "cap_bolao.inscricoes": "1",
            "cap_listra.gestir": "1",
            "cap_xonhometro.gestir": "1",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert db.admin_tem_capability("ramos", "acervo.gestir")
    assert db.admin_tem_capability("ramos", "bolao.resultados")


def test_dono_tem_todas_capabilities(client):
    caps = db.admin_capabilities("mazeta")
    assert "usuarios.permissoes" in caps
    assert "acervo.gestir" in caps
    assert "grid.bugs" in caps
