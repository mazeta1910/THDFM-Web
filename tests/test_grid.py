"""THDFM Grid — puzzle diário privado (Mazeta)."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from src.config import ROOT_DIR
from src.grid_game import (
    DENSIDADE_MIN,
    GRID_HISTORICO_DESDE,
    GRID_VARIEDADE_DESDE,
    TZ_SP,
    categoria_por_id,
    categorias_disponiveis,
    clubes_grid,
    clubes_por_id,
    dia_grid,
    gerar_puzzle,
    historico_ativo,
    ms_ate_proxima_virada,
    pool_celula,
    texto_share,
    validar_chute,
    variedade_ativa,
)
from src.grid_historico import historico_serie_a
from tests.conftest import login_admin

# Puzzle clássico congelado: categorias históricas não podem alterar o dia anterior ao cutover.
# Após strip de prefixos FC/SC/EC o pool de letras muda e o seed v1 produz este board.
_PUZZLE_2026_08_10 = {
    "dia": "2026-08-10",
    "linhas": [
        {"id": "serie:SEM", "tipo": "serie", "valor": "SEM", "rotulo": "Sem divisão nacional"},
        {"id": "regiao:Norte", "tipo": "regiao", "valor": "Norte", "rotulo": "Região Norte"},
        {"id": "serie:D", "tipo": "serie", "valor": "D", "rotulo": "Brasileirão Série D"},
    ],
    "colunas": [
        {"id": "letra:A", "tipo": "letra", "valor": "A", "rotulo": "Nome começa com A"},
        {"id": "letra:C", "tipo": "letra", "valor": "C", "rotulo": "Nome começa com C"},
        {"id": "letra:I", "tipo": "letra", "valor": "I", "rotulo": "Nome começa com I"},
    ],
}


def test_gerar_puzzle_deterministico_e_denso():
    a = gerar_puzzle("2026-08-10")
    b = gerar_puzzle("2026-08-10")
    assert a == b
    assert a["tamanho"] == 3
    assert len(a["linhas"]) == 3
    assert len(a["colunas"]) == 3
    for row in a["densidades"]:
        assert all(n >= DENSIDADE_MIN for n in row)
    # Eixos do dia pré-cutover permanecem idênticos ao pool clássico
    assert a["linhas"] == _PUZZLE_2026_08_10["linhas"]
    assert a["colunas"] == _PUZZLE_2026_08_10["colunas"]


def test_gerar_puzzle_nunca_quebra_dias_dificeis():
    """Dias em que o legado sozinho falhava ainda precisam devolver grade."""
    from datetime import date, timedelta

    # Amostra inclui datas que antes estouravam RuntimeError no legado
    dias = ["2026-08-11", "2026-08-17", "2026-08-18", "2026-08-27", "2026-09-03"]
    base = date(2026, 8, 11)
    for i in range(25):
        dias.append((base + timedelta(days=i)).isoformat())
    for dia in dias:
        p = gerar_puzzle(dia)
        assert p["dia"] == dia
        assert len(p["linhas"]) == 3 and len(p["colunas"]) == 3
        for row in p["densidades"]:
            assert all(n >= DENSIDADE_MIN for n in row)
        assert gerar_puzzle(dia) == p


def test_categorias_historicas_so_apos_cutover_meia_noite():
    assert GRID_HISTORICO_DESDE == "2026-08-11"
    assert historico_ativo("2026-08-10") is False
    assert historico_ativo("2026-08-11") is True

    cats_antes = {c.id for c in categorias_disponiveis("2026-08-10")}
    cats_depois = {c.id for c in categorias_disponiveis("2026-08-11")}
    assert "titulo:campeao_br" not in cats_antes
    assert "premio:melhor_ataque" not in cats_antes
    assert "titulo:campeao_br" in cats_depois
    assert "premio:artilheiro" in cats_depois
    # Terminações (letra/sílaba) entram no pool clássico
    assert "termina:ense" in cats_antes
    assert "termina:A" in cats_antes

    hist = historico_serie_a()
    assert len(hist.get("titulo:campeao_br") or []) >= DENSIDADE_MIN
    assert len(hist.get("premio:melhor_ataque") or []) >= DENSIDADE_MIN
    # Novas categorias (classificação + goleadas)
    for key in (
        "premio:pior_defesa",
        "premio:mais_vitorias",
        "premio:mais_empates",
        "premio:mais_derrotas",
        "premio:rebaixado",
        "premio:g4",
        "premio:melhor_defesa",
        "goleada:presente",
        "goleada:aplicou",
        "goleada:sofreu",
    ):
        assert len(hist.get(key) or []) >= DENSIDADE_MIN, key
        assert key in cats_depois

    # Subconjuntos de goleada (ao longo das edições; um clube pode aplicar e sofrer em anos distintos)
    assert hist["goleada:aplicou"] <= hist["goleada:presente"]
    assert hist["goleada:sofreu"] <= hist["goleada:presente"]
    assert hist["goleada:aplicou"] | hist["goleada:sofreu"] == hist["goleada:presente"]

    p = gerar_puzzle("2026-08-11")
    assert p["dia"] == "2026-08-11"
    for row in p["densidades"]:
        assert all(n >= DENSIDADE_MIN for n in row)


def test_novas_categorias_historicas_aparecem_no_pool():
    from src.grid_historico import HISTORICO_META, historico_meta, limpar_caches_historico

    limpar_caches_historico()
    from src.grid_game import categorias_disponiveis

    categorias_disponiveis.cache_clear()
    cats = {c.id: c for c in categorias_disponiveis("2026-08-12")}
    ids_meta = {m[0] for m in historico_meta()}
    assert "goleada:aplicou" in ids_meta
    assert "premio:rebaixado" in ids_meta
    assert "titulo:campeao_serie_b" in ids_meta
    assert "participacao:serie_c" in ids_meta
    assert "titulo:campeao_cdb" in ids_meta
    assert "participacao:serie_d" not in ids_meta  # sem CSV local de Série D
    assert cats["goleada:aplicou"].rotulo.startswith("Já aplicou")
    assert cats["titulo:campeao_serie_b"].rotulo.startswith("Já foi campeão da Série B")
    assert cats["titulo:campeao_cdb"].tipo == "titulo"
    hist = historico_serie_a()
    for cid, _tipo, _val, _rot in historico_meta():
        assert cid in cats, cid
        assert len(hist.get(cid) or []) >= DENSIDADE_MIN, (cid, len(hist.get(cid) or []))
    # base antiga continua coberta
    for cid, *_ in HISTORICO_META:
        assert cid in ids_meta


def test_filtros_negacao_uf_regiao_e_nunca_historico():
    """Gentílico UF, não-UF, não-região e 'nunca…' históricos."""
    from src.grid_historico import limpar_caches_historico

    limpar_caches_historico()
    categorias_disponiveis.cache_clear()
    clubes_grid.cache_clear()

    cats = {c.id: c for c in categorias_disponiveis("2026-08-12")}
    assert cats["uf:PR"].rotulo == "Time paranaense"
    assert cats["nao_uf:PR"].rotulo == "Não é paranaense"
    assert cats["nao_regiao:Sul"].rotulo == "Não é da região Sul"

    hist = historico_serie_a()
    assert not (hist["titulo:campeao_br"] & hist["titulo:nunca_campeao_br"])
    assert "premio:nunca_rebaixado" in cats


def test_filtros_nome_e_compostos_historicos():
    """Nome (vogal/KWY/tamanho/letras) + compostos históricos densos."""
    from src.grid_historico import limpar_caches_historico

    limpar_caches_historico()
    categorias_disponiveis.cache_clear()
    clubes_grid.cache_clear()

    cats = {c.id: c for c in categorias_disponiveis("2026-08-12")}
    for key in (
        "nome:vogal",
        "nome:kwy",
        "nome:curto",
        "nome:longo",
        "nome:nv:4",
        "nome:nc:5",
        "nome:tem:a",
        "nome:nao:x",
        "premio:g4_sem_titulo",
        "titulo:vice_sem_campeao",
        "titulo:nunca_campeao_cdb",
        "titulo:nunca_final_cdb",
        "premio:rebaixado_2x",
        "longevidade:serie_b_3",
        "longevidade:serie_a_le_5",
        "longevidade:serie_b_le_3",
        "longevidade:serie_c_le_3",
        "participacao:serie_a_dec_1990",
        "participacao:serie_a_antes_2003",
        "participacao:serie_a_seq_2024_2025",
    ):
        assert key in cats, key

    assert cats["participacao:serie_a_seq_2024_2025"].rotulo == (
        "Jogou a Série A em todos os anos de 2024 a 2025"
    )
    assert "seq" not in cats["participacao:serie_a_seq_2024_2025"].rotulo.casefold()
    assert cats["longevidade:serie_a_le_5"].rotulo == "≤5 participações na Série A"
    assert cats["longevidade:serie_c_le_2"].rotulo == "≤2 participações na Série C"

    hist = historico_serie_a()
    assert hist["premio:g4_sem_titulo"].isdisjoint(hist["titulo:campeao_br"])
    assert hist["titulo:vice_sem_campeao"].isdisjoint(hist["titulo:campeao_br"])

    from src.grid_game import clube_bate_categoria

    vogal = cats["nome:vogal"]
    curto = cats["nome:curto"]
    sample = next(c for c in clubes_grid() if clube_bate_categoria(c, vogal))
    assert sample["nome_core"][0] in "aeiou"
    sample2 = next(c for c in clubes_grid() if clube_bate_categoria(c, curto))
    assert sample2["nome_tam"] <= 6


def test_categorias_serie_b_c_e_copa_densas():
    """Categorias B/C/Copa vêm dos CSV/XLSX locais em data/torneios (sem scrape)."""
    from src.grid_historico import limpar_caches_historico

    limpar_caches_historico()
    hist = historico_serie_a()
    for key in (
        "titulo:campeao_serie_b",
        "titulo:vice_serie_b",
        "premio:g4_serie_b",
        "premio:melhor_defesa_serie_b",
        "premio:mais_vitorias_serie_b",
        "premio:rebaixado_serie_b",
        "participacao:serie_b",
        "goleada:aplicou_serie_b",
        "titulo:campeao_serie_c",
        "premio:g4_serie_c",
        "premio:melhor_defesa_serie_c",
        "titulo:campeao_cdb",
        "titulo:vice_cdb",
        "goleada:presente_cdb",
    ):
        assert len(hist.get(key) or []) >= DENSIDADE_MIN, key
    assert "titulo:campeao_serie_d" not in hist


def test_variedade_cutover_e_eixos_mistos():
    from src.grid_game import _subgrupo_categoria, categoria_por_id

    assert GRID_VARIEDADE_DESDE == "2026-08-12"
    assert variedade_ativa("2026-08-11") is False
    assert variedade_ativa("2026-08-12") is True

    legado = gerar_puzzle("2026-08-11")
    assert legado["dia"] == "2026-08-11"

    tipos_vistos: set[str] = set()
    familias_por_dia: list[int] = []
    ids_vistos: set[str] = set()
    n_uf = 0
    n_nao_uf = 0
    n_serie_c = 0
    from src.grid_game import _categoria_serie_c

    for i in range(36):
        dia = f"2026-09-{i + 1:02d}" if i < 30 else f"2026-10-{i - 29:02d}"
        p = gerar_puzzle(dia)
        assert p["tamanho"] == 3
        for row in p["densidades"]:
            assert all(n >= DENSIDADE_MIN for n in row)

        for eixo in (p["linhas"], p["colunas"]):
            tipos = [c["tipo"] for c in eixo]
            cont = Counter(tipos)
            assert len(cont) >= 2, (dia, eixo)
            assert cont.get("termina", 0) <= 1, (dia, eixo)
            assert cont.get("letra", 0) <= 1, (dia, eixo)
            assert cont.get("regiao", 0) <= 1, (dia, eixo)
            n_nome = cont.get("letra", 0) + cont.get("termina", 0) + cont.get("nome", 0)
            assert n_nome <= 1, (dia, eixo)
            assert not all(t in ("letra", "termina", "nome") for t in tipos), (dia, eixo)

            # ≤1 categoria por subgrupo semântico no mesmo eixo
            cats = [categoria_por_id(c["id"], dia) for c in eixo]
            assert all(c is not None for c in cats), (dia, eixo)
            subs = [_subgrupo_categoria(c) for c in cats]
            assert len(subs) == len(set(subs)), (dia, eixo, subs)

        board = p["linhas"] + p["colunas"]
        n_nome_board = sum(1 for c in board if c["tipo"] in ("letra", "termina", "nome"))
        assert n_nome_board <= 2, (dia, n_nome_board)
        tipos_all = {c["tipo"] for c in board}
        assert len(tipos_all) >= 4, (dia, tipos_all)

        for c in board:
            if c["tipo"] == "uf":
                n_uf += 1
            elif c["tipo"] == "nao_uf":
                n_nao_uf += 1
            cat = categoria_por_id(c["id"], dia)
            assert cat is not None
            if _categoria_serie_c(cat):
                n_serie_c += 1

        def _fam(t: str) -> str:
            if t in ("letra", "termina", "nome"):
                return "nome"
            if t in ("uf", "nao_uf", "regiao", "nao_regiao", "serie"):
                return "geo"
            if t in {
                "titulo",
                "premio",
                "participacao",
                "longevidade",
                "paridade",
                "goleada",
            }:
                return "hist"
            return t

        familias = {_fam(t) for t in tipos_all}
        assert len(familias) >= 2, (dia, familias)
        familias_por_dia.append(len(familias))
        tipos_vistos |= tipos_all
        ids_vistos |= {c["id"] for c in board}
        assert gerar_puzzle(dia) == p

    # Cobertura ampla: nomes, geo e histórico aparecem ao longo dos dias
    assert tipos_vistos & {"letra", "termina", "nome"}
    assert tipos_vistos & {"uf", "regiao", "serie", "nao_uf", "nao_regiao"}
    assert tipos_vistos & {
        "titulo",
        "premio",
        "participacao",
        "longevidade",
        "paridade",
        "goleada",
    }
    assert len(tipos_vistos) >= 7
    assert len(ids_vistos) >= 25
    assert max(familias_por_dia) >= 3

    # Preferência de sorteio: UF positiva > “Não é…”, e Série C aparece mais
    assert n_uf > n_nao_uf, (n_uf, n_nao_uf)
    assert n_serie_c >= 10, n_serie_c


def test_subgrupos_semanticos_basicos():
    from src.grid_game import Categoria, _subgrupo_categoria

    assert (
        _subgrupo_categoria(Categoria("nao_uf:SP", "nao_uf", "SP", "Não é paulista"))
        == "geo_neg"
    )
    assert (
        _subgrupo_categoria(
            Categoria("nao_regiao:Sul", "nao_regiao", "Sul", "Não é da região Sul")
        )
        == "geo_neg"
    )
    assert (
        _subgrupo_categoria(Categoria("uf:RJ", "uf", "RJ", "Time carioca")) == "geo_pos"
    )
    assert (
        _subgrupo_categoria(
            Categoria("titulo:a", "titulo", "a", "Já foi campeão do Brasileirão")
        )
        == "hist_ja"
    )
    assert (
        _subgrupo_categoria(
            Categoria("premio:b", "premio", "b", "Já teve artilheiro do Brasileirão")
        )
        == "hist_ja"
    )
    assert (
        _subgrupo_categoria(
            Categoria("titulo:c", "titulo", "c", "Nunca foi campeão do Brasileirão")
        )
        == "hist_nunca"
    )
    assert (
        _subgrupo_categoria(
            Categoria("longevidade:d", "longevidade", "d", "≥5 participações na Série B")
        )
        == "hist_contagem"
    )
    assert (
        _subgrupo_categoria(
            Categoria("participacao:e", "participacao", "e", "Disputou a Série A nos anos 90")
        )
        == "hist_era"
    )

def test_categoria_termina_com_letra_e_silaba():
    from src.grid_game import Categoria, categorias_compativeis, clube_bate_categoria

    ense = categoria_por_id("termina:ense", "2026-08-10")
    assert ense is not None
    assert ense.rotulo == "Nome termina com ense"
    letra_e = categoria_por_id("termina:E", "2026-08-10")
    assert letra_e is not None

    bateu = False
    for c in clubes_grid():
        if clube_bate_categoria(c, ense):
            assert c["nome_core"].endswith("ense")
            assert clube_bate_categoria(c, letra_e)
            bateu = True
            break
    assert bateu

    assert categorias_compativeis(ense, letra_e) is True
    assert categorias_compativeis(
        ense, Categoria("termina:A", "termina", "A", "Nome termina com A")
    ) is False
    assert categorias_compativeis(
        Categoria("termina:eiro", "termina", "eiro", "x"),
        Categoria("termina:iro", "termina", "iro", "y"),
    ) is True


def test_virada_meia_noite_sao_paulo():
    antes = datetime(2026, 8, 10, 23, 59, 30, tzinfo=TZ_SP)
    depois = datetime(2026, 8, 11, 0, 0, 0, tzinfo=TZ_SP)
    assert dia_grid(antes, hora_virada=0) == "2026-08-10"
    assert dia_grid(depois, hora_virada=0) == "2026-08-11"
    assert gerar_puzzle(dia_grid(antes, hora_virada=0)) != gerar_puzzle(
        dia_grid(depois, hora_virada=0)
    )

    ms = ms_ate_proxima_virada(antes, hora_virada=0)
    assert 0 < ms <= 30_000 + 50
    assert ms_ate_proxima_virada(depois, hora_virada=0) > 23 * 60 * 60 * 1000

    # UTC 03:00 == 00:00 SP (sem horário de verão)
    utc = ZoneInfo("UTC")
    assert (
        dia_grid(datetime(2026, 8, 11, 2, 59, tzinfo=utc), hora_virada=0) == "2026-08-10"
    )
    assert (
        dia_grid(datetime(2026, 8, 11, 3, 0, tzinfo=utc), hora_virada=0) == "2026-08-11"
    )

    # Virada às 18:00: antes = dia civil; na virada abre o puzzle do dia seguinte
    tarde = datetime(2026, 8, 11, 17, 59, tzinfo=TZ_SP)
    noite = datetime(2026, 8, 11, 18, 0, tzinfo=TZ_SP)
    assert dia_grid(tarde, hora_virada=18) == "2026-08-11"
    assert dia_grid(noite, hora_virada=18) == "2026-08-12"
    ms18 = ms_ate_proxima_virada(tarde, hora_virada=18)
    assert 0 < ms18 <= 60_000 + 50

    # HH:MM livre — 18:30
    quase = datetime(2026, 8, 11, 18, 29, tzinfo=TZ_SP)
    pos = datetime(2026, 8, 11, 18, 30, tzinfo=TZ_SP)
    assert dia_grid(quase, hora_virada="18:30") == "2026-08-11"
    assert dia_grid(pos, hora_virada="18:30") == "2026-08-12"
    assert 0 < ms_ate_proxima_virada(quase, hora_virada=(18, 30)) <= 60_000 + 50

    # Caso do bug: 22:20 no dia 10 deve abrir o puzzle 11/08
    assert (
        dia_grid(datetime(2026, 8, 10, 22, 19, tzinfo=TZ_SP), hora_virada="22:20")
        == "2026-08-10"
    )
    assert (
        dia_grid(datetime(2026, 8, 10, 22, 20, tzinfo=TZ_SP), hora_virada="22:20")
        == "2026-08-11"
    )
    assert (
        dia_grid(datetime(2026, 8, 10, 22, 22, tzinfo=TZ_SP), hora_virada="22:20")
        == "2026-08-11"
    )


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
    assert 'id="grid-admin"' not in r.text
    assert "Painel do Grid" not in r.text
    api = client.get("/grid/api/hoje")
    assert api.status_code == 200
    assert api.json()["pode_salvar"] is True


def test_grid_admin_so_mazeta(client: TestClient):
    from src import db as dbmod

    part = dbmod.criar_participante("Admin Grid", status="liberado", celular="11991112299")
    dbmod.definir_credenciais(part["id"], "grid.admin.user", "senha12345")
    client.get(f"/p/{part['token']}")

    r = client.get("/grid/api/admin/resumo")
    assert r.status_code == 403

    login_admin(client)
    ok = client.get("/grid/api/admin/resumo")
    assert ok.status_code == 200
    data = ok.json()
    assert data["puzzle"]["tamanho"] == 3
    assert "virada_hora" in data
    assert isinstance(data["dias"], list)
    assert isinstance(data["respostas"], list)

    virada = client.post("/grid/api/admin/virada", json={"hora": "18:30"})
    assert virada.status_code == 200
    assert virada.json()["virada_hora"] == 18
    assert virada.json()["virada_minuto"] == 30
    assert virada.json()["virada_rotulo"] == "18:30"
    assert dbmod.get_grid_virada_hm() == (18, 30)
    assert dbmod.get_grid_virada_hora() == 18

    # Compat: int ainda funciona (= :00)
    virada_int = client.post("/grid/api/admin/virada", json={"hora": 19})
    assert virada_int.status_code == 200
    assert virada_int.json()["virada_rotulo"] == "19:00"

    bad = client.post("/grid/api/admin/virada", json={"hora": "25:00"})
    assert bad.status_code == 400
    bad2 = client.post("/grid/api/admin/virada", json={"hora": "abc"})
    assert bad2.status_code == 400

    client.post("/grid/api/admin/virada", json={"hora": "18:30"})
    assert dbmod.get_grid_virada_hm() == (18, 30)

    dia = data["dia"]
    antes = gerar_puzzle(dia)
    regen = client.post(
        "/grid/api/admin/regenerar",
        json={"dia": dia, "limpar_progresso": True},
    )
    assert regen.status_code == 200
    body = regen.json()
    assert body["ok"] is True
    assert body["salt"]
    depois = gerar_puzzle(dia)
    assert depois["linhas"] != antes["linhas"] or depois["colunas"] != antes["colunas"]

    full = [
        [{"ok": True, "clube": {"id": "1", "nome": "A", "uf": "SP", "emblema": None}}]
        * 3
        for _ in range(3)
    ]
    # estrutura 3x3 correta
    full = [[full[0][0] for _ in range(3)] for _ in range(3)]
    dbmod.salvar_grid_progresso(part["id"], dia, full, finalizado=True)
    resumo = client.get(f"/grid/api/admin/resumo?dia={dia}")
    assert resumo.status_code == 200
    nomes = [x["nome"] for x in resumo.json()["respostas"]]
    assert "Admin Grid" in nomes

    rest = client.post(
        "/grid/api/admin/regenerar",
        json={"dia": dia, "restaurar": True, "limpar_progresso": True},
    )
    assert rest.status_code == 200
    assert rest.json()["restaurado"] is True
    assert gerar_puzzle(dia) == antes
    assert dbmod.get_grid_virada_hm() == (18, 30)
    client.post("/grid/api/admin/virada", json={"hora": "00:00"})


def test_grid_fluxo_logado(client: TestClient):
    login_admin(client)
    r = client.get("/grid")
    assert r.status_code == 200
    assert "THDFM Grid" in r.text
    assert "Puzzle diário" in r.text
    assert 'id="thdfm-grid"' in r.text
    assert "/static/grid.js?v=13" in r.text
    assert "data-virada-ms=" in r.text
    assert "vira às 00:00 (Brasília)" in r.text
    assert 'id="grid-admin"' in r.text
    assert 'data-grid-admin' in r.text
    assert "/static/grid-admin.js?v=3" in r.text
    assert "Painel do Grid" in r.text
    assert 'data-grid-admin-hist' in r.text
    assert "grid-admin-ico" in r.text
    assert 'type="text"' in r.text
    assert 'placeholder="HH:MM"' in r.text
    assert "Salvar hora" not in r.text or 'aria-label="Salvar hora"' in r.text
    assert 'data-grid-daltonismo' in r.text
    assert 'data-daltonismo="protanopia"' in r.text
    assert 'data-daltonismo="deuteranopia"' in r.text
    assert 'data-daltonismo="tritanopia"' in r.text
    assert "data-grid-share-wa" in r.text
    assert "aria-label=\"Compartilhar no WhatsApp\"" in r.text
    assert "WhatsApp</button>" not in r.text
    assert 'id="ranking"' in r.text
    assert "grid-result-top" in r.text
    assert "data-grid-chute" in r.text
    assert "data-grid-suggestions" in r.text
    assert "~70%" in r.text
    assert 'href="#ranking"' not in r.text
    assert "data-grid-streak" in r.text
    assert "grid-title" in r.text
    css = (ROOT_DIR / "static" / "style.css").read_text(encoding="utf-8")
    assert ".grid-share-text" in css
    assert "text-align: center" in css.split(".grid-share-text", 1)[1].split("}", 1)[0]
    assert '.grid-page[data-daltonismo-mode="protanopia"]' in css
    assert "button.grid-daltonismo-btn" in css
    assert ".grid-daltonismo-toggles" in css
    # Não pode herdar width:100% do button global
    dalton_btn_css = css.split("button.grid-daltonismo-btn", 1)[1].split("}", 1)[0]
    assert "width: auto" in dalton_btn_css
    assert "Jogos e Passatempos" in (
        ROOT_DIR / "templates" / "partials" / "site_sidebar.html"
    ).read_text(encoding="utf-8")
    site_side = (
        ROOT_DIR / "templates" / "partials" / "site_sidebar.html"
    ).read_text(encoding="utf-8")
    assert "Jogos e Passatempos" in site_side
    assert site_side.index("Jogos e Passatempos") < site_side.index("Bolão CdB")
    assert 'href="/grid"' in site_side
    assert "Ranking Grid" not in site_side
    # fora do submenu Bolão
    bolao_block = site_side.split('data-group="bolao"', 1)[1].split("</details>", 1)[0]
    assert "THDFM Grid" not in bolao_block
    assert "Ranking Grid" not in bolao_block
    js = (ROOT_DIR / "static" / "grid.js").read_text(encoding="utf-8")
    assert "SQ_OK" in js
    assert "\\uD83D\\uDFE9" in js
    assert "🟩" not in js
    assert "data-grid-suggestions" in js
    assert "c.uf" not in js
    assert "thdfm-grid-daltonismo" in js
    assert "aplicarDaltonismo" in js
    assert "data-daltonismo-mode" in js
    assert "clubeJaUsado" in js
    assert "já foi usado" in js
    assert "aplicarMiopia" not in js
    assert "data-miopia" not in js
    assert 'href="/grid"' in (
        ROOT_DIR / "templates" / "partials" / "admin_sidebar.html"
    ).read_text(encoding="utf-8")
    admin_side = (
        ROOT_DIR / "templates" / "partials" / "admin_sidebar.html"
    ).read_text(encoding="utf-8")
    assert "Ranking Grid" not in admin_side
    assert 'rel="icon" href="/static/img/thdfm-logo.png"' in r.text
    assert (ROOT_DIR / "static" / "img" / "thdfm-logo.png").is_file()
    fav = client.get("/favicon.ico")
    assert fav.status_code == 200
    assert fav.headers.get("content-type", "").startswith("image/png")

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
    from src.grid_game import min_chars_sugestao, nome_core_norm

    core = nome_core_norm(clube["nome_norm"])
    precisa = min_chars_sugestao(clube["nome_norm"])

    # Poucas letras: ainda sem sugestão (abaixo de 70%)
    curto_q = core[: max(1, precisa - 1)]
    curto = client.get(
        "/grid/api/buscar",
        params={"linha": 0, "coluna": 0, "q": curto_q},
    )
    assert curto.status_code == 200
    assert curto.json()["itens"] == [] or not any(
        x["id"] == clube["id"] for x in curto.json()["itens"]
    )

    # ~70% do nome: aparece no catálogo completo
    q70 = core[:precisa]
    busca = client.get(
        "/grid/api/buscar",
        params={"linha": 0, "coluna": 0, "q": q70},
    )
    assert busca.status_code == 200
    assert busca.json()["pronto"] is True
    assert busca.json().get("sugestoes") is True
    assert any(x["id"] == clube["id"] for x in busca.json()["itens"])
    assert "uf" not in (busca.json()["itens"][0] or {})

    chute = client.post(
        "/grid/api/chute",
        json={"linha": 0, "coluna": 0, "clube_id": clube["id"]},
    )
    assert chute.status_code == 200
    body = chute.json()
    assert body["resultado"]["ok"] is True
    assert body["celulas"][0][0]["clube"]["id"] == clube["id"]

    chute2 = client.post(
        "/grid/api/chute",
        json={"linha": 0, "coluna": 0, "clube_id": clube["id"]},
    )
    assert chute2.status_code == 409


def _celula_ok(clube_id: str = "1", *, rep: int | None = None) -> dict:
    clube: dict = {"id": clube_id, "nome": "Clube X"}
    if rep is not None:
        clube["rep"] = rep
    return {"ok": True, "clube": clube}


def test_ranking_desempate_por_rep_baixa():
    """Com mesmos dias/acertos/streak, quem acertou times com menor Rep FM fica na frente."""
    from src import db as dbmod
    from src.clubes_catalogo import pontos_rep_desempate

    assert pontos_rep_desempate(400) > pontos_rep_desempate(7750)

    a = dbmod.criar_participante("Grid Obscuro", status="liberado", celular="11991110011")
    b = dbmod.criar_participante("Grid Famoso", status="liberado", celular="11991110012")
    # Mesmo dia finalizado, 9 acertos cada; A usou times fracos, B usou elite.
    full_a = [[_celula_ok(f"a{i}{j}", rep=200) for j in range(3)] for i in range(3)]
    full_b = [[_celula_ok(f"b{i}{j}", rep=7500) for j in range(3)] for i in range(3)]
    dbmod.salvar_grid_progresso(a["id"], "2026-08-09", full_a, finalizado=True)
    dbmod.salvar_grid_progresso(b["id"], "2026-08-09", full_b, finalizado=True)

    ranking = dbmod.ranking_grid(limite=10)
    assert ranking[0]["participante_id"] == a["id"]
    assert ranking[1]["participante_id"] == b["id"]
    assert ranking[0]["pontos_rep"] > ranking[1]["pontos_rep"]
    assert ranking[0]["dias_finalizados"] == ranking[1]["dias_finalizados"] == 1
    assert ranking[0]["celulas_ok"] == ranking[1]["celulas_ok"] == 9


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


def test_clube_ja_usado_no_grid():
    from src.grid_game import clube_ja_usado_no_grid

    celulas = [
        [{"ok": True, "clube": {"id": "10", "nome": "A"}}, None, None],
        [None, {"ok": False, "clube": {"id": "20", "nome": "B"}}, None],
        [None, None, None],
    ]
    assert clube_ja_usado_no_grid(celulas, "10") is True
    assert clube_ja_usado_no_grid(celulas, "20") is True
    assert clube_ja_usado_no_grid(celulas, "99") is False
    assert clube_ja_usado_no_grid(celulas, "") is False


def test_chute_clube_repetido_nao_preenche_celula(client: TestClient):
    """Estilo HoopsGrid: time já usado não entra no quadro (sem miss)."""
    login_admin(client)
    clube = next(c for c in clubes_grid())
    r1 = client.post(
        "/grid/api/chute",
        json={"linha": 0, "coluna": 0, "clube_id": clube["id"]},
    )
    assert r1.status_code == 200
    assert r1.json()["celulas"][0][0]["clube"]["id"] == clube["id"]

    # Mesmo time em outra célula: 400, quadro inalterado
    r2 = client.post(
        "/grid/api/chute",
        json={"linha": 0, "coluna": 1, "clube_id": clube["id"]},
    )
    assert r2.status_code == 400
    assert "já foi usado" in r2.json()["erro"].casefold()

    outro = next(c for c in clubes_grid() if c["id"] != clube["id"])
    r3 = client.post(
        "/grid/api/chute",
        json={"linha": 0, "coluna": 1, "clube_id": outro["id"]},
    )
    assert r3.status_code == 200
    body = r3.json()
    assert body["celulas"][0][0]["clube"]["id"] == clube["id"]
    assert body["celulas"][0][1]["clube"]["id"] == outro["id"]
    assert body["celulas"][0][1] is not None
    # Célula repetida ficou vazia no rechazo; agora tem o outro time
    assert body["celulas"][0][1]["clube"]["id"] != clube["id"]


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


def test_sugestao_exige_cerca_de_70_por_cento_do_nome():
    from src.grid_game import buscar_celula, min_chars_sugestao, nome_core_norm

    santos = next(c for c in clubes_grid() if c["nome_norm"] == "santos")
    precisa = min_chars_sugestao(santos["nome_norm"])
    assert precisa == 5  # ceil(6 * 0.7)

    dia = "2026-08-10"
    cedo = buscar_celula(dia=dia, linha=0, coluna=0, q="sant")
    assert all(x["id"] != santos["id"] for x in cedo["itens"])

    ok = buscar_celula(dia=dia, linha=0, coluna=0, q="santo")  # 5/6
    assert any(x["id"] == santos["id"] for x in ok["itens"])

    # Barcelona (RJ): core=barcelona (9) → precisa 7
    barca = next(c for c in clubes_grid() if c["nome_norm"] == "barcelona (rj)")
    assert min_chars_sugestao(barca["nome_norm"]) == 7
    assert nome_core_norm(barca["nome_norm"]) == "barcelona"
    cedo_b = buscar_celula(dia=dia, linha=0, coluna=0, q="barcel")  # 6
    assert all(x["id"] != barca["id"] for x in cedo_b["itens"])
    ok_b = buscar_celula(dia=dia, linha=0, coluna=0, q="barcelo")  # 7
    assert any(x["id"] == barca["id"] for x in ok_b["itens"])


def test_chute_nome_inexistente_conta_como_erro(client: TestClient):
    login_admin(client)
    r = client.post(
        "/grid/api/chute",
        json={"linha": 0, "coluna": 0, "nome": "S. C. DA PEÇÁ"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["resultado"]["ok"] is False
    assert body["resultado"].get("inventado") is True
    assert body["resultado"]["clube"]["nome"] == "S. C. DA PEÇÁ"
    assert body["celulas"][0][0]["ok"] is False
    assert body["celulas"][0][0]["clube"]["nome"] == "S. C. DA PEÇÁ"

    # Célula já preenchida
    r2 = client.post(
        "/grid/api/chute",
        json={"linha": 0, "coluna": 0, "nome": "B. C. DO CURVEDO"},
    )
    assert r2.status_code == 409


def test_resolver_clube_por_nome_sem_sugestoes():
    from src.grid_game import resolver_clube_por_nome

    clube = next(c for c in clubes_grid() if c["nome_norm"] == "santos")
    hit = resolver_clube_por_nome("Santos")
    assert hit["id"] == clube["id"]
    try:
        resolver_clube_por_nome("xyzclubeinexistente999")
        assert False, "deveria falhar"
    except ValueError as exc:
        assert "não encontrado" in str(exc).casefold() or "lista" in str(exc).casefold()


def test_busca_e_chute_ignoram_acentos():
    """Galícia deve aparecer/resolver com 'Galicia' (sem acento)."""
    from src.grid_game import (
        buscar_celula,
        dia_grid,
        fold_txt,
        min_chars_sugestao,
        resolver_clube_por_nome,
    )

    clubes_grid.cache_clear()
    clubes_por_id.cache_clear()

    assert fold_txt("Galícia") == "galicia"
    galicia = next(c for c in clubes_grid() if c["nome"] == "Galícia")
    assert galicia["nome_norm"] == "galicia"

    precisa = min_chars_sugestao(galicia["nome_norm"])
    q = "galicia"[:precisa]
    dia = dia_grid()
    sug = buscar_celula(dia=dia, linha=0, coluna=0, q=q)
    ids = {x["id"] for x in sug["itens"]}
    assert galicia["id"] in ids

    assert resolver_clube_por_nome("Galicia")["id"] == galicia["id"]
    assert resolver_clube_por_nome("GALÍCIA")["id"] == galicia["id"]


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
    assert ranking[0]["zona"] == "campeao"
    assert ranking[1]["participante_id"] == b["id"]
    assert ranking[1]["dias_finalizados"] == 0
    assert ranking[1]["celulas_ok"] == 1
    assert "zona" in ranking[1]
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
    assert 'href="#ranking"' not in r.text
    assert "data-grid-streak" in r.text
    assert "grid-share-actions" in r.text
    assert "grid-rank-crown" in r.text
    assert "zona-campeao" in r.text


def test_letra_ignora_prefixo_juridico_fc_sc_ec():
    from src.grid_game import (
        Categoria,
        clube_bate_categoria,
        clubes_grid,
        clubes_por_id,
        fold_txt,
        nome_sem_prefixo_juridico,
    )
    from src.clubes_catalogo import carregar_clubes

    carregar_clubes.cache_clear()
    clubes_grid.cache_clear()
    clubes_por_id.cache_clear()

    assert nome_sem_prefixo_juridico(fold_txt("FC Cascavel")) == "cascavel"
    assert nome_sem_prefixo_juridico(fold_txt("RB Bragantino")) == "rb bragantino"
    assert nome_sem_prefixo_juridico(fold_txt("XV de Piracicaba")) == "xv de piracicaba"

    cascavel = next(c for c in clubes_grid() if c["nome"] == "FC Cascavel")
    assert cascavel["letra"] == "C"
    assert cascavel["serie"] == "D"

    cat_c = Categoria("letra:C", "letra", "C", "Nome começa com C")
    cat_f = Categoria("letra:F", "letra", "F", "Nome começa com F")
    assert clube_bate_categoria(cascavel, cat_c) is True
    assert clube_bate_categoria(cascavel, cat_f) is False

    rb = next(c for c in clubes_grid() if c["nome"] == "RB Bragantino")
    assert rb["letra"] == "R"
    xv = next(c for c in clubes_grid() if "XV de Piracicaba" in c["nome"])
    assert xv["letra"] == "X"

    # Interseção letra C × Série D inclui FC Cascavel
    from src.grid_game import pool_celula

    serie_d = Categoria("serie:D", "serie", "D", "Brasileirão Série D")
    pool = pool_celula(cat_c, serie_d)
    assert any(c["id"] == cascavel["id"] for c in pool)


def test_grid_ranking_top5_ver_mais(client: TestClient):
    from src import db as dbmod

    login_admin(client)
    full = [[_celula_ok("1") for _ in range(3)] for _ in range(3)]
    for i in range(7):
        p = dbmod.criar_participante(
            f"Rank Top {i}", status="liberado", celular=f"1199222000{i}"
        )
        # Dias diferentes para ordenar estável
        for d in range(i + 1):
            dbmod.salvar_grid_progresso(
                p["id"], f"2026-07-{d + 1:02d}", full, finalizado=True
            )

    r = client.get("/grid")
    assert r.status_code == 200
    assert "data-grid-rank-mais" in r.text
    assert "Ver mais" in r.text
    assert "grid-rank-extra" in r.text
    assert r.text.count("grid-rank-extra") >= 2
    assert "grid-rank-crown" in r.text
