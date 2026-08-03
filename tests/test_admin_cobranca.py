"""Admin › Quem palpitou: status + WhatsApp de cobrança."""

from urllib.parse import unquote

from src import db
from src.config import TRAVA_PALPITE_ANTES_MIN
from tests.conftest import login_admin


def test_status_palpites_liberados_separa_completo_e_incompleto(client):
    ok = db.criar_participante("Ja Fez", status="liberado", celular="11990001111")
    falta = db.criar_participante("Nao Fez", status="liberado", celular="11990002222")
    parcial = db.criar_participante("Meio Fez", status="liberado", celular="11990003333")
    db.criar_participante("Pendente", status="pendente", celular="11990004444")

    confrontos = db.list_confrontos_completos("oitavas")
    assert len(confrontos) >= 2
    jogos_ida = []
    for c in confrontos:
        ida = next(j for j in c["jogos"] if j["perna"] == "ida")
        db.set_inicio_jogo(ida["id"], "2099-08-10 20:00")
        jogos_ida.append(ida)

    for jogo in jogos_ida:
        db.salvar_palpite_jogo(ok["id"], jogo["id"], 1, 0)
    db.salvar_palpite_jogo(parcial["id"], jogos_ida[0]["id"], 2, 1)

    st = db.status_palpites_liberados("oitavas", "ida", so_abertos=True, janela="ida")
    assert st["n_jogos"] == len(jogos_ida)
    ids_ok = {p["id"] for p in st["completos"]}
    ids_falta = {p["id"] for p in st["incompletos"]}
    assert ok["id"] in ids_ok
    assert falta["id"] in ids_falta
    assert parcial["id"] in ids_falta
    row_parcial = next(p for p in st["incompletos"] if p["id"] == parcial["id"])
    assert row_parcial["parcial"] is True
    assert row_parcial["n_feitos"] == 1


def test_mensagem_cobranca_menciona_trava_e_link():
    msg = db.mensagem_whatsapp_cobranca_palpite(
        "João Silva",
        "https://exemplo.test",
        "tok123",
        fase_label="Oitavas",
        perna_label="Volta",
        n_feitos=0,
        n_jogos=8,
    )
    assert "Oi, João!" in msg
    assert "Oitavas" in msg
    assert "Volta" in msg
    assert f"{TRAVA_PALPITE_ANTES_MIN} min" in msg
    assert "https://exemplo.test/p/tok123" in msg


def test_admin_cobranca_lista_e_whatsapp(client):
    falta = db.criar_participante("Falta WA", status="liberado", celular="11990005555")
    ok = db.criar_participante("Completo WA", status="liberado", celular="11990006666")
    confrontos = db.list_confrontos_completos("oitavas")
    for c in confrontos:
        ida = next(j for j in c["jogos"] if j["perna"] == "ida")
        db.set_inicio_jogo(ida["id"], "2099-08-10 20:00")
        db.salvar_palpite_jogo(ok["id"], ida["id"], 1, 0)
    db.set_janela("ida")
    db.set_fase_atual("oitavas")

    login_admin(client)
    r = client.get("/admin/cobranca?fase=oitavas&perna=ida")
    assert r.status_code == 200
    assert "Quem palpitou" in r.text
    assert "Falta WA" in r.text
    assert "Completo WA" in r.text
    assert f"/admin/cobranca/avisar/{falta['id']}" in r.text
    assert "30" in r.text

    side = client.get("/admin")
    assert side.status_code == 200
    assert 'href="/admin/cobranca"' in side.text

    wa = client.get(
        f"/admin/cobranca/avisar/{falta['id']}?fase=oitavas&perna=ida",
        follow_redirects=False,
    )
    assert wa.status_code == 303
    loc = wa.headers.get("location") or ""
    digitos = db.celular_whatsapp(falta["celular"])
    assert loc.startswith(f"https://wa.me/{digitos}")
    assert "text=" in loc
    decoded = unquote(loc)
    assert "30 min" in decoded
    assert falta["token"] in decoded
