"""Lembretes automáticos de palpites: faixas 14d / 7d / 24h + job cron."""

from datetime import datetime, timedelta
from urllib.parse import unquote

from src import db
from src.config import _TZ_SP
from src.lembrete_palpites import marco_na_banda, prazo_mais_proximo, rodar_job
from tests.conftest import login_admin


def _ida_jogos_em(inicio: str) -> list:
    confrontos = db.list_confrontos_completos("oitavas")
    jogos = []
    for c in confrontos:
        ida = next(j for j in c["jogos"] if j["perna"] == "ida")
        db.set_inicio_jogo(ida["id"], inicio)
        jogos.append(ida)
    return jogos


def test_marco_na_banda_faixas():
    prazo = datetime(2026, 9, 20, 20, 0, tzinfo=_TZ_SP)
    assert marco_na_banda(prazo, agora=prazo - timedelta(days=10)) == "14d"
    assert marco_na_banda(prazo, agora=prazo - timedelta(days=5)) == "7d"
    assert marco_na_banda(prazo, agora=prazo - timedelta(hours=12)) == "24h"
    assert marco_na_banda(prazo, agora=prazo - timedelta(days=20)) is None
    assert marco_na_banda(prazo, agora=prazo + timedelta(hours=1)) is None


def test_prazo_mais_proximo():
    jogos = [
        {"inicio_em": "2026-09-22 21:00"},
        {"inicio_em": "2026-09-20 19:30"},
        {"inicio_em": "lixo"},
    ]
    p = prazo_mais_proximo(jogos)
    assert p is not None
    assert p.day == 20


def test_job_envia_so_na_faixa_e_nao_repete(client, monkeypatch):
    falta = db.criar_participante("Sem Palpite", status="liberado", celular="11990001111")
    db.definir_email_participante(falta["id"], "sem@thdfm.test")
    ok = db.criar_participante("Ja Palpitou", status="liberado", celular="11990002222")
    db.definir_email_participante(ok["id"], "ok@thdfm.test")

    prazo = datetime(2026, 9, 20, 20, 0, tzinfo=_TZ_SP)
    jogos = _ida_jogos_em(prazo.strftime("%Y-%m-%d %H:%M"))
    for j in jogos:
        db.salvar_palpite_jogo(ok["id"], j["id"], 1, 0)

    enviados: list[dict] = []

    def fake_enviar(*, para, assunto, texto):
        enviados.append({"para": para, "assunto": assunto, "texto": texto})
        return True

    agora_14 = prazo - timedelta(days=10)
    r1 = rodar_job(
        base_url="https://thdfm.test",
        agora=agora_14,
        fase="oitavas",
        perna="ida",
        enviar=fake_enviar,
    )
    assert r1["enviados"] == 1
    assert enviados[0]["para"] == "sem@thdfm.test"
    assert "14 dias" in enviados[0]["assunto"] or "14" in enviados[0]["assunto"]
    assert db.lembrete_palpites_ja_enviado(falta["id"], "oitavas", "ida", "14d")

    # Mesma faixa: não reenvia
    enviados.clear()
    r2 = rodar_job(
        base_url="https://thdfm.test",
        agora=agora_14,
        fase="oitavas",
        perna="ida",
        enviar=fake_enviar,
    )
    assert r2["enviados"] == 0
    assert enviados == []

    # Entra na faixa 7d
    agora_7 = prazo - timedelta(days=5)
    r3 = rodar_job(
        base_url="https://thdfm.test",
        agora=agora_7,
        fase="oitavas",
        perna="ida",
        enviar=fake_enviar,
    )
    assert r3["enviados"] == 1
    assert "7 dias" in enviados[0]["assunto"] or "7" in enviados[0]["assunto"]


def test_job_nao_flood_fora_de_faixa(client):
    falta = db.criar_participante("Longe", status="liberado", celular="11990003333")
    db.definir_email_participante(falta["id"], "longe@thdfm.test")
    prazo = datetime(2026, 9, 20, 20, 0, tzinfo=_TZ_SP)
    _ida_jogos_em(prazo.strftime("%Y-%m-%d %H:%M"))

    enviados: list = []

    def fake_enviar(*, para, assunto, texto):
        enviados.append(para)
        return True

    # 20 dias antes: fora de todas as faixas
    r = rodar_job(
        base_url="https://thdfm.test",
        agora=prazo - timedelta(days=20),
        fase="oitavas",
        perna="ida",
        enviar=fake_enviar,
    )
    assert r["enviados"] == 0
    assert enviados == []


def test_cron_endpoint_exige_segredo(client, monkeypatch):
    monkeypatch.delenv("CRON_SECRET", raising=False)
    r = client.get("/internal/jobs/lembrete-palpites")
    assert r.status_code == 503

    monkeypatch.setenv("CRON_SECRET", "segredo-teste")
    r2 = client.get("/internal/jobs/lembrete-palpites")
    assert r2.status_code == 401

    r3 = client.get(
        "/internal/jobs/lembrete-palpites",
        headers={"X-Cron-Secret": "segredo-teste"},
    )
    assert r3.status_code == 200
    body = r3.json()
    assert body.get("ok") is True


def test_admin_email_todos_manual(client, monkeypatch):
    login_admin(client)
    falta = db.criar_participante("Manual Mail", status="liberado", celular="11990004444")
    db.definir_email_participante(falta["id"], "manual@thdfm.test")
    prazo = datetime.now(_TZ_SP) + timedelta(days=3)
    _ida_jogos_em(prazo.strftime("%Y-%m-%d %H:%M"))

    enviados: list = []

    def fake_enviar(*, para, assunto, texto):
        enviados.append(para)
        return True

    monkeypatch.setattr("src.mail.enviar_email", fake_enviar)
    monkeypatch.setattr("src.lembrete_palpites.enviar_email", fake_enviar)

    r = client.post(
        "/admin/cobranca/email-todos",
        data={"fase": "oitavas", "perna": "ida"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    loc = unquote(r.headers.get("location") or "")
    assert "E-mails:" in loc
    assert "manual@thdfm.test" in enviados or enviados  # pelo menos 1 tentativa
    assert db.lembrete_palpites_ja_enviado(falta["id"], "oitavas", "ida", "manual")


def test_admin_cobranca_mostra_botao_email(client):
    login_admin(client)
    falta = db.criar_participante("UI Mail", status="liberado", celular="11990005555")
    db.definir_email_participante(falta["id"], "ui@thdfm.test")
    prazo = datetime.now(_TZ_SP) + timedelta(days=10)
    _ida_jogos_em(prazo.strftime("%Y-%m-%d %H:%M"))

    r = client.get("/admin/cobranca?fase=oitavas&perna=ida")
    assert r.status_code == 200
    assert 'action="/admin/cobranca/email-todos"' in r.text
    assert ">E-mail</button>" in r.text
    assert 'id="modal-email-lote"' in r.text
    assert "Nenhum e-mail em lote registrado" in r.text or "Último e-mail em lote" in r.text
    assert "14 dias" in r.text
