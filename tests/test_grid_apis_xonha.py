"""Fase 4 — APIs Xonha: cota, salt, dicas Contagem/Matriz."""

from __future__ import annotations

from src import db as dbmod
from src.grid_game import dia_grid, gerar_puzzle
from src.grid_partidas import XONHA_LIVRE_POR_DIA, MATRIZ_TAMANHO, MATRIZ_VALIDOS
from src.grid_score import CUSTO_CONTAGEM, custo_dica_matriz


def _login(client, nome: str, username: str):
    part = dbmod.criar_participante(nome, status="liberado")
    dbmod.definir_credenciais(part["id"], username, "senha12345")
    client.cookies.clear()
    r = client.get(f"/p/{part['token']}", follow_redirects=False)
    assert r.status_code in (200, 303)
    return part


def test_gerar_puzzle_salt_diferente_do_oficial():
    dia = dia_grid()
    a = gerar_puzzle(dia)
    b = gerar_puzzle(dia, salt="xonha-teste-aaa")
    c = gerar_puzzle(dia, salt="xonha-teste-bbb")
    # Salt diferente deve poder divergir dos eixos oficiais (quase sempre).
    assert b["linhas"] or b["colunas"]
    assert (b["linhas"], b["colunas"]) != (c["linhas"], c["colunas"]) or b[
        "densidades"
    ] != c["densidades"]
    # Oficial sem salt explícito permanece estável
    assert gerar_puzzle(dia) == a


def test_iniciar_xonha_respeita_cota_de_3(client):
    from src.grid_partidas import agora_iso

    part = _login(client, "Xonha Cota", "xonha.cota")
    ids = []
    for i in range(XONHA_LIVRE_POR_DIA):
        r = client.post("/grid/api/iniciar", json={"modo": "xonha"})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["modo"] == "xonha"
        assert data["partida"]["puzzle_salt"]
        assert data["puzzle"]["modo"] == "xonha"
        pid = data["partida"]["id"]
        ids.append(pid)
        # Consome a cota: marca início e finaliza para liberar slot de "aberta"
        # (iniciar Contínuo retoma a aberta — sem isso, 3 POSTs = 1 partida).
        dbmod.atualizar_grid_partida(
            pid,
            iniciado_em=agora_iso(),
            finalizado=True,
            celulas=[[{"ok": True, "clube": {"id": f"c{i}", "nome": "X", "rep": 1}}]],
        )
    assert len(set(ids)) == XONHA_LIVRE_POR_DIA

    bloqueado = client.post("/grid/api/iniciar", json={"modo": "xonha"})
    assert bloqueado.status_code == 402
    body = bloqueado.json()
    assert "1,65" in body["erro"] or "1,65" in body.get("pix_valor", "")
    assert body["cota"]["usados"] == 3
    assert body["cota"]["passe_ativo"] is False

    # Com passe, libera
    dbmod.liberar_grid_xonha_passe(
        part["id"], valido_ate="2099-01-01", liberado_por="teste"
    )
    ok = client.post("/grid/api/iniciar", json={"modo": "xonha"})
    assert ok.status_code == 200, ok.text


def test_iniciar_xonha_retoma_aberta(client):
    _login(client, "Xonha Resume", "xonha.resume")
    a = client.post("/grid/api/iniciar", json={"modo": "xonha"}).json()["partida"]["id"]
    b = client.post("/grid/api/iniciar", json={"modo": "xonha"}).json()["partida"]["id"]
    assert a == b
    assert client.post("/grid/api/iniciar", json={"modo": "xonha"}).json()["cota_xonha"][
        "usados"
    ] == 0


def test_dicas_contagem_e_matriz(client):
    _login(client, "Xonha Dicas", "xonha.dicas")
    partida = client.post("/grid/api/iniciar", json={"modo": "xonha"}).json()["partida"]
    pid = partida["id"]

    c1 = client.post(
        "/grid/api/dica",
        json={"partida_id": pid, "linha": 0, "coluna": 0, "tipo": "contagem"},
    )
    assert c1.status_code == 200, c1.text
    d1 = c1.json()
    assert d1["dica"]["tipo"] == "contagem"
    assert d1["dica"]["custo"] == CUSTO_CONTAGEM
    assert d1["dica"]["payload"]["densidade"] >= 1
    score_apos_contagem = d1["score_parcial"]

    # Segunda contagem na mesma célula → erro
    dup = client.post(
        "/grid/api/dica",
        json={"partida_id": pid, "linha": 0, "coluna": 0, "tipo": "contagem"},
    )
    assert dup.status_code == 400

    m1 = client.post(
        "/grid/api/dica",
        json={"partida_id": pid, "linha": 0, "coluna": 1, "tipo": "matriz"},
    )
    assert m1.status_code == 200, m1.text
    mat = m1.json()
    assert mat["dica"]["custo"] == custo_dica_matriz(0) == 80
    clubes = mat["dica"]["payload"]["clubes"]
    assert len(clubes) == MATRIZ_TAMANHO
    assert all("nome" in c and "emblema" in c for c in clubes)
    assert mat["proximo_custo_matriz"] == 160
    assert mat["score_parcial"] <= score_apos_contagem  # descontou

    m2 = client.post(
        "/grid/api/dica",
        json={"partida_id": pid, "linha": 1, "coluna": 1, "tipo": "matriz"},
    )
    assert m2.status_code == 200
    assert m2.json()["dica"]["custo"] == 160
    assert m2.json()["proximo_custo_matriz"] == 240

    m3 = client.post(
        "/grid/api/dica",
        json={"partida_id": pid, "linha": 2, "coluna": 2, "tipo": "matriz"},
    )
    assert m3.status_code == 200
    assert m3.json()["dica"]["custo"] == 240
    assert m3.json()["proximo_custo_matriz"] == 320


def test_matriz_tem_exatos_dois_validos(client):
    """Sanidade: payload não marca válidos, mas a contagem no pool bate 2."""
    from src.grid_game import categoria_por_id, pool_celula
    from src.grid_partidas import puzzle_da_partida

    _login(client, "Xonha Pool", "xonha.pool")
    data = client.post("/grid/api/iniciar", json={"modo": "xonha"}).json()
    partida = data["partida"]
    mat = client.post(
        "/grid/api/dica",
        json={
            "partida_id": partida["id"],
            "linha": 0,
            "coluna": 0,
            "tipo": "matriz",
        },
    ).json()
    puzzle = puzzle_da_partida(partida)
    row = categoria_por_id(puzzle["linhas"][0]["id"])
    col = categoria_por_id(puzzle["colunas"][0]["id"])
    assert row and col
    ids_ok = {c["id"] for c in pool_celula(row, col)}
    no_payload = [c["id"] for c in mat["dica"]["payload"]["clubes"]]
    n_validos = sum(1 for i in no_payload if i in ids_ok)
    assert n_validos == MATRIZ_VALIDOS


def test_dica_nao_funciona_no_raiz(client):
    _login(client, "Raiz Sem Dica", "raiz.nodica")
    pid = client.post("/grid/api/iniciar", json={"modo": "raiz"}).json()["partida"]["id"]
    r = client.post(
        "/grid/api/dica",
        json={"partida_id": pid, "linha": 0, "coluna": 0, "tipo": "contagem"},
    )
    assert r.status_code == 400
