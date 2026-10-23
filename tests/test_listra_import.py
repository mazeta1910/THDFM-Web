"""Testes da importação de .txt para a Listra."""

from __future__ import annotations

from fastapi.testclient import TestClient

from src import listra_import as li
from tests.conftest import login_admin as _login_admin


def test_parse_linhas_ignora_vazias_e_marca_inicio_bloco():
    texto = "Gui\nBibicleta\nFoz de Gaucho\n\nXonha\nNesa branca\n"
    linhas = li.parse_linhas(texto)
    assert [l["texto"] for l in linhas] == [
        "Gui",
        "Bibicleta",
        "Foz de Gaucho",
        "Xonha",
        "Nesa branca",
    ]
    # Primeira linha e a logo após a linha em branco começam bloco.
    assert [l["inicio_bloco"] for l in linhas] == [True, False, False, True, False]


def test_parse_linhas_trim_e_multiplas_vazias():
    texto = "  Gui  \n\n\n   \nFrase 1\n"
    linhas = li.parse_linhas(texto)
    assert [l["texto"] for l in linhas] == ["Gui", "Frase 1"]
    assert linhas[0]["inicio_bloco"] is True
    assert linhas[1]["inicio_bloco"] is True  # veio após várias vazias


def test_classificar_palpite_por_bloco_e_conhecido():
    texto = "Gui\nUma frase bem longa que claramente é uma pérola do grupo.\nXonha\n"
    linhas = li.parse_linhas(texto)
    cls = li.classificar(linhas, meliantes_conhecidos=["Xonha"])
    assert cls[0]["tipo"] == "nome"  # início de bloco
    assert cls[1]["tipo"] == "frase"  # longa, com pontuação
    assert cls[2]["tipo"] == "nome"  # meliante conhecido


def test_classificar_conservador_frases_curtas_no_bloco():
    # Palpite conservador: só o início do bloco vira nome; frases curtas no
    # meio do bloco continuam frase (menos correções manuais).
    texto = "Gui\nBibicleta\nAlce manga\nFoz de Gaucho\n"
    linhas = li.parse_linhas(texto)
    cls = li.classificar(linhas)
    assert [c["tipo"] for c in cls] == ["nome", "frase", "frase", "frase"]


def test_classificar_novo_bloco_apos_linha_em_branco():
    texto = "Gui\nBibicleta\n\nXonha\nNesa branca\n"
    linhas = li.parse_linhas(texto)
    cls = li.classificar(linhas)
    assert [c["tipo"] for c in cls] == ["nome", "frase", "nome", "frase"]


def test_resolver_importacao_cadeia_de_atribuicao():
    itens = [
        {"texto": "Gui", "tipo": "nome"},
        {"texto": "Bibicleta", "tipo": "frase"},
        {"texto": "Foz de Gaucho", "tipo": "frase"},
        {"texto": "Xonha", "tipo": "nome"},
        {"texto": "Nesa branca", "tipo": "frase"},
        {"texto": "lixo", "tipo": "fora"},
    ]
    frases, avisos = li.resolver_importacao(itens)
    assert avisos == []
    assert frases == [
        {"texto": "Bibicleta", "responsavel": "Gui"},
        {"texto": "Foz de Gaucho", "responsavel": "Gui"},
        {"texto": "Nesa branca", "responsavel": "Xonha"},
    ]


def test_resolver_importacao_usa_padrao_e_avisa_sem_meliante():
    itens = [
        {"texto": "Frase solta", "tipo": "frase"},
        {"texto": "Gui", "tipo": "nome"},
        {"texto": "Com dono", "tipo": "frase"},
    ]
    # Sem padrão: a frase antes do 1º nome vira aviso (não entra).
    frases, avisos = li.resolver_importacao(itens)
    assert [f["texto"] for f in frases] == ["Com dono"]
    assert len(avisos) == 1 and avisos[0]["texto"] == "Frase solta"

    # Com padrão: a frase solta é atribuída ao padrão.
    frases2, avisos2 = li.resolver_importacao(itens, meliante_padrao="Mazeta")
    assert avisos2 == []
    assert frases2[0] == {"texto": "Frase solta", "responsavel": "Mazeta"}


def test_resolver_importacao_nomes_consecutivos_ultimo_vence():
    itens = [
        {"texto": "Gui", "tipo": "nome"},
        {"texto": "Xonha", "tipo": "nome"},
        {"texto": "Frase do Xonha", "tipo": "frase"},
    ]
    frases, _ = li.resolver_importacao(itens)
    assert frases == [{"texto": "Frase do Xonha", "responsavel": "Xonha"}]


def _criar_liberado_logado(client: TestClient):
    from src import db

    part = db.criar_participante("Sem Permissao", status="liberado", celular="11988887777")
    db.definir_credenciais(part["id"], "sem.permissao", "senha12345")
    part = db.get_participante(part["id"])
    client.get(f"/p/{part['token']}", follow_redirects=False)
    return part


def test_resolver_importacao_override_por_linha():
    itens = [
        {"texto": "Gui", "tipo": "nome"},
        {"texto": "Herdada", "tipo": "frase"},
        {"texto": "Trocada", "tipo": "frase", "responsavel": "Xonha"},
    ]
    frases, avisos = li.resolver_importacao(itens)
    assert avisos == []
    assert frases == [
        {"texto": "Herdada", "responsavel": "Gui"},
        {"texto": "Trocada", "responsavel": "Xonha"},
    ]


def test_preview_exige_permissao(client: TestClient):
    # Participante logado sem permissão de adicionar recebe 403.
    _criar_liberado_logado(client)
    r = client.post(
        "/grupo/listra/importar/preview",
        data={"texto": "Gui\nFrase"},
        follow_redirects=False,
    )
    assert r.status_code == 403


def test_preview_classifica_e_traz_meliantes(client: TestClient):
    _login_admin(client)
    texto = "Gui\nUma pérola bem longa do grupo, com pontuação final.\n\nXonha\n"
    r = client.post("/grupo/listra/importar/preview", data={"texto": texto})
    assert r.status_code == 200
    data = r.json()
    tipos = [l["tipo"] for l in data["linhas"]]
    assert tipos == ["nome", "frase", "nome"]
    assert "meliantes" in data and isinstance(data["meliantes"], list)
    assert all("nome" in m and "avatar" in m for m in data["meliantes"])


def test_importar_cria_frases_e_meliantes_novos(client: TestClient):
    from src import db

    _login_admin(client)
    payload = {
        "ano": 2026,
        "meliante_padrao": "",
        "itens": [
            {"texto": "Zoinho", "tipo": "nome"},
            {"texto": "Frase um do Zoinho", "tipo": "frase"},
            {"texto": "Frase dois do Zoinho", "tipo": "frase"},
            {"texto": "lixo ignorado", "tipo": "fora"},
            {"texto": "Mazeta", "tipo": "nome"},
            {"texto": "Frase do Mazeta", "tipo": "frase"},
        ],
    }
    r = client.post("/grupo/listra/importar", json=payload)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["ok"] is True
    assert data["criadas"] == 3
    assert "Zoinho" in data["meliantes_novos"]
    assert data["avisos"] == []

    frases = db.list_listra_frases(2026)
    por_texto = {f["texto"]: f["responsavel"] for f in frases}
    assert por_texto["Frase um do Zoinho"] == "Zoinho"
    assert por_texto["Frase dois do Zoinho"] == "Zoinho"
    assert por_texto["Frase do Mazeta"] == "Mazeta"
    assert "lixo ignorado" not in por_texto
    assert "Zoinho" in db.list_listra_meliantes()


def test_importar_avisa_frase_sem_meliante(client: TestClient):
    _login_admin(client)
    payload = {
        "ano": 2026,
        "itens": [
            {"texto": "Frase órfã", "tipo": "frase"},
            {"texto": "Gui", "tipo": "nome"},
            {"texto": "Frase do Gui", "tipo": "frase"},
        ],
    }
    r = client.post("/grupo/listra/importar", json=payload)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["criadas"] == 1
    assert len(data["avisos"]) == 1
    assert data["avisos"][0]["texto"] == "Frase órfã"


def test_unificar_meliantes_reatribui_frases(client: TestClient):
    from src import db

    db.criar_listra_frase("Frase A", "Zoinho", ano=2026)
    db.criar_listra_frase("Frase B", "Zoinho", ano=2026)
    db.criar_listra_frase("Frase C", "Arthur", ano=2026)

    nomes = {n.casefold() for n in db.list_listra_meliantes()}
    assert {"zoinho", "arthur"} <= nomes

    res = db.unificar_listra_meliantes("Zoinho", "Arthur")
    assert res["frases_movidas"] == 2
    assert res["destino"] == "Arthur"

    # Filtra só as frases que criei (o banco de teste já vem com seed).
    frases = db.list_listra_frases(2026)
    minhas = {f["texto"]: f["responsavel"] for f in frases if f["texto"] in ("Frase A", "Frase B", "Frase C")}
    assert minhas == {"Frase A": "Arthur", "Frase B": "Arthur", "Frase C": "Arthur"}
    assert "zoinho" not in {n.casefold() for n in db.list_listra_meliantes()}


def test_unificar_meliantes_valida_entrada(client: TestClient):
    import pytest

    from src import db

    db.criar_listra_frase("Frase", "Gui", ano=2026)
    with pytest.raises(ValueError):
        db.unificar_listra_meliantes("Gui", "Gui")
    with pytest.raises(ValueError):
        db.unificar_listra_meliantes("Gui", "NaoExiste")
