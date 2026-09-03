"""Participantes inativos: fora da classificação e do badge Quem palpitou."""

from src import db
from src.ranking import calcular_classificacao
from tests.conftest import login_admin


def test_inativar_remove_da_cobranca_e_classificacao(client):
    ativo = db.criar_participante("Ativo Bolao", status="liberado", celular="11990001111")
    sai = db.criar_participante("Saiu Bolao", status="liberado", celular="11990002222")

    confrontos = db.list_confrontos_completos("oitavas")
    jogos_ida = []
    for c in confrontos:
        ida = next(j for j in c["jogos"] if j["perna"] == "ida")
        db.set_inicio_jogo(ida["id"], "2099-08-10 20:00")
        jogos_ida.append(ida)

    st_antes = db.status_palpites_liberados("oitavas", "ida", so_abertos=True, janela="ida")
    ids_antes = {p["id"] for p in st_antes["incompletos"]} | {p["id"] for p in st_antes["completos"]}
    assert sai["id"] in ids_antes
    assert ativo["id"] in ids_antes

    assert db.inativar_participante(sai["id"]) is True
    part = db.get_participante(sai["id"])
    assert part["status"] == "liberado"
    assert (part.get("inativo_em") or "").strip()
    assert db.participante_ativo_no_bolao(part) is False

    st = db.status_palpites_liberados("oitavas", "ida", so_abertos=True, janela="ida")
    ids = {p["id"] for p in st["incompletos"]} | {p["id"] for p in st["completos"]}
    assert sai["id"] not in ids
    assert ativo["id"] in ids

    classif_ids = {r["participante_id"] for r in calcular_classificacao()}
    assert sai["id"] not in classif_ids
    assert ativo["id"] in classif_ids


def test_admin_inativar_e_reativar_ui(client):
    part = db.criar_participante("Inativo UI", status="liberado", celular="11990003333")
    login_admin(client)

    r = client.post("/admin/inativar", data={"participante_id": part["id"]}, follow_redirects=False)
    assert r.status_code == 303
    assert "Participante+inativo" in (r.headers.get("location") or "")

    page = client.get("/admin?sec=inscricoes")
    assert page.status_code == 200
    assert "Inativos" in page.text
    assert "Inativo UI" in page.text
    assert "participante-card-status-btn" in page.text
    assert "Marcar" in page.text  # aria-label / title do botão no canto do card
    assert "data-inscricoes-col=\"inativos\"" in page.text

    cob = client.get("/admin/cobranca")
    assert cob.status_code == 200
    # não deve listar o inativo na cobrança
    assert "Inativo UI" not in cob.text

    r2 = client.post("/admin/reativar", data={"participante_id": part["id"]}, follow_redirects=False)
    assert r2.status_code == 303
    assert db.participante_ativo_no_bolao(db.get_participante(part["id"])) is True

    cob2 = client.get("/admin/cobranca")
    assert "Inativo UI" in cob2.text


def test_sidebar_badge_ignora_inativo(client):
    db.criar_participante("Falta Palpite", status="liberado", celular="11990004444")
    sai = db.criar_participante("Saiu Badge", status="liberado", celular="11990005555")
    for c in db.list_confrontos_completos("oitavas"):
        ida = next(j for j in c["jogos"] if j["perna"] == "ida")
        db.set_inicio_jogo(ida["id"], "2099-08-10 20:00")

    login_admin(client)
    before = client.get("/admin?sec=inscricoes")
    assert before.status_code == 200
    # badge de cobrança no HTML da sidebar
    assert "admin-badge" in before.text

    db.inativar_participante(sai["id"])
    after = client.get("/admin?sec=inscricoes")
    assert after.status_code == 200
    st = db.status_palpites_liberados("oitavas", "ida", so_abertos=True, janela="ida")
    assert all(p["id"] != sai["id"] for p in st["incompletos"])
