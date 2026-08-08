"""Testes da Listra THDFM."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.conftest import login_admin as _login_admin

ROOT_DIR = Path(__file__).resolve().parents[1]


def _criar_liberado(
    nome="Fulano",
    username="fulano",
    senha="senha12345",
    celular="11999990001",
):
    from src import db

    part = db.criar_participante(nome, status="liberado", celular=celular)
    db.definir_credenciais(part["id"], username, senha)
    return db.get_participante(part["id"])


def _login_participante(client: TestClient, part: dict):
    r = client.get(f"/p/{part['token']}", follow_redirects=False)
    assert r.status_code in (200, 303, 302)


@pytest.fixture()
def admin_users():
    return "mazeta=senha-dono=Mazeta:dono|ramos=senha-mod=Ramos:moderador"


def test_listra_publica_com_anos(client: TestClient):
    from html import unescape

    from src.listra_seed import LISTRA_SEED_FRASES, listra_seed_por_ano

    part = _criar_liberado(nome="Leitor Listra", username="leitor.listra", celular="11990001111")
    _login_participante(client, part)
    r = client.get("/grupo/listra")
    assert r.status_code == 200
    body = unescape(r.text)
    assert "Listra" in body
    assert "listra-page" in body
    assert "listra-ano-card--atual" in body
    assert "listra-ano-toggle" in body
    assert "listra-ano-toggle-icon--fechar" in body
    assert "listra-ano-summary" in body
    assert "LISTRA THDFM 2026" in body
    assert "LISTRA THDFM 2025" in body
    assert "LISTRA THDFM 2024" in body
    # First paint leve: frases do seed não vão no HTML inicial.
    assert LISTRA_SEED_FRASES[0] not in body
    assert listra_seed_por_ano(2024)[0] not in body
    assert 'data-listra-lazy="1"' in body
    assert 'data-listra-lazy-src="/grupo/listra/2026.json"' in body
    assert "listraCarregarAno" in body
    assert "Nova frase" not in body
    assert "data-listra-enviar" not in body
    assert "data-listra-ordenar" in body
    assert 'id="listra-toast-host"' in body
    assert 'id="listra-scroll-fab"' in body
    assert "listra-scroll-fab" in body
    assert "Ir para o fim da Listra" in body
    assert "Ir para o topo da Listra" in body  # label no JS do modo up
    assert "Ir para o topo da página" not in body
    assert "listra-scroll-fab-icon--up" not in body
    assert "listra-scroll-fab-icon--down" not in body
    assert body.count("listra-scroll-fab-icon") == 1
    assert "/static/style.css?v=237" in body
    assert "Usar seleção" not in body
    assert "data-listra-destaque-sel" not in body
    assert len(body) < 250_000

    j2026 = client.get("/grupo/listra/2026.json")
    assert j2026.status_code == 200
    assert "private, max-age=60" in (j2026.headers.get("cache-control") or "")
    payload = j2026.json()
    assert payload["ano"] == 2026
    assert payload["total"] >= 1
    textos = [f["texto"] for f in payload["frases"]]
    assert LISTRA_SEED_FRASES[0] in textos

    j2025 = client.get("/grupo/listra/2025.json")
    assert j2025.status_code == 200
    blob = j2025.text
    assert "📺" in blob
    assert "Progama" in blob

    j2024 = client.get("/grupo/listra/2024.json")
    assert j2024.status_code == 200
    assert listra_seed_por_ano(2024)[0] in j2024.text


def test_admin_adiciona_com_emoji_e_destaque(client: TestClient):
    from src.listra_seed import LISTRA_ANO_ATUAL
    from src import db

    _login_admin(client)
    frase_longa = (
        "TESTE FILTRO: o narrador XPTO SILVA (por todos os ângulos) "
        "foi demitido do grupo de testes"
    )
    r = client.post(
        "/grupo/listra",
        data={
            "texto": frase_longa,
            "responsavel": "Mazeta",
            "ano": str(LISTRA_ANO_ATUAL),
            "emoji": "📺",
            "destaque": "XPTO SILVA",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    frase = next(
        f for f in db.list_listra_frases(LISTRA_ANO_ATUAL)
        if f.get("destaque") == "XPTO SILVA"
    )
    assert frase["emoji"] == "📺"
    assert frase["texto"] == frase_longa
    assert "XPTO SILVA" in frase["texto"]

    pub = client.get("/grupo/listra")
    assert frase_longa not in pub.text
    assert "listraCarregarAno" in pub.text

    ano_json = client.get(f"/grupo/listra/{LISTRA_ANO_ATUAL}.json")
    assert ano_json.status_code == 200
    payload = ano_json.json()
    hit = next(f for f in payload["frases"] if f.get("destaque") == "XPTO SILVA")
    assert frase_longa in hit["texto"]
    assert "listra-destaque" in hit["texto_html"]
    assert "XPTO SILVA" in hit["texto_html"]

    frase_json = client.get(f"/grupo/listra/frase/{frase['id']}.json")
    assert frase_json.status_code == 200
    assert frase_json.json()["id"] == frase["id"]

    export = client.get(f"/grupo/listra/export.txt?ano={LISTRA_ANO_ATUAL}")
    assert export.status_code == 200
    assert "📺 XPTO SILVA" in export.text
    assert ". 📺 XPTO SILVA" in export.text  # numerado: N. emoji frase
    assert "📺 TESTE FILTRO" not in export.text
    assert frase_longa not in export.text


def test_emoji_rejeita_texto(client: TestClient):
    from urllib.parse import unquote

    from src.listra_seed import LISTRA_ANO_ATUAL

    _login_admin(client)
    r = client.post(
        "/grupo/listra",
        data={
            "texto": "Frase com emoji inválido",
            "responsavel": "Mazeta",
            "ano": str(LISTRA_ANO_ATUAL),
            "emoji": "ABC",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    loc = unquote(r.headers.get("location") or "").lower()
    assert "emoji" in loc


def test_linha_compartilhar_usa_destaque():
    from src import db

    linha = db.listra_linha_compartilhar(
        {
            "texto": "Frase longa com ODIEI RIBEIRO no meio",
            "emoji": "🎤",
            "destaque": "ODIEI RIBEIRO",
        }
    )
    assert linha == "🎤 ODIEI RIBEIRO"
    sem = db.listra_linha_compartilhar(
        {"texto": "Progama", "emoji": "📺", "destaque": ""}
    )
    assert sem == "📺 Progama"

def test_visitante_nao_adiciona(client: TestClient):
    from urllib.parse import unquote

    r = client.post(
        "/grupo/listra",
        data={"texto": "pérola teste", "responsavel": "Alguém"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    loc = unquote(r.headers.get("location") or "").lower()
    # Anônimo é barrado no gate de login.
    assert "acesso=entrar" in loc or "permiss" in loc


def test_admin_adiciona_no_ano_atual(client: TestClient):
    from src.listra_seed import LISTRA_ANO_ATUAL

    _login_admin(client)
    r = client.post(
        "/grupo/listra",
        data={
            "texto": "Nova pérola do teste",
            "responsavel": "Mazeta",
            "ano": str(LISTRA_ANO_ATUAL),
        },
        follow_redirects=False,
    )
    assert r.status_code == 303

    from src import db

    frase = next(
        f for f in db.list_listra_frases(LISTRA_ANO_ATUAL)
        if f["texto"] == "Nova pérola do teste"
    )
    assert frase["ano"] == LISTRA_ANO_ATUAL
    assert frase.get("criado_em")
    # Novo item guarda data e hora (YYYY-MM-DD HH:MM:…)
    assert len(frase["criado_em"]) >= 16
    assert frase["criado_em"][10] == " "
    assert "Mazeta" in db.list_listra_meliantes()
    pub = client.get("/grupo/listra")
    assert "Nova pérola do teste" not in pub.text
    assert "Mazeta" in pub.text  # opção do select / template de edição
    assert 'data-listra-meliante-select' in pub.text
    assert "listra-save-btn" in pub.text
    assert "Selecione o meliante" in pub.text
    assert "Usar seleção" not in pub.text
    assert "listraCarregarAno" in pub.text
    assert "listra-editar-btn" in pub.text
    assert "/grupo/listra/atualizar" in pub.text
    assert 'id="listra-edit-template"' in pub.text

    ano_json = client.get(f"/grupo/listra/{LISTRA_ANO_ATUAL}.json")
    assert ano_json.status_code == 200
    hit = next(f for f in ano_json.json()["frases"] if f["texto"] == "Nova pérola do teste")
    assert hit["responsavel"] == "Mazeta"
    assert hit["criado_em"]
    assert len(hit["criado_em"]) >= 16


def test_admin_edita_frase(client: TestClient):
    from urllib.parse import unquote

    from src.listra_seed import LISTRA_ANO_ATUAL
    from src import db

    _login_admin(client)
    criada = db.criar_listra_frase(
        "Texto original", "Fulano", ano=LISTRA_ANO_ATUAL
    )
    r = client.post(
        "/grupo/listra/atualizar",
        data={
            "frase_id": criada["id"],
            "texto": "Texto editado",
            "responsavel": "Ciclano",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    loc = unquote(r.headers.get("location") or "")
    assert "edição feita com sucesso" in loc.lower()
    assert f"#listra-frase-{criada['id']}" in loc
    atualizada = db.get_listra_frase(criada["id"])
    assert atualizada["texto"] == "Texto editado"
    assert atualizada["responsavel"] == "Ciclano"
    assert "Ciclano" in db.list_listra_meliantes()
    pub = client.get(
        f"/grupo/listra?msg=Edi%C3%A7%C3%A3o+feita+com+sucesso#listra-frase-{criada['id']}"
    )
    assert "Texto editado" not in pub.text
    assert "Ciclano" in pub.text  # meliante no select
    assert "listraEnsureFrase" in pub.text
    assert 'id="listra-toast-host"' in pub.text
    assert "feita com sucesso" in pub.text
    assert "showToast(" in pub.text
    assert 'class="msg"' not in pub.text

    frase_json = client.get(f"/grupo/listra/frase/{criada['id']}.json")
    assert frase_json.status_code == 200
    assert frase_json.json()["texto"] == "Texto editado"
    assert frase_json.json()["responsavel"] == "Ciclano"


def test_visitante_nao_edita(client: TestClient):
    from src.listra_seed import LISTRA_ANO_ATUAL
    from src import db
    from urllib.parse import unquote

    frase = db.list_listra_frases(LISTRA_ANO_ATUAL)[0]
    r = client.post(
        "/grupo/listra/atualizar",
        data={
            "frase_id": frase["id"],
            "texto": "Hack",
            "responsavel": "Ninguém",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    loc = unquote(r.headers.get("location") or "").lower()
    assert "acesso=entrar" in loc or "administração" in loc or "editar" in loc
    assert db.get_listra_frase(frase["id"])["texto"] != "Hack"


def test_admin_permissoes_painel(client: TestClient):
    part = _criar_liberado()
    _login_admin(client)
    r = client.get("/admin/listra")
    assert r.status_code == 200
    assert part["nome"] in r.text
    assert "Gestor de meliantes" in r.text
    assert 'id="meliantes"' in r.text
    assert "/admin/listra/meliantes" in r.text

    r = client.post(
        "/admin/listra/permissoes",
        data={f"add_{part['id']}": "1", f"env_{part['id']}": "1"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    from src import db

    perm = db.get_listra_permissao(part["id"])
    assert perm["pode_adicionar"] is True
    assert perm["pode_enviar"] is True


def test_admin_gestor_meliantes(client: TestClient):
    from urllib.parse import unquote

    from src import db

    _login_admin(client)
    r = client.post(
        "/admin/listra/meliantes",
        data={"nome": "Odiei Ribeiro"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    loc = unquote(r.headers.get("location") or "")
    assert "adicionado" in loc.lower()
    assert "Odiei Ribeiro" in db.list_listra_meliantes()
    detalhe = {m["nome"]: m for m in db.list_listra_meliantes_detalhe()}
    assert detalhe["Odiei Ribeiro"]["vinculado"] is False

    dup = client.post(
        "/admin/listra/meliantes",
        data={"nome": "odiei ribeiro"},
        follow_redirects=False,
    )
    assert dup.status_code == 303
    assert "já está cadastrado" in unquote(dup.headers.get("location") or "").lower()

    part = _criar_liberado(
        nome="Meliante User", username="meluser", celular="11999990077"
    )
    r_user = client.post(
        "/admin/listra/meliantes",
        data={"participante_id": str(part["id"])},
        follow_redirects=False,
    )
    assert r_user.status_code == 303
    assert "Meliante User" in db.list_listra_meliantes()
    detalhe = {m["nome"]: m for m in db.list_listra_meliantes_detalhe()}
    assert detalhe["Meliante User"]["vinculado"] is True
    assert detalhe["Meliante User"]["participante_id"] == part["id"]

    painel = client.get("/admin/listra")
    assert "Odiei Ribeiro" in painel.text
    assert "Meliante User" in painel.text
    assert "usuário" in painel.text
    assert "livre" in painel.text
    assert "Usuário cadastrado" in painel.text
    assert "Nome livre" in painel.text
    assert "/admin/listra/meliantes/vincular" in painel.text
    assert "data-listra-custom-select" in painel.text
    assert "/static/listra-custom-select.js" in painel.text

    # Vínculo manual: meliante livre → usuário liberado
    part2 = _criar_liberado(
        nome="Link User", username="linkuser", celular="11999990088"
    )
    link = client.post(
        "/admin/listra/meliantes/vincular",
        data={"nome": "Odiei Ribeiro", "participante_id": str(part2["id"])},
        follow_redirects=False,
    )
    assert link.status_code == 303
    assert "vinculado" in unquote(link.headers.get("location") or "").lower()
    detalhe = {m["nome"]: m for m in db.list_listra_meliantes_detalhe()}
    assert detalhe["Odiei Ribeiro"]["vinculado"] is True
    assert detalhe["Odiei Ribeiro"]["participante_id"] == part2["id"]

    desv = client.post(
        "/admin/listra/meliantes/desvincular",
        data={"nome": "Odiei Ribeiro"},
        follow_redirects=False,
    )
    assert desv.status_code == 303
    assert "livre" in unquote(desv.headers.get("location") or "").lower()
    detalhe = {m["nome"]: m for m in db.list_listra_meliantes_detalhe()}
    assert detalhe["Odiei Ribeiro"]["vinculado"] is False

    pub = client.get("/grupo/listra")
    assert "Odiei Ribeiro" in pub.text
    assert "Gestor de meliantes" in pub.text
    assert "limparUrlListra" in pub.text

    apaga = client.post(
        "/admin/listra/meliantes/apagar",
        data={"nome": "Odiei Ribeiro"},
        follow_redirects=False,
    )
    assert apaga.status_code == 303
    assert "Odiei Ribeiro" not in db.list_listra_meliantes()


def test_participante_com_permissao_enviar(client: TestClient):
    part = _criar_liberado(
        nome="Envio", username="envio", senha="senha12345", celular="11999990002"
    )
    from src import db

    db.salvar_listra_permissao(part["id"], pode_adicionar=False, pode_enviar=True)
    _login_participante(client, part)
    r = client.get("/grupo/listra")
    assert "data-listra-copiar" in r.text
    assert "data-listra-abrir-grupo" in r.text
    assert 'aria-label="Copiar a Listra 2026"' in r.text
    assert 'aria-label="Abrir grupo do WhatsApp"' in r.text
    assert 'data-ano="2026"' in r.text
    assert 'data-ano="2025"' in r.text
    assert 'data-ano="2024"' in r.text
    assert "data-listra-ordenar" in r.text
    assert "showListraToast" in r.text
    assert "ultimaFraseCopiada" in r.text
    assert "Última frase:" in r.text
    assert "copiada com sucesso" in r.text


def test_export_por_ano(client: TestClient):
    _login_admin(client)
    r26 = client.get("/grupo/listra/export.txt?ano=2026")
    r25 = client.get("/grupo/listra/export.txt?ano=2025")
    r24 = client.get("/grupo/listra/export.txt?ano=2024")
    assert r26.status_code == 200
    assert r25.status_code == 200
    assert r24.status_code == 200
    assert "LISTRA THDFM 2026" in r26.text
    assert "LISTRA THDFM 2025" in r25.text
    assert "LISTRA THDFM 2024" in r24.text
    assert "1. 📺 Progama" in r25.text
    assert "Chooping" in r24.text
    # Formato numerado estilo 2025 (não usa bullet "* ").
    assert "\n* 📺" not in r25.text
    assert "listra-emoji-opcoes" not in client.get("/grupo/listra").text


def test_export_exige_permissao(client: TestClient):
    part = _criar_liberado(nome="Export Sem Perm", username="export.nop", celular="11990002222")
    _login_participante(client, part)
    r = client.get("/grupo/listra/export.txt")
    assert r.status_code == 403


def test_texto_whatsapp_formatado():
    from src import db
    from src.listra_seed import LISTRA_TITULO

    texto = db.listra_texto_whatsapp(
        [
            {"texto": "Uma", "ano": 2026, "emoji": "", "destaque": ""},
            {"texto": "Duas\nlinhas", "ano": 2026, "emoji": "", "destaque": ""},
        ],
        ano=2026,
    )
    assert texto.startswith(f"*{LISTRA_TITULO}*")
    assert "1. Uma" in texto
    assert "2. Duas" in texto

    com_destaque = db.listra_texto_whatsapp(
        [
            {
                "texto": "EXCELENTE NARRADOR ODIEI RIBEIRO FOI DA PEDIDURA",
                "ano": 2026,
                "emoji": "📺",
                "destaque": "ODIEI RIBEIRO",
            }
        ],
        ano=2026,
    )
    assert "1. 📺 ODIEI RIBEIRO" in com_destaque
    assert "PEDIDURA" not in com_destaque
    assert "EXCELENTE" not in com_destaque


def test_reembolsos_itens_separados_no_seed(client: TestClient):
    from src import db

    textos = [f["texto"] for f in db.list_listra_frases(2026)]
    assert "lista dos reembilos" in textos
    assert "blodo de notas" in textos
    assert any("REEMBOLSOS DO BOLÃO ROLANDO" in t for t in textos)
    assert not any(
        "lista dos reembilos" in t and "blodo de notas" in t for t in textos
    )
    part = _criar_liberado(nome="Leitor Reembolso", username="leitor.reemb", celular="11990003333")
    _login_participante(client, part)
    pub = client.get("/grupo/listra")
    assert "lista dos reembilos" not in pub.text
    j = client.get("/grupo/listra/2026.json")
    assert j.status_code == 200
    assert "lista dos reembilos" in j.text
    assert "blodo de notas" in j.text


def test_seed_2026_emojis_a_partir_do_38(client: TestClient):
    from src import db
    from src.listra_seed import listra_seed_por_ano

    seed = listra_seed_por_ano(2026)
    assert seed[36] == "Ronovava"
    emoji38, texto38 = db.split_leading_emoji(seed[37])
    assert emoji38 == "🧬"
    assert texto38 == "Nem evoluir os pijemin evolui po"
    # Itens 1–37 do seed ficam sem emoji (já feitos na mão).
    for raw in seed[:37]:
        assert db.split_leading_emoji(raw)[0] == ""
    # A partir do 38, todos têm emoji no seed.
    for raw in seed[37:]:
        assert db.split_leading_emoji(raw)[0]

    part = _criar_liberado(nome="Leitor Emoji", username="leitor.emoji", celular="11990004444")
    _login_participante(client, part)
    pub = client.get("/grupo/listra")
    assert "🧬" not in pub.text
    frases = db.list_listra_frases(2026)
    por_ordem = {int(f["ordem"]): f for f in frases}
    assert por_ordem[37]["texto"] == "Ronovava"
    assert por_ordem[38]["emoji"] == "🧬"
    assert por_ordem[38]["texto"] == "Nem evoluir os pijemin evolui po"
    assert por_ordem[286]["emoji"]
    assert "roca" in por_ordem[286]["texto"].lower()

    j = client.get("/grupo/listra/2026.json")
    assert j.status_code == 200
    assert "🧬" in j.text
    assert "Nem evoluir os pijemin evolui po" in j.text


def test_migrar_emojis_do_seed_nao_sobrescreve(client: TestClient):
    from src import db

    with db.get_db() as conn:
        conn.execute(
            "UPDATE listra_frases SET emoji = '' "
            "WHERE ano = 2026 AND ordem >= 38"
        )
        conn.execute(
            "UPDATE listra_frases SET emoji = '💧' "
            "WHERE ano = 2026 AND ordem = 37"
        )
        db._migrar_listra_emojis_do_seed(conn)

    frases = {int(f["ordem"]): f for f in db.list_listra_frases(2026)}
    assert frases[37]["emoji"] == "💧"
    assert frases[38]["emoji"] == "🧬"
    assert frases[38]["texto"] == "Nem evoluir os pijemin evolui po"


def test_migra_reembolsos_combinados(client: TestClient):
    from src import db

    combinado = (
        "@\u200etodos REEMBOLSOS DO BOLÃO ROLANDO\n"
        "INTERESSADOS MANDAREM MENSAGEM NO PRIMAVERA\n"
        "- lista dos reembilos\n"
        "- blodo de notas"
    )
    with db.get_db() as conn:
        conn.execute("DELETE FROM listra_frases WHERE ano = 2026")
        conn.execute(
            "INSERT INTO listra_frases "
            "(texto, responsavel, ordem, ano, criado_em, emoji, destaque) "
            "VALUES (?, '', 10, 2026, datetime('now', 'localtime'), '', '')",
            (combinado,),
        )
        db._migrar_listra_reembolsos_itens(conn)

    textos = [f["texto"] for f in db.list_listra_frases(2026)]
    assert "lista dos reembilos" in textos
    assert "blodo de notas" in textos
    assert any(
        "REEMBOLSOS DO BOLÃO ROLANDO" in t and "PRIMAVERA" in t for t in textos
    )
    assert not any(
        "lista dos reembilos" in t and "blodo de notas" in t for t in textos
    )
    with db.get_db() as conn:
        db._migrar_listra_reembolsos_itens(conn)
    assert [f["texto"] for f in db.list_listra_frases(2026)].count(
        "lista dos reembilos"
    ) == 1
