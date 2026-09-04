"""Fase 5–6 — ranking por modo, UI markers, passe admin."""

from __future__ import annotations

from src import db as dbmod
from src.grid_game import dia_grid
from src.grid_partidas import iniciar_raiz, iniciar_xonha
from src.grid_score import pontos_partida
from tests.conftest import login_admin


def test_ranking_grid_modo_score_unico(client):
    a = dbmod.criar_participante("Rank A", status="liberado")
    b = dbmod.criar_participante("Rank B", status="liberado")
    dia = dia_grid()
    pa = iniciar_raiz(a["id"], dia)
    pb = iniciar_raiz(b["id"], dia)
    # A com mais pontos artificiais
    dbmod.atualizar_grid_partida(pa["id"], pontos=500, finalizado=True, celulas=[[{"ok": True, "clube": {"id": "1", "nome": "X", "rep": 100}}]])
    dbmod.atualizar_grid_partida(pb["id"], pontos=100, finalizado=True, celulas=[[{"ok": True, "clube": {"id": "2", "nome": "Y", "rep": 100}}]])
    rank = dbmod.ranking_grid_modo("raiz", limite=10)
    assert rank
    assert rank[0]["participante_id"] == a["id"]
    assert rank[0]["score"] >= rank[1]["score"]
    assert "score" in rank[0]


def test_grid_page_tem_modos_e_rankings(client):
    r = client.get("/grid")
    assert r.status_code == 200
    assert 'data-grid-mode="raiz"' in r.text
    assert 'data-grid-mode="xonha"' in r.text
    assert "Pro" in r.text
    assert "Contínuo" in r.text
    assert "data-grid-live-score" in r.text
    assert "grid-hero-block" in r.text
    assert "grid-toolbar" in r.text
    assert "data-grid-warn-modal" in r.text
    assert 'data-rank-modo="xonha"' in r.text
    assert "data-grid-rank-panel" in r.text
    assert "Detalhes" in r.text
<<<<<<< HEAD
    assert "/static/grid.js?v=32" in r.text
=======
    assert "/static/grid.js?v=33" in r.text
>>>>>>> origin/master
    assert "Modo Pro" in r.text
    assert "Modo Raiz" not in r.text
    assert "data-grid-leave-pro-modal" in r.text
    assert "Sair do Pro?" in r.text
    assert "data-grid-leave-pro-ok" in r.text
    assert 'data-rank-modo="xonha"' in r.text
    # Ranking default = Contínuo (mesmo modo de jogo)
    assert 'data-rank-modo="xonha" aria-selected="true"' in r.text or (
        'data-rank-modo="xonha"' in r.text and 'data-grid-rank-raiz hidden' in r.text
    )

def test_admin_libera_passe_xonha(client):
    part = dbmod.criar_participante("Passe UI", status="liberado")
    login_admin(client)
    r = client.post(
        "/grid/api/admin/xonha-passe",
        json={"participante_id": part["id"], "dias": 30},
    )
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True
    assert dbmod.grid_xonha_passe_ativo(part["id"]) is True


def test_admin_resumo_mostra_tipo_pro_e_continuo(client):
    """Histórico de tentativas distingue Pro vs Contínuo."""
    from src.grid_partidas import agora_iso

    login_admin(client)
    p = dbmod.criar_participante("Hist Tipo", status="liberado")
    dia = dia_grid()
    pro = iniciar_raiz(p["id"], dia)
    dbmod.atualizar_grid_partida(
        pro["id"],
        pontos=100,
        finalizado=True,
        iniciado_em=agora_iso(),
        celulas=[[{"ok": True, "clube": {"id": "1", "nome": "A", "rep": 1}}]],
    )
    x1 = iniciar_xonha(p["id"], dia)
    dbmod.atualizar_grid_partida(
        x1["id"],
        pontos=50,
        finalizado=True,
        iniciado_em=agora_iso(),
        celulas=[[{"ok": True, "clube": {"id": "2", "nome": "B", "rep": 1}}]],
    )
    x2 = iniciar_xonha(p["id"], dia)
    dbmod.atualizar_grid_partida(
        x2["id"],
        pontos=40,
        finalizado=False,
        iniciado_em=agora_iso(),
        celulas=[[{"ok": True, "clube": {"id": "3", "nome": "C", "rep": 1}}]],
    )
    r = client.get(f"/grid/api/admin/resumo?dia={dia}")
    assert r.status_code == 200
    respostas = r.json()["respostas"]
    rotulos = {row["modo_rotulo"] for row in respostas if row["participante_id"] == p["id"]}
    assert "Pro" in rotulos
    assert "Contínuo 1" in rotulos
    assert "Contínuo 2" in rotulos


def test_iniciar_share_respeita_modo(client):
    """Share ao retomar partida encerrada usa o tipo do modo atual (não o boot Pro)."""
    from src.grid_partidas import agora_iso

    p = dbmod.criar_participante("Share Modo", status="liberado")
    dbmod.definir_credenciais(p["id"], "share.modo", "senha12345")
    client.cookies.clear()
    client.get(f"/p/{p['token']}")
    dia = dia_grid()
    pro = iniciar_raiz(p["id"], dia)
    dbmod.atualizar_grid_partida(
        pro["id"],
        pontos=200,
        finalizado=True,
        iniciado_em=agora_iso(),
        celulas=[[{"ok": True, "clube": {"id": "1", "nome": "A", "rep": 1}}]],
    )
    r_pro = client.post("/grid/api/iniciar", json={"modo": "raiz"})
    assert r_pro.status_code == 200
    data_pro = r_pro.json()
    assert data_pro["modo"] == "raiz"
    assert "share" in data_pro
    assert data_pro["share"].startswith("THDFM Grid Pro")

    # Novo Contínuo em andamento: sem share de Pro grudado
    r_x = client.post("/grid/api/iniciar", json={"modo": "xonha"})
    assert r_x.status_code == 200
    data_x = r_x.json()
    assert data_x["modo"] == "xonha"
    assert not data_x["partida"].get("finalizado")
    assert "share" not in data_x

    # Finaliza Contínuo e retoma via chute/share path: finalizar + iniciar novo
    # não devolve a finalizada; o share correto vem no chute. Garante índice.
    pid = data_x["partida"]["id"]
    dbmod.atualizar_grid_partida(
        pid,
        pontos=150,
        finalizado=True,
        iniciado_em=agora_iso(),
        celulas=[[{"ok": True, "clube": {"id": "2", "nome": "B", "rep": 1}}]],
    )
    from src.grid_partidas import texto_share_partida

    part = dbmod.get_grid_partida(pid)
    share = texto_share_partida(part)
    assert share.startswith("THDFM Grid 1")
    assert "Pro" not in share.splitlines()[0]
    p = dbmod.criar_participante("Xonha Rank", status="liberado")
    dia = dia_grid()
    part = iniciar_xonha(p["id"], dia)
    dbmod.atualizar_grid_partida(
        part["id"],
        pontos=222,
        finalizado=True,
        celulas=[[{"ok": True, "clube": {"id": "9", "nome": "Z", "rep": 400}}]],
    )
    rx = dbmod.ranking_grid_modo("xonha")
    rr = dbmod.ranking_grid_modo("raiz")
    assert any(x["participante_id"] == p["id"] for x in rx)
    assert not any(x["participante_id"] == p["id"] for x in rr)


def test_xonha_ranking_so_primeira_partida_do_dia(client):
    """2ª/3ª Contínuo do dia não somam no ranking (só diversão)."""
    from src.grid_score import pontos_partida, score_ranking

    p = dbmod.criar_participante("Xonha Diversao", status="liberado")
    dia = dia_grid()
    cells1 = [[{"ok": True, "clube": {"id": "1", "nome": "A", "rep": 50}}]]
    p1 = iniciar_xonha(p["id"], dia)
    dbmod.atualizar_grid_partida(
        p1["id"],
        pontos=100,
        finalizado=True,
        celulas=cells1,
    )
    p2 = iniciar_xonha(p["id"], dia)
    dbmod.atualizar_grid_partida(
        p2["id"],
        pontos=900,
        finalizado=True,
        celulas=[[{"ok": True, "clube": {"id": "2", "nome": "B", "rep": 50}}]],
    )
    rank = dbmod.ranking_grid_modo("xonha")
    me = next(x for x in rank if x["participante_id"] == p["id"])
    assert me["partidas_finalizadas"] == 1
    assert me["dias_finalizados"] == 1
    expected_pts = pontos_partida(cells1, finalizado=True)
    assert me["score"] == score_ranking([expected_pts], streak=me["streak"])
    assert me["streak"] >= 1


def test_ranking_modo_acertos_vencem_raridade(client):
    """Déficit grande (3 vs 6): mais acertos vencem, mesmo com Rep menor."""
    from src.grid_partidas import iniciar_xonha as _ix

    a = dbmod.criar_participante("3 Obscuros", status="liberado")
    b = dbmod.criar_participante("6 Famosos", status="liberado")
    dia = dia_grid()
    pa = _ix(a["id"], dia)
    pb = _ix(b["id"], dia)
    cells3 = [
        [
            {"ok": True, "clube": {"id": "o1", "nome": "O1", "rep": 200}},
            {"ok": True, "clube": {"id": "o2", "nome": "O2", "rep": 200}},
            {"ok": True, "clube": {"id": "o3", "nome": "O3", "rep": 200}},
        ],
        [None, None, None],
        [None, None, None],
    ]
    cells6 = [
        [
            {"ok": True, "clube": {"id": "f1", "nome": "F1", "rep": 7750}},
            {"ok": True, "clube": {"id": "f2", "nome": "F2", "rep": 7750}},
            {"ok": True, "clube": {"id": "f3", "nome": "F3", "rep": 7750}},
        ],
        [
            {"ok": True, "clube": {"id": "f4", "nome": "F4", "rep": 7750}},
            {"ok": True, "clube": {"id": "f5", "nome": "F5", "rep": 7750}},
            {"ok": True, "clube": {"id": "f6", "nome": "F6", "rep": 7750}},
        ],
        [None, None, None],
    ]
    dbmod.atualizar_grid_partida(pa["id"], pontos=99999, finalizado=True, celulas=cells3)
    dbmod.atualizar_grid_partida(pb["id"], pontos=1, finalizado=True, celulas=cells6)
    rank = dbmod.ranking_grid_modo("xonha")
    ids = [x["participante_id"] for x in rank]
    assert ids.index(b["id"]) < ids.index(a["id"])
    me_b = next(x for x in rank if x["participante_id"] == b["id"])
    me_a = next(x for x in rank if x["participante_id"] == a["id"])
    assert me_b["celulas_ok"] == 6
    assert me_a["celulas_ok"] == 3
    assert me_b["score"] > me_a["score"]
    assert me_a["pontos_rep"] > me_b["pontos_rep"]


def test_ranking_modo_raros_podem_passar_safe(client):
    """7/9 obscuros podem ficar na frente de 8/9 safe."""
    from src.grid_partidas import iniciar_xonha as _ix

    a = dbmod.criar_participante("7 Raros", status="liberado")
    b = dbmod.criar_participante("8 Safe", status="liberado")
    dia = dia_grid()
    pa = _ix(a["id"], dia)
    pb = _ix(b["id"], dia)

    def cells(n: int, rep: int, prefix: str):
        flat = [
            {"ok": True, "clube": {"id": f"{prefix}{i}", "nome": f"{prefix}{i}", "rep": rep}}
            for i in range(n)
        ] + [None] * (9 - n)
        return [flat[0:3], flat[3:6], flat[6:9]]

    dbmod.atualizar_grid_partida(
        pa["id"], pontos=1, finalizado=True, celulas=cells(7, 200, "r")
    )
    dbmod.atualizar_grid_partida(
        pb["id"], pontos=99999, finalizado=True, celulas=cells(8, 7750, "s")
    )
    rank = dbmod.ranking_grid_modo("xonha")
    ids = [x["participante_id"] for x in rank]
    assert ids.index(a["id"]) < ids.index(b["id"])
    me_a = next(x for x in rank if x["participante_id"] == a["id"])
    me_b = next(x for x in rank if x["participante_id"] == b["id"])
    assert me_a["celulas_ok"] == 7
    assert me_b["celulas_ok"] == 8
    assert me_a["score"] > me_b["score"]


def test_xonha_streak_exige_primeira_finalizada(client):
    p = dbmod.criar_participante("Xonha Streak 1ª", status="liberado")
    dia = dia_grid()
    p1 = iniciar_xonha(p["id"], dia)
    # 1ª abandonada (interrompida, não finalizada); 2ª finalizada com muitos pontos
    dbmod.atualizar_grid_partida(
        p1["id"],
        pontos=10,
        finalizado=False,
        interrompido=True,
        celulas=[[{"ok": True, "clube": {"id": "1", "nome": "A", "rep": 1}}]],
    )
    p2 = iniciar_xonha(p["id"], dia)
    assert p2["id"] != p1["id"]
    dbmod.atualizar_grid_partida(
        p2["id"],
        pontos=500,
        finalizado=True,
        celulas=[[{"ok": True, "clube": {"id": "2", "nome": "B", "rep": 1}}]],
    )
    assert dbmod.grid_streak_modo(p["id"], "xonha", ate_dia=dia) == 0
    rank = dbmod.ranking_grid_modo("xonha")
    me = next(x for x in rank if x["participante_id"] == p["id"])
    assert me["dias_finalizados"] == 0
    assert me["partidas_finalizadas"] == 0
