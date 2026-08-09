"""Planilha de palpites: emblemas, fotos e agrupamento por time."""

from __future__ import annotations

from fastapi.testclient import TestClient

import src.db as db
from tests.conftest import login_admin as _login_admin
from src.transparencia import (
    _metricas_palpites,
    metricas_gerais,
    montar_portal,
    ranking_apostadores,
)


def test_montar_portal_agrupa_por_time_e_inclui_avatar(client: TestClient):
    casa = db.criar_participante("Casa Fan", status="liberado", celular="11990000001")
    fora = db.criar_participante("Fora Fan", status="liberado", celular="11990000002")
    emp = db.criar_participante("Empate Fan", status="liberado", celular="11990000003")
    db.salvar_avatar(casa["id"], "casa.jpg")

    confrontos = db.list_confrontos_completos("oitavas")
    assert confrontos
    c = confrontos[0]
    jogo = next(j for j in c["jogos"] if j.get("perna") == "ida")
    mandante = jogo["mandante_clube_id"]
    visitante = "b" if mandante == "a" else "a"

    db.salvar_palpite_jogo(casa["id"], jogo["id"], 2, 0)
    db.salvar_palpite_jogo(fora["id"], jogo["id"], 0, 3)
    db.salvar_palpite_jogo(emp["id"], jogo["id"], 1, 1)

    tabelas = [
        t
        for t in montar_portal("oitavas", exigir_resultado=False)
        if t["jogo_id"] == jogo["id"]
    ]
    assert len(tabelas) == 1
    linhas = tabelas[0]["linhas"]
    grupos = [r for r in linhas if r["tipo"] == "grupo"]
    assert [g["grupo"] for g in grupos] == ["casa", "empate", "fora"]

    casa_row = next(r for r in linhas if r.get("nome") == "Casa Fan")
    assert casa_row["grupo"] == "casa"
    assert casa_row["avatar_path"] == "casa.jpg"
    fora_row = next(r for r in linhas if r.get("nome") == "Fora Fan")
    assert fora_row["grupo"] == "fora"
    emp_row = next(r for r in linhas if r.get("nome") == "Empate Fan")
    assert emp_row["grupo"] == "empate"

    # Empate na ida permanece empate mesmo com pênaltis salvos (só valem na volta)
    db.salvar_palpite_penaltis(emp["id"], c["id"], visitante)
    tabelas2 = [
        t
        for t in montar_portal("oitavas", exigir_resultado=False)
        if t["jogo_id"] == jogo["id"]
    ]
    emp2 = next(r for r in tabelas2[0]["linhas"] if r.get("nome") == "Empate Fan")
    assert emp2["grupo"] == "empate"
    assert emp2["penaltis"] == ""

    # Na volta, empate + pênaltis agrupa no time escolhido e exibe o label
    jogo_volta = next(j for j in c["jogos"] if j.get("perna") == "volta")
    mandante_v = jogo_volta["mandante_clube_id"]
    visitante_v = "b" if mandante_v == "a" else "a"
    db.salvar_palpite_penaltis(emp["id"], c["id"], visitante_v)
    db.salvar_palpite_jogo(emp["id"], jogo_volta["id"], 1, 1)
    tabelas_v = [
        t
        for t in montar_portal("oitavas", exigir_resultado=False)
        if t["jogo_id"] == jogo_volta["id"]
    ]
    assert len(tabelas_v) == 1
    emp_v = next(r for r in tabelas_v[0]["linhas"] if r.get("nome") == "Empate Fan")
    assert emp_v["grupo"] == "fora"
    assert emp_v["penaltis"]

def test_admin_palpites_mostra_emblemas_e_fotos(client: TestClient):
    part = db.criar_participante("Foto User", status="liberado", celular="11990000009")
    db.salvar_avatar(part["id"], "foto.jpg")
    confrontos = db.list_confrontos_completos("oitavas")
    jogo = next(j for j in confrontos[0]["jogos"] if j.get("perna") == "ida")
    db.salvar_palpite_jogo(part["id"], jogo["id"], 1, 0)

    _login_admin(client)
    r = client.get("/admin/palpites?fase=oitavas&perna=ida")
    assert r.status_code == 200
    assert "planilha-th-emblema" in r.text
    assert "planilha-grupo" in r.text
    assert "planilha-avatar" in r.text
    assert "Foto User" in r.text
    assert "/avatars/foto.jpg" in r.text
    assert "planilha-zebra" in r.text
    assert "data-planilha-export" in r.text
    assert "/static/planilha-export.js" in r.text
    assert "Exportar card em PNG" in r.text
    assert "data-planilha-grupo-toggle" in r.text
    assert "btn-planilha-grupo-toggle" in r.text
    assert "data-planilha-grupo-item" in r.text
    assert "planilha-match-title" in r.text
    assert "planilha-metricas" in r.text
    assert "planilha-head-top-spacer" in r.text
    assert "planilha-jogo-tag\">Métricas<" in r.text
    assert "Gerais" in r.text
    assert "Dos jogos" in r.text
    assert "Dos participantes" in r.text
    assert "planilha-metricas-wrap" in r.text
    assert "planilha-section-card" in r.text
    assert "planilha-metricas-bloco-title" in r.text
    assert "Exportar métricas em PNG" in r.text
    assert "Nesta fase/perna" not in r.text
    assert "Palpites por jogo" in r.text
    assert "Mais vitórias casa" in r.text
    assert "Mais vitórias fora" in r.text
    assert "· 1 gols)" in r.text or " gols)" in r.text
    assert "— Ida" not in r.text
    assert "Foto User" in r.text
    assert "data-planilha-export" in r.text
    assert "/static/planilha-export.js?v=197" in r.text

def test_metricas_palpites_conta_lados_medias_e_extremos():
    rows = [
        {"nome": "A", "grupo": "casa", "gols_m": 3, "gols_v": 0, "sem_palpite": False},
        {"nome": "B", "grupo": "casa", "gols_m": 2, "gols_v": 1, "sem_palpite": False},
        {"nome": "C", "grupo": "empate", "gols_m": 1, "gols_v": 1, "sem_palpite": False},
        {"nome": "D", "grupo": "fora", "gols_m": 0, "gols_v": 2, "sem_palpite": False},
        {"nome": "E", "grupo": "casa", "gols_m": None, "gols_v": None, "sem_palpite": True},
    ]
    m = _metricas_palpites(rows, clube_casa="Mirassol", clube_fora="Grêmio")
    assert m["total"] == 4
    assert m["n_casa"] == 2
    assert m["n_empate"] == 1
    assert m["n_fora"] == 1
    assert m["n_sem"] == 1
    assert m["pct_casa"] == 50.0
    assert m["media_gols_partida"] == 2.5
    assert m["media_gols_casa"] == 1.5
    assert m["media_gols_fora"] == 1.0
    assert m["maior_diferenca"]["diff"] == 3
    assert m["maior_diferenca"]["placar"] == "3 x 0"
    assert m["maior_diferenca"]["nome"] == "A"
    assert m["placar_mais_comum"]["n"] >= 1
    assert m["favorito"] == "casa"
    assert m["favorito_label"] == "Mirassol"
    assert m["consenso_pct"] == 50.0
    assert m["mais_gols"]["nome"] == "A"
    assert m["mais_gols"]["total"] == 3
    assert m["menos_gols"]["nome"] == "C"
    assert m["menos_gols"]["total"] == 2

def test_ranking_apostadores_por_fase():
    tabelas = [
        {
            "linhas": [
                {"tipo": "palpite", "nome": "Alto", "grupo": "casa", "gols_m": 4, "gols_v": 1, "sem_palpite": False},
                {"tipo": "palpite", "nome": "Baixo", "grupo": "empate", "gols_m": 0, "gols_v": 0, "sem_palpite": False},
                {"tipo": "palpite", "nome": "Empateiro", "grupo": "empate", "gols_m": 1, "gols_v": 1, "sem_palpite": False},
            ]
        },
        {
            "linhas": [
                {"tipo": "palpite", "nome": "Alto", "grupo": "fora", "gols_m": 1, "gols_v": 3, "sem_palpite": False},
                {"tipo": "palpite", "nome": "Baixo", "grupo": "casa", "gols_m": 1, "gols_v": 0, "sem_palpite": False},
                {"tipo": "palpite", "nome": "Empateiro", "grupo": "empate", "gols_m": 2, "gols_v": 2, "sem_palpite": False},
            ]
        },
    ]
    r = ranking_apostadores(tabelas)
    assert r is not None
    assert r["mais_gols"]["nome"] == "Alto"
    assert r["menos_gols"]["nome"] == "Baixo"
    assert r["mais_empates"]["nome"] == "Empateiro"
    assert r["mais_empates"]["n"] == 2
    assert r["mais_empates"]["pct"] == 100.0
    assert r["mais_casa"]["pct"] is not None
    assert r["placar_mais_alto"]["nome"] == "Alto"
    assert r["placar_mais_alto"]["placar"] == "4 x 1"

def test_metricas_gerais_agrega_fase():
    tabelas = [
        {
            "linhas": [
                {"tipo": "palpite", "nome": "A", "grupo": "casa", "gols_m": 2, "gols_v": 0, "sem_palpite": False},
                {"tipo": "palpite", "nome": "B", "grupo": "empate", "gols_m": 1, "gols_v": 1, "sem_palpite": False},
            ]
        },
        {
            "linhas": [
                {"tipo": "palpite", "nome": "A", "grupo": "fora", "gols_m": 0, "gols_v": 2, "sem_palpite": False},
                {"tipo": "palpite", "nome": "B", "grupo": "fora", "gols_m": 1, "gols_v": 3, "sem_palpite": False},
            ]
        },
    ]
    g = metricas_gerais(tabelas)
    assert g is not None
    assert g["n_casa"] == 1
    assert g["n_empate"] == 1
    assert g["n_fora"] == 2
    assert g["total"] == 4
    assert g["favorito"] == "fora"

def test_montar_portal_inclui_metricas(client: TestClient):
    a = db.criar_participante("Met A", status="liberado", celular="11990000011")
    b = db.criar_participante("Met B", status="liberado", celular="11990000012")
    confrontos = db.list_confrontos_completos("oitavas")
    jogo = next(j for j in confrontos[0]["jogos"] if j.get("perna") == "ida")
    db.salvar_palpite_jogo(a["id"], jogo["id"], 4, 0)
    db.salvar_palpite_jogo(b["id"], jogo["id"], 1, 1)

    tabelas = [
        t
        for t in montar_portal("oitavas", exigir_resultado=False)
        if t["jogo_id"] == jogo["id"]
    ]
    assert len(tabelas) == 1
    m = tabelas[0]["metricas"]
    assert m["n_casa"] >= 1
    assert m["n_empate"] >= 1
    assert m["media_gols_partida"] is not None
    assert m["maior_diferenca"]["diff"] == 4

def test_montar_portal_mostra_pontos_por_acerto(client: TestClient):
    placar = db.criar_participante("Placar Ok", status="liberado", celular="11990000201")
    so_venc = db.criar_participante("So Venc", status="liberado", celular="11990000202")
    gols = db.criar_participante("Gols Casa", status="liberado", celular="11990000203")
    errou = db.criar_participante("Errou Tudo", status="liberado", celular="11990000204")

    confrontos = db.list_confrontos_completos("oitavas")
    c = confrontos[0]
    jogo = next(j for j in c["jogos"] if j.get("perna") == "ida")
    # Resultado oficial 2x1 (mandante vence)
    db.set_resultado_jogo(jogo["id"], 2, 1, None)

    db.salvar_palpite_jogo(placar["id"], jogo["id"], 2, 1)  # placar + vencedor
    db.salvar_palpite_jogo(so_venc["id"], jogo["id"], 3, 0)  # só vencedor
    db.salvar_palpite_jogo(gols["id"], jogo["id"], 2, 0)  # gols casa + vencedor
    db.salvar_palpite_jogo(errou["id"], jogo["id"], 0, 3)  # nada

    tabelas = [
        t
        for t in montar_portal("oitavas", exigir_resultado=True)
        if t["jogo_id"] == jogo["id"]
    ]
    assert len(tabelas) == 1
    by_nome = {
        r["nome"]: r
        for r in tabelas[0]["linhas"]
        if r.get("tipo") == "palpite"
    }

    p = by_nome["Placar Ok"]
    assert p["acertou"] == "Placar"
    assert p["vencedor"] == "Acertou"
    assert p["pts_placar"] == 10
    assert p["pts_vencedor"] == 7
    assert p["pts_total"] == 17

    v = by_nome["So Venc"]
    assert v["acertou"] == "Nada"
    assert v["vencedor"] == "Acertou"
    assert v["pts_vencedor"] == 7
    assert v["pts_total"] == 7

    g = by_nome["Gols Casa"]
    assert g["acertou"] == "Gols Casa"
    assert g["vencedor"] == "Acertou"
    assert g["pts_gols_casa"] == 5
    assert g["pts_vencedor"] == 7
    assert g["pts_total"] == 12

    e = by_nome["Errou Tudo"]
    assert e["acertou"] == "Nada"
    assert e["vencedor"] == "Errou"
    assert e["pts_total"] == 0

    _login_admin(client)
    r = client.get("/transparencia?fase=oitavas&perna=ida")
    assert r.status_code == 200
    assert ">Total<" in r.text or ">Total</th>" in r.text
    assert "Placar +10" in r.text
    assert "Acertou +7" in r.text
    assert "Gols Casa +5" in r.text
    assert "planilha-pts-total" in r.text
    assert ">Pênaltis<" not in r.text
    assert "/static/style.css?v=275" in r.text

    db.set_janela("volta")
    jogo_volta = next(j for j in c["jogos"] if j.get("perna") == "volta")
    db.set_resultado_jogo(jogo_volta["id"], 1, 1, None)
    r_volta = client.get("/transparencia?fase=oitavas&perna=volta")
    assert r_volta.status_code == 200
    assert ">Pênaltis<" in r_volta.text

    # Sem perna na query, abre na janela atual (volta)
    r_default = client.get("/transparencia")
    assert r_default.status_code == 200
    compact = " ".join(r_default.text.split())
    assert 'perna=volta" class="active"' in compact or "perna=volta' class='active'" in compact
    assert ">Pênaltis<" in r_default.text
