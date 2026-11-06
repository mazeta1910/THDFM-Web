"""Gate de e-mail obrigatório + confirmação por link."""

from __future__ import annotations

from urllib.parse import unquote

from src import db
from tests.conftest import confirmar_email_teste, limpar_email_teste, login_admin


def _login_user(client, part: dict) -> None:
    client.get(f"/p/{part['token']}")


def _part_sem_email(nome: str, celular: str) -> dict:
    part = db.criar_participante(nome, status="liberado", celular=celular)
    limpar_email_teste(part["id"])
    return db.get_participante(part["id"])


def test_modal_aparece_sem_email_confirmado(client):
    part = _part_sem_email("Sem Email", "11990010001")
    db.definir_credenciais(part["id"], "sem.email", "senha12345")
    _login_user(client, part)

    r = client.get("/")
    assert r.status_code == 200
    assert 'id="email-gate-dialog"' in r.text
    assert "E-mail obrigatório" in r.text
    assert 'action="/conta/email/verificar"' in r.text


def test_modal_sumido_com_email_confirmado(client):
    part = db.criar_participante("Com Email", status="liberado", celular="11990010002")
    db.definir_credenciais(part["id"], "com.email", "senha12345")
    confirmar_email_teste(part["id"], "com.email@example.com")
    _login_user(client, part)

    r = client.get("/")
    assert r.status_code == 200
    assert 'id="email-gate-dialog"' not in r.text


def test_mutacao_bloqueada_sem_email(client):
    part = _part_sem_email("Bloqueado", "11990010003")
    db.definir_credenciais(part["id"], "bloqueado.user", "senha12345")
    _login_user(client, part)

    r = client.post(
        f"/p/{part['token']}/conta/senha",
        data={
            "senha_atual": "senha12345",
            "senha_nova": "outrasenha9",
            "senha_nova2": "outrasenha9",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "email=obrigatorio" in r.headers["location"]
    assert db.autenticar_por_username("bloqueado.user", "senha12345")


def test_verificar_envia_token_e_confirma(client):
    part = _part_sem_email("Verify Me", "11990010004")
    db.definir_credenciais(part["id"], "verify.me", "senha12345")
    _login_user(client, part)

    r = client.post(
        "/conta/email/verificar",
        data={"email": "verify.me@example.com", "next": "/"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    loc = unquote(r.headers["location"])
    assert "email_msg=" in loc
    assert "email=obrigatorio" in loc

    part2 = db.get_participante(part["id"])
    assert part2["email"] == "verify.me@example.com"
    assert not part2.get("email_confirmado_em")
    assert not db.email_esta_confirmado(part2)

    with db.get_db() as conn:
        row = conn.execute(
            "SELECT token FROM email_verify_tokens WHERE participante_id = ? "
            "AND usado_em IS NULL ORDER BY criado_em DESC LIMIT 1",
            (part["id"],),
        ).fetchone()
    assert row
    token = row["token"]

    r2 = client.get(f"/confirmar-email/{token}", follow_redirects=False)
    assert r2.status_code == 303
    loc = unquote(r2.headers["location"])
    assert "E-mail confirmado" in loc or "email confirmado" in loc.casefold()
    assert db.email_esta_confirmado(db.get_participante(part["id"]))

    r3 = client.get(f"/p/{part['token']}")
    assert r3.status_code == 200
    assert 'id="email-gate-dialog"' not in r3.text


def test_reenviar_link(client):
    part = _part_sem_email("Resend Me", "11990010005")
    db.definir_credenciais(part["id"], "resend.me", "senha12345")
    _login_user(client, part)
    updated, token1 = db.solicitar_verificacao_email(part["id"], "resend.me@example.com")
    assert updated["email"] == "resend.me@example.com"

    r = client.post(
        "/conta/email/reenviar",
        data={"next": "/"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "email_msg=" in unquote(r.headers["location"])

    with db.get_db() as conn:
        rows = conn.execute(
            "SELECT token, usado_em FROM email_verify_tokens WHERE participante_id = ? "
            "ORDER BY criado_em",
            (part["id"],),
        ).fetchall()
    assert len(rows) >= 2
    # token antigo invalidado
    old = next(r for r in rows if r["token"] == token1)
    assert old["usado_em"]
    fresh = [r for r in rows if r["usado_em"] is None]
    assert len(fresh) == 1


def test_token_invalido(client):
    r = client.get("/confirmar-email/token-que-nao-existe")
    assert r.status_code == 200
    assert "Não foi possível confirmar" in r.text


def test_conta_email_nao_confirma_no_ato(client):
    part = _part_sem_email("Conta Email", "11990010006")
    db.definir_credenciais(part["id"], "conta.email", "senha12345")
    _login_user(client, part)

    r = client.post(
        f"/p/{part['token']}/conta/email",
        data={"email": "conta.email@example.com", "next": "/"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "confirmação" in unquote(r.headers["location"]).casefold() or "msg=" in r.headers[
        "location"
    ]
    part2 = db.get_participante(part["id"])
    assert part2["email"] == "conta.email@example.com"
    assert not db.email_esta_confirmado(part2)


def test_admin_com_email_confirma_pode_postar(client):
    login_admin(client)
    r = client.post(
        "/admin/permissoes",
        data={
            "admin_login": "mazeta",
            "cap_bolao.resultados": "1",
            "cap_bolao.inscricoes": "1",
            "cap_listra.gestir": "1",
            "cap_xonhometro.gestir": "1",
            "cap_acervo.gestir": "1",
        },
        follow_redirects=False,
    )
    # Sem gate: 303; com gate quebrado seria email=obrigatorio
    assert r.status_code == 303
    assert "email=obrigatorio" not in r.headers.get("location", "")
