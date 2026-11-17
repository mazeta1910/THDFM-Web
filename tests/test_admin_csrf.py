"""CSRF nos POSTs do painel admin."""

from __future__ import annotations

from tests.conftest import csrf_token_for, login_admin


def test_admin_post_sem_csrf_rejeita(client):
    login_admin(client)
    # Novo client com os mesmos cookies, sem o wrapper que injeta CSRF.
    from src.app import app
    from fastapi.testclient import TestClient

    with TestClient(app) as raw:
        for k, v in client.cookies.items():
            raw.cookies.set(k, v)
        r = raw.post(
            "/admin/cobranca/email-todos",
            data={"fase": "oitavas", "perna": "ida"},
            follow_redirects=False,
        )
    assert r.status_code == 303
    loc = r.headers.get("location") or ""
    assert "erro=csrf" in loc


def test_admin_post_com_csrf_passa_pelo_middleware(client):
    login_admin(client)
    token = csrf_token_for(client)
    r = client.post(
        "/admin/cobranca/email-todos",
        data={"fase": "oitavas", "perna": "ida", "csrf_token": token},
        follow_redirects=False,
    )
    # Não é 403 CSRF — pode redirecionar com msg/erro de negócio.
    assert r.status_code == 303
    loc = r.headers.get("location") or ""
    assert "erro=csrf" not in loc


def test_admin_html_expoe_meta_csrf(client):
    login_admin(client)
    r = client.get("/admin/visao")
    assert r.status_code == 200
    assert 'name="csrf-token"' in r.text
    assert csrf_token_for(client)
