"""Salts Contínuo compartilhados + SSR anti-flash."""

from __future__ import annotations

from src import db as dbmod
from src.grid_game import dia_grid, gerar_puzzle
from src.grid_partidas import (
    agora_iso,
    iniciar_raiz,
    iniciar_xonha,
    puzzle_da_partida,
    puzzle_ssr_continuo,
    salt_xonha_indice,
)


def _participante(nome: str) -> dict:
    return dbmod.criar_participante(nome, status="liberado")


def _login(client, nome: str, username: str):
    part = _participante(nome)
    dbmod.definir_credenciais(part["id"], username, "senha12345")
    client.cookies.clear()
    r = client.get(f"/p/{part['token']}", follow_redirects=False)
    assert r.status_code in (200, 303)
    return part


def test_salt_xonha_indice_formato():
    assert salt_xonha_indice(1) == "xonha-1"
    assert salt_xonha_indice(2) == "xonha-2"
    assert salt_xonha_indice(3) == "xonha-3"


def test_dois_usuarios_mesmo_slot_mesmos_eixos(client):
    dia = dia_grid()
    a = _participante("Salt A")
    b = _participante("Salt B")
    pa = iniciar_xonha(a["id"], dia)
    pb = iniciar_xonha(b["id"], dia)
    assert pa["puzzle_salt"] == "xonha-1"
    assert pb["puzzle_salt"] == "xonha-1"
    ea = puzzle_da_partida(pa)
    eb = puzzle_da_partida(pb)
    assert [c["id"] for c in ea["linhas"]] == [c["id"] for c in eb["linhas"]]
    assert [c["id"] for c in ea["colunas"]] == [c["id"] for c in eb["colunas"]]
    assert ea["densidades"] == eb["densidades"]


def test_slots_e_pro_diferentes(client):
    dia = dia_grid()
    p = _participante("Salt Slots")
    x1 = iniciar_xonha(p["id"], dia)
    assert x1["puzzle_salt"] == "xonha-1"
    dbmod.atualizar_grid_partida(
        x1["id"],
        finalizado=True,
        iniciado_em=agora_iso(),
        celulas=[[{"ok": True, "clube": {"id": "1", "nome": "A", "rep": 1}}]],
    )
    x2 = iniciar_xonha(p["id"], dia)
    assert x2["puzzle_salt"] == "xonha-2"
    pro = iniciar_raiz(p["id"], dia)
    e1 = puzzle_da_partida(x1)
    e2 = puzzle_da_partida(x2)
    epro = puzzle_da_partida(pro)
    ids1 = ([c["id"] for c in e1["linhas"]], [c["id"] for c in e1["colunas"]])
    ids2 = ([c["id"] for c in e2["linhas"]], [c["id"] for c in e2["colunas"]])
    ids_pro = (
        [c["id"] for c in epro["linhas"]],
        [c["id"] for c in epro["colunas"]],
    )
    assert ids1 != ids2
    assert ids1 != ids_pro
    assert ids2 != ids_pro
    assert gerar_puzzle(dia, salt="xonha-1")["linhas"][0]["id"] == e1["linhas"][0]["id"]


def test_api_iniciar_salt_deterministico(client):
    _login(client, "Salt API", "salt.api")
    r = client.post("/grid/api/iniciar", json={"modo": "xonha"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["partida"]["puzzle_salt"] == "xonha-1"
    assert data["puzzle"]["modo"] == "xonha"
    linhas = [c["id"] for c in data["puzzle"]["linhas"]]
    esperado = gerar_puzzle(dia_grid(), salt="xonha-1")
    assert linhas == [c["id"] for c in esperado["linhas"]]


def test_ssr_continuo_preview_sem_criar_partida(client):
    part = _login(client, "SSR Preview", "ssr.preview")
    dia = dia_grid()
    antes = dbmod.contar_grid_partidas_dia(part["id"], dia, modo="xonha")
    puzzle, partida = puzzle_ssr_continuo(part["id"], dia)
    assert partida is None
    assert puzzle["modo"] == "xonha"
    assert dbmod.contar_grid_partidas_dia(part["id"], dia, modo="xonha") == antes
    esperado = gerar_puzzle(dia, salt="xonha-1")
    assert [c["id"] for c in puzzle["linhas"]] == [
        c["id"] for c in esperado["linhas"]
    ]


def test_ssr_continuo_retoma_aberta(client):
    dia = dia_grid()
    p = _participante("SSR Aberta")
    aberta = iniciar_xonha(p["id"], dia)
    puzzle, partida = puzzle_ssr_continuo(p["id"], dia)
    assert partida is not None
    assert partida["id"] == aberta["id"]
    assert puzzle["modo"] == "xonha"
    assert [c["id"] for c in puzzle["linhas"]] == [
        c["id"] for c in puzzle_da_partida(aberta)["linhas"]
    ]


def test_grid_page_logado_ssr_eixos_continuo(client):
    _login(client, "SSR Page", "ssr.page")
    dia = dia_grid()
    esperado = gerar_puzzle(dia, salt="xonha-1")
    rotulo = esperado["linhas"][0]["rotulo"]
    r = client.get("/grid")
    assert r.status_code == 200
    assert rotulo in r.text
    assert '"modo": "xonha"' in r.text or '"modo":"xonha"' in r.text
    assert "partida" in r.text


def test_grid_page_convidado_ssr_continuo(client):
    client.cookies.clear()
    dia = dia_grid()
    esperado = gerar_puzzle(dia, salt="xonha-1")
    r = client.get("/grid")
    assert r.status_code == 200
    assert esperado["linhas"][0]["rotulo"] in r.text
    assert '"modo": "xonha"' in r.text or '"modo":"xonha"' in r.text
    assert "Jogue o Contínuo" in r.text


def test_convidado_chute_continuo_sem_login(client):
    client.cookies.clear()
    from src.grid_game import clubes_grid, validar_chute
    from src.grid_partidas import salt_convidado_continuo

    dia = dia_grid()
    salt = salt_convidado_continuo()
    alvo = None
    for c in clubes_grid():
        try:
            r = validar_chute(
                dia=dia, linha=0, coluna=0, clube_id=c["id"], salt=salt
            )
        except ValueError:
            continue
        if r["ok"]:
            alvo = c
            break
    assert alvo is not None
    chute = client.post(
        "/grid/api/chute",
        json={"linha": 0, "coluna": 0, "clube_id": alvo["id"]},
    )
    assert chute.status_code == 200, chute.text
    body = chute.json()
    assert body["convidado"] is True
    assert body["modo"] == "xonha"
    assert body["resultado"]["ok"] is True
    assert body["resultado"]["clube"]["id"] == alvo["id"]
    assert "partida" not in body or body.get("partida") is None
