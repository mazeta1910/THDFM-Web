"""THDFM Grid — puzzle diário privado (Mazeta)."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from src.config import ROOT_DIR
from src.grid_game import (
    DENSIDADE_MIN,
    TZ_SP,
    categoria_por_id,
    clubes_grid,
    clubes_por_id,
    dia_grid,
    gerar_puzzle,
    ms_ate_proxima_virada,
    pool_celula,
    texto_share,
    validar_chute,
)
from tests.conftest import login_admin


def test_gerar_puzzle_deterministico_e_denso():
    a = gerar_puzzle("2026-08-10")
    b = gerar_puzzle("2026-08-10")
    assert a == b
    assert a["tamanho"] == 3
    assert len(a["linhas"]) == 3
    assert len(a["colunas"]) == 3
    for row in a["densidades"]:
        assert all(n >= DENSIDADE_MIN for n in row)


def test_virada_meia_noite_sao_paulo():
    antes = datetime(2026, 8, 10, 23, 59, 30, tzinfo=TZ_SP)
    depois = datetime(2026, 8, 11, 0, 0, 0, tzinfo=TZ_SP)
    assert dia_grid(antes) == "2026-08-10"
    assert dia_grid(depois) == "2026-08-11"
    assert gerar_puzzle(dia_grid(antes)) != gerar_puzzle(dia_grid(depois))

    ms = ms_ate_proxima_virada(antes)
    assert 0 < ms <= 30_000 + 50
    assert ms_ate_proxima_virada(depois) > 23 * 60 * 60 * 1000

    # UTC 03:00 == 00:00 SP (sem horário de verão)
    utc = ZoneInfo("UTC")
    assert dia_grid(datetime(2026, 8, 11, 2, 59, tzinfo=utc)) == "2026-08-10"
    assert dia_grid(datetime(2026, 8, 11, 3, 0, tzinfo=utc)) == "2026-08-11"


def test_vancouver_whitecaps_no_catalogo_fora_do_puzzle():
    from src.clubes_catalogo import carregar_clubes

    carregar_clubes.cache_clear()
    clubes_grid.cache_clear()
    clubes_por_id.cache_clear()

    white = next(c for c in carregar_clubes() if "Whitecaps" in c["nome"])
    assert white["uf"] == "EX"
    assert white["tem_emblema"] is True
    assert white["id_arquivo"] == "4400014"
    assert (ROOT_DIR / "data/clubes/emblemas-por-id/4400014.png").is_file()
    assert white["id"] not in {c["id"] for c in clubes_grid()}


def test_grid_exige_login(client: TestClient):
    r = client.get("/grid", follow_redirects=False)
    assert r.status_code in (303, 302)


def test_grid_og_preview_para_bot_whatsapp(client: TestClient):
    """Crawler do WhatsApp precisa ver título/OG do Grid (sem redirect de login)."""
    r = client.get(
        "/grid",
        headers={"User-Agent": "WhatsApp/2.23.0"},
        follow_redirects=False,
    )
    assert r.status_code == 200
    assert "<title>THDFM Grid</title>" in r.text
    assert 'property="og:title" content="THDFM Grid"' in r.text
    assert 'property="og:description"' in r.text
    assert "Puzzle diário" in r.text
    assert 'property="og:image" content="' in r.text
    assert "/static/img/og-grid.png" in r.text
    assert 'property="og:url"' in r.text
    assert "/grid" in r.text
    assert (ROOT_DIR / "static" / "img" / "og-grid.png").is_file()


def test_grid_liberado_para_participante(client: TestClient):
    from src import db as dbmod

    part = dbmod.criar_participante("Grid User", status="liberado", celular="11991112201")
    dbmod.definir_credenciais(part["id"], "grid.user", "senha12345")
    client.get(f"/p/{part['token']}")

    r = client.get("/grid")
    assert r.status_code == 200
    assert "THDFM Grid" in r.text
    assert "Prévia privada" not in r.text
    assert "Puzzle diário" in r.text
    api = client.get("/grid/api/hoje")
    assert api.status_code == 200
    assert api.json()["pode_salvar"] is True


def test_grid_fluxo_logado(client: TestClient):
    login_admin(client)
    r = client.get("/grid")
    assert r.status_code == 200
    assert "THDFM Grid" in r.text
    assert "Puzzle diário" in r.text
    assert 'id="thdfm-grid"' in r.text
    assert "/static/grid.js?v=6" in r.text
    assert "data-virada-ms=" in r.text
    assert "00:00 (Brasília)" in r.text
    assert "data-grid-share-wa" in r.text
    assert "aria-label=\"Compartilhar no WhatsApp\"" in r.text
    assert "WhatsApp</button>" not in r.text
    assert 'id="ranking"' in r.text
    assert "grid-result-top" in r.text
    assert "data-grid-chute" in r.text
    assert "data-grid-suggestions" not in r.text
    assert "Jogos e Passatempos" in (
        ROOT_DIR / "templates" / "partials" / "site_sidebar.html"
    ).read_text(encoding="utf-8")
    site_side = (
        ROOT_DIR / "templates" / "partials" / "site_sidebar.html"
    ).read_text(encoding="utf-8")
    assert "Jogos e Passatempos" in site_side
    assert site_side.index("Jogos e Passatempos") < site_side.index("Bolão CdB")
    assert 'href="/grid"' in site_side
    assert "/grid" in site_side and "Ranking Grid" in site_side
    # fora do submenu Bolão
    bolao_block = site_side.split('data-group="bolao"', 1)[1].split("</details>", 1)[0]
    assert "THDFM Grid" not in bolao_block
    assert "Ranking Grid" not in bolao_block
    js = (ROOT_DIR / "static" / "grid.js").read_text(encoding="utf-8")
    assert "SQ_OK" in js
    assert "\\uD83D\\uDFE9" in js
    assert "🟩" not in js
    assert "data-grid-suggestions" not in js
    assert "c.uf" not in js
    assert 'href="/grid"' in (
        ROOT_DIR / "templates" / "partials" / "admin_sidebar.html"
    ).read_text(encoding="utf-8")
    assert 'href="/grid#ranking"' in (
        ROOT_DIR / "templates" / "partials" / "admin_sidebar.html"
    ).read_text(encoding="utf-8")

    hoje = client.get("/grid/api/hoje")
    assert hoje.status_code == 200
    data = hoje.json()
    assert data["puzzle"]["tamanho"] == 3
    assert data["puzzle"]["rotulo"]
    assert isinstance(data["puzzle"]["virada_em_ms"], int)
    assert data["pode_salvar"] is True

    puzzle = data["puzzle"]
    row = categoria_por_id(puzzle["linhas"][0]["id"])
    col = categoria_por_id(puzzle["colunas"][0]["id"])
    assert row and col
    clube = pool_celula(row, col)[0]

    # 1–2 letras: API não devolve sugestões
    curto = client.get(
        "/grid/api/buscar",
        params={"linha": 0, "coluna": 0, "q": clube["nome"][:1]},
    )
    assert curto.status_code == 200
    assert curto.json()["itens"] == []

    busca = client.get(
        "/grid/api/buscar",
        params={"linha": 0, "coluna": 0, "q": clube["nome"][:3]},
    )
    assert busca.status_code == 200
    assert busca.json()["pronto"] is True
    assert busca.json()["itens"] == []
    assert busca.json().get("sugestoes") is False

    chute = client.post(
        "/grid/api/chute",
        json={"linha": 0, "coluna": 0, "nome": clube["nome"]},
    )
    assert chute.status_code == 200
    body = chute.json()
    assert body["resultado"]["ok"] is True
    assert body["celulas"][0][0]["clube"]["id"] == clube["id"]

    chute2 = client.post(
        "/grid/api/chute",
        json={"linha": 0, "coluna": 0, "nome": clube["nome"]},
    )
    assert chute2.status_code == 409


def _celula_ok(clube_id: str = "1") -> dict:
    return {"ok": True, "clube": {"id": clube_id, "nome": "Clube X"}}


def test_grid_reset_lancamento_zera_progresso(client: TestClient):
    from src import db as dbmod

    part = dbmod.criar_participante("Reset Grid", status="liberado", celular="11991112202")
    full = [[_celula_ok(str(i * 3 + j)) for j in range(3)] for i in range(3)]
    dbmod.salvar_grid_progresso(part["id"], "2026-08-09", full, finalizado=True)
    assert dbmod.ranking_grid()
    assert dbmod.limpar_grid_progresso() >= 1
    assert dbmod.ranking_grid() == []
    assert dbmod.grid_stats_participante(part["id"])["jogou"] is False


def test_chute_errado_marca_miss():
    puzzle = gerar_puzzle("2026-08-15")
    row = categoria_por_id(puzzle["linhas"][0]["id"])
    col = categoria_por_id(puzzle["colunas"][0]["id"])
    assert row and col
    pool_ids = {c["id"] for c in pool_celula(row, col)}
    outro = next(c for c in clubes_grid() if c["id"] not in pool_ids)
    res = validar_chute(dia="2026-08-15", linha=0, coluna=0, clube_id=outro["id"])
    assert res["ok"] is False


def test_texto_share_usa_verde_e_vermelho():
    celulas = [
        [{"ok": True, "clube": {"id": "1"}}, {"ok": False, "clube": {"id": "2"}}, None],
        [None, {"ok": True, "clube": {"id": "3"}}, {"ok": False, "clube": {"id": "4"}}],
        [None, None, None],
    ]
    text = texto_share(dia="2026-08-09", celulas=celulas)
    assert "🟩 🟥 ⬜" in text
    assert "⬜ 🟩 🟥" in text
    assert "⬛" not in text
    assert "2/9" in text
    assert "https://thdfm.com.br/grid" in text
    # bytes UTF-8 corretos dos quadrados (não latin-1)
    raw = text.encode("utf-8")
    assert "🟩".encode("utf-8") in raw
    assert "🟥".encode("utf-8") in raw


def test_resolver_clube_por_nome_sem_sugestoes():
    from src.grid_game import resolver_clube_por_nome

    clube = clubes_grid()[0]
    hit = resolver_clube_por_nome(clube["nome"])
    assert hit["id"] == clube["id"]
    try:
        resolver_clube_por_nome("xyzclubeinexistente999")
        assert False, "deveria falhar"
    except ValueError as exc:
        assert "não encontrado" in str(exc).casefold() or "nao encontrado" in str(exc).casefold()


def test_ranking_e_stats_grid(client: TestClient):
    from src import db as dbmod

    a = dbmod.criar_participante("Grid Ace", status="liberado", celular="11991110001")
    b = dbmod.criar_participante("Grid Rookie", status="liberado", celular="11991110002")
    full = [[_celula_ok(str(i * 3 + j)) for j in range(3)] for i in range(3)]
    half = [[_celula_ok("9") if (i, j) == (0, 0) else None for j in range(3)] for i in range(3)]

    dbmod.salvar_grid_progresso(a["id"], "2026-08-08", full, finalizado=True)
    dbmod.salvar_grid_progresso(a["id"], "2026-08-09", full, finalizado=True)
    dbmod.salvar_grid_progresso(b["id"], "2026-08-09", half, finalizado=False)

    ranking = dbmod.ranking_grid(limite=10)
    assert ranking[0]["participante_id"] == a["id"]
    assert ranking[0]["dias_finalizados"] == 2
    assert ranking[0]["celulas_ok"] == 18
    assert ranking[1]["participante_id"] == b["id"]
    assert ranking[1]["dias_finalizados"] == 0
    assert ranking[1]["celulas_ok"] == 1

    stats_a = dbmod.grid_stats_participante(a["id"])
    assert stats_a["jogou"] is True
    assert stats_a["dias_finalizados"] == 2
    assert stats_a["posicao"] == 1
    assert stats_a["taxa"] == 100

    stats_b = dbmod.grid_stats_participante(b["id"])
    assert stats_b["posicao"] == 2
    assert stats_b["celulas_preenchidas"] == 1


def test_perfil_mostra_bloco_grid(client: TestClient):
    from src import db as dbmod

    part = dbmod.criar_participante("Perfil Grid", status="liberado", celular="11991110003")
    dbmod.definir_credenciais(part["id"], "perfil.grid", "senha12345")
    client.get(f"/p/{part['token']}")

    full = [[_celula_ok(str(i * 3 + j)) for j in range(3)] for i in range(3)]
    dbmod.salvar_grid_progresso(part["id"], "2026-08-09", full, finalizado=True)

    r = client.get("/meu-perfil")
    assert r.status_code == 200
    assert 'id="grid"' in r.text
    assert "THDFM Grid" in r.text
    assert "Dias zerados" in r.text
    assert 'href="/grid#ranking"' in r.text


def test_grid_ranking_inline_e_redirect(client: TestClient):
    r_guest = client.get("/grid/ranking", follow_redirects=False)
    assert r_guest.status_code in (303, 302)
    assert "acesso=entrar" in (r_guest.headers.get("location") or "")

    from src import db as dbmod

    part = dbmod.criar_participante("Rank Viewer", status="liberado", celular="11991110004")
    dbmod.definir_credenciais(part["id"], "rank.viewer", "senha12345")
    client.get(f"/p/{part['token']}")

    r_redir = client.get("/grid/ranking", follow_redirects=False)
    assert r_redir.status_code in (303, 302)
    loc = r_redir.headers.get("location") or ""
    assert "/grid" in loc
    assert "#ranking" in loc

    full = [[_celula_ok("1") for _ in range(3)] for _ in range(3)]
    dbmod.salvar_grid_progresso(part["id"], "2026-08-09", full, finalizado=True)

    r = client.get("/grid")
    assert r.status_code == 200
    assert 'id="ranking"' in r.text
    assert "Rank Viewer" in r.text
    assert "Dias" in r.text
    assert 'href="#ranking"' in r.text
    assert "grid-result-top" in r.text
    assert "grid-share-actions" in r.text
