"""Árvore, pênaltis com Ida oficial, trava por horário e rota /bolao/meus-palpites."""

from datetime import datetime

from src import db
from src.config import _TZ_SP
from src.seed_data import jogo_palpite_travado, normalizar_inicio_em
from tests.conftest import login_admin


def test_jogo_palpite_travado_meia_hora():
    agora = datetime(2026, 8, 1, 16, 59, tzinfo=_TZ_SP)
    inicio = "2026-08-01 17:30"
    assert jogo_palpite_travado(inicio, agora=agora) is False
    no_limite = datetime(2026, 8, 1, 17, 0, tzinfo=_TZ_SP)
    assert jogo_palpite_travado(inicio, agora=no_limite) is True
    assert jogo_palpite_travado(None, agora=agora) is False
    assert jogo_palpite_travado(inicio, agora=agora, janela="fechado") is True


def test_normalizar_inicio_em():
    assert normalizar_inicio_em("2026-08-10T20:00") == "2026-08-10 20:00"
    assert normalizar_inicio_em("") is None


def test_rota_meus_palpites_exige_sessao(client):
    r = client.get("/bolao/meus-palpites", follow_redirects=False)
    assert r.status_code == 303
    assert "/?acesso=entrar" in r.headers.get("location", "")


def test_rota_meus_palpites_com_sessao(client):
    part = db.criar_participante("Rota User", status="liberado")
    db.definir_credenciais(part["id"], "rotauser", "senha12345")
    client.get(f"/p/{part['token']}")
    r = client.get("/bolao/meus-palpites")
    assert r.status_code == 200
    assert "form-palpites" in r.text or "Palpites" in r.text
    assert "Meus Palpites" in r.text
    assert "30" in r.text
    assert "minutos antes do início" in r.text


def test_menu_aponta_rota_limpa(client):
    part = db.criar_participante("Menu User", status="liberado")
    db.definir_credenciais(part["id"], "menuuser", "senha12345")
    client.get(f"/p/{part['token']}")
    r = client.get("/")
    assert r.status_code == 200
    assert 'href="/bolao/meus-palpites"' in r.text


def test_penaltis_usam_ida_oficial(client):
    login_admin(client)
    part = db.criar_participante("Pen User", status="liberado")
    db.definir_credenciais(part["id"], "penuser", "senha12345")
    confrontos = db.list_confrontos_completos("oitavas")
    c = confrontos[0]
    ida = next(j for j in c["jogos"] if j["perna"] == "ida")
    volta = next(j for j in c["jogos"] if j["perna"] == "volta")
    # Mantém a volta aberta para palpites (seed antigo pode já ter passado).
    db.set_inicio_jogo(volta["id"], "2026-12-01 20:00")
    # Oficial Ida 1x0; usuário na ida tinha palpitado outra coisa
    db.set_resultado_jogo(ida["id"], 1, 0, None)
    db.salvar_palpite_jogo(part["id"], ida["id"], 3, 3)
    db.set_janela("volta")
    client.get(f"/p/{part['token']}")
    # Volta 1x0 (B mandante) → agregado oficial 1-1 → precisa pênaltis
    r = client.post(
        f"/p/{part['token']}/salvar",
        data={f"volta_{c['id']}_m": "1", f"volta_{c['id']}_v": "0", f"pen_{c['id']}": "a"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "erro" not in (r.headers.get("location") or "")
    pens = db.palpites_do_participante(part["id"])["penaltis"]
    assert pens.get(c["id"], {}).get("penaltis_clube_id") == "a"


def test_montar_quartas_via_admin(client):
    login_admin(client)
    # Fecha oitavas com vencedores oficiais
    confrontos = db.list_confrontos_completos("oitavas")
    for c in confrontos:
        ida = next(j for j in c["jogos"] if j["perna"] == "ida")
        volta = next(j for j in c["jogos"] if j["perna"] == "volta")
        db.set_resultado_jogo(ida["id"], 1, 0, None)
        db.set_resultado_jogo(volta["id"], 0, 0, None)
    classificados = db.classificados_da_fase("oitavas")
    assert len(classificados) == 8
    clubs = [c["clube"] for c in classificados]
    data = {"fase": "quartas"}
    for i in range(4):
        data[f"chave_{i}_a"] = clubs[i * 2]
        data[f"chave_{i}_b"] = clubs[i * 2 + 1]
        data[f"chave_{i}_ida"] = f"2026-08-2{i}T20:00"
        data[f"chave_{i}_volta"] = f"2026-08-2{i}T22:00"
    r = client.post("/admin/arvore/montar", data=data, follow_redirects=False)
    assert r.status_code == 303
    quartas = db.list_confrontos_completos("quartas")
    assert len(quartas) == 4
    assert all(len(c["jogos"]) == 2 for c in quartas)
    assert any(j.get("inicio_em") for c in quartas for j in c["jogos"])

    admin = client.get("/admin")
    assert admin.status_code == 200
    assert "Árvore / próxima fase" in admin.text
    assert "Quartas" in admin.text


def test_seed_oitavas_tem_horarios_da_volta(client):
    from src.seed_data import OITAVAS

    by_id = {item["id"]: item for item in OITAVAS}
    assert by_id[1]["volta_em"] == "2026-08-05 21:30"  # Flu x Vasco
    assert by_id[2]["volta_em"] == "2026-08-04 19:30"  # Juventude x CAM
    assert by_id[3]["volta_em"] == "2026-08-04 21:30"  # Remo x Santos
    assert by_id[4]["volta_em"] == "2026-08-05 21:30"  # Fortaleza x Palmeiras
    assert by_id[5]["volta_em"] == "2026-08-05 19:30"  # Grêmio x Mirassol
    assert by_id[6]["volta_em"] == "2026-08-05 19:00"  # Cruzeiro x Chape
    assert by_id[7]["volta_em"] == "2026-08-06 20:00"  # Corinthians x Inter
    assert by_id[8]["volta_em"] == "2026-08-06 20:00"  # Vitória x Athletico

    confrontos = db.list_confrontos_completos("oitavas")
    for c in confrontos:
        volta = next(j for j in c["jogos"] if j["perna"] == "volta")
        assert volta.get("inicio_em") == by_id[c["id"]]["volta_em"]


def test_migrate_preenche_volta_vazia(client, tmp_path, monkeypatch):
    """Banco antigo sem horário na volta recebe os oficiais na migração."""
    from src.seed_data import OITAVAS

    # Simula volta sem início
    with db.get_db() as conn:
        conn.execute(
            "UPDATE jogos SET inicio_em = NULL WHERE perna = 'volta'"
        )
    db.init_db()  # roda _migrate_jogos de novo
    by_id = {item["id"]: item for item in OITAVAS}
    for c in db.list_confrontos_completos("oitavas"):
        volta = next(j for j in c["jogos"] if j["perna"] == "volta")
        assert volta.get("inicio_em") == by_id[c["id"]]["volta_em"]


def test_salvar_mantem_placares_se_faltar_penaltis(client):
    """Faltar pênaltis não pode descartar os placares já preenchidos."""
    part = db.criar_participante("Pen Falta", status="liberado")
    db.definir_credenciais(part["id"], "penfalta", "senha12345")
    confrontos = db.list_confrontos_completos("oitavas")
    c1, c2 = confrontos[0], confrontos[1]
    for c in (c1, c2):
        ida = next(j for j in c["jogos"] if j["perna"] == "ida")
        # Ida 0x0 oficial → Volta 1x1 empata no agregado e exige pênaltis
        db.set_resultado_jogo(ida["id"], 0, 0, None)
        # Libera edição (horário no futuro)
        volta = next(j for j in c["jogos"] if j["perna"] == "volta")
        db.set_inicio_jogo(volta["id"], "2099-01-01 20:00")
    db.set_janela("volta")
    client.get(f"/p/{part['token']}")

    data = {
        f"volta_{c1['id']}_m": "1",
        f"volta_{c1['id']}_v": "1",
        f"volta_{c2['id']}_m": "2",
        f"volta_{c2['id']}_v": "2",
        # sem pen_* de propósito
    }
    r = client.post(
        f"/p/{part['token']}/salvar",
        data=data,
        follow_redirects=False,
    )
    assert r.status_code == 303
    loc = r.headers.get("location") or ""
    assert "erro=" in loc
    assert "Placares" in loc or "penaltis" in loc.lower() or "p%C3%AAnaltis" in loc

    palp = db.palpites_do_participante(part["id"])
    v1 = next(j for j in c1["jogos"] if j["perna"] == "volta")
    v2 = next(j for j in c2["jogos"] if j["perna"] == "volta")
    assert palp["jogos"][v1["id"]]["gols_mandante"] == 1
    assert palp["jogos"][v1["id"]]["gols_visitante"] == 1
    assert palp["jogos"][v2["id"]]["gols_mandante"] == 2
    assert palp["jogos"][v2["id"]]["gols_visitante"] == 2
    assert c1["id"] not in palp["penaltis"]
    assert c2["id"] not in palp["penaltis"]
