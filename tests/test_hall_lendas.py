"""Hall das Lendas — mural público + admin Mazeta."""

from __future__ import annotations

from fastapi.testclient import TestClient

from src import db as dbmod
from src.config import ROOT_DIR
from src.hall_lendas import format_valor_brl, parse_valor_centavos
from tests.conftest import login_admin


def _lenda(nome: str, celular: str, *, valor: str = "100,00", recado: str = "Valeu THDFM"):
    part = dbmod.criar_participante(nome, status="liberado", celular=celular)
    dbmod.upsert_hall_lenda(
        part["id"],
        valor_centavos_add=parse_valor_centavos(valor),
        recado=recado,
        borda="anel",
    )
    return part


def test_parse_e_format_valor():
    assert parse_valor_centavos("50") == 5000
    assert parse_valor_centavos("50,00") == 5000
    assert parse_valor_centavos("R$ 1.234,56") == 123456
    assert format_valor_brl(5000) == "R$ 50,00"


def test_hall_lendas_publico_sem_login(client: TestClient):
    a = _lenda("Ramos Lenda", "11990008001", valor="500,00", recado="Segue o baile")
    b = _lenda("João JEC", "11990008002", valor="200,00", recado="JEC eterno")

    r = client.get("/hall-lendas", follow_redirects=False)
    assert r.status_code == 200
    assert "Hall das Lendas" in r.text
    assert "Ramos Lenda" in r.text
    assert "João JEC" in r.text
    assert "Segue o baile" in r.text
    assert "hall-lendas-badge" in r.text
    assert "hall-lendas-avatar--anel" in r.text
    # Valores ocultos para o público
    assert "R$ 500,00" not in r.text
    assert "Total doado" not in r.text
    assert "Visão Mazeta" not in r.text
    assert "Protótipo" not in r.text
    assert "prévia só Mazeta" not in r.text
    assert "Protótipo visual" not in r.text
    # Ordenado por total (Ramos primeiro)
    assert r.text.index("Ramos Lenda") < r.text.index("João JEC")
    assert a and b


def test_hall_lendas_mazeta_ve_valores(client: TestClient):
    _lenda("Benevides Ouro", "11990008003", valor="80,00", recado="Apoio")
    login_admin(client)
    r = client.get("/hall-lendas")
    assert r.status_code == 200
    assert "Visão Mazeta" in r.text
    assert "Total doado" in r.text
    assert "R$ 80,00" in r.text
    assert "Gerenciar Hall" in r.text


def test_sidebar_hall_lendas_publico(client: TestClient):
    r = client.get("/")
    assert r.status_code == 200
    assert "Hall das Lendas" in r.text
    chunk = r.text.split("site-hall-lendas", 1)[1].split(">", 1)[0]
    assert 'href="/hall-lendas"' in chunk or 'href="/hall-lendas"' in r.text
    assert "disabled" not in chunk
    side = (ROOT_DIR / "templates" / "partials" / "site_sidebar.html").read_text(
        encoding="utf-8"
    )
    assert 'href="/hall-lendas"' in side
    assert "Em breve" not in side
    assert "{% if is_mazeta %}" not in side.split("site-hall-lendas", 1)[0][-80:] + side.split(
        "site-hall-lendas", 1
    )[1][:400]


def test_admin_hall_crud(client: TestClient):
    part = dbmod.criar_participante("Doador Admin", status="liberado", celular="11990008004")
    login_admin(client)

    r = client.get("/admin/hall-lendas")
    assert r.status_code == 200
    assert "Hall das Lendas" in r.text
    assert "Doador Admin" in r.text

    r = client.post(
        "/admin/hall-lendas/salvar",
        data={
            "modo": "doar",
            "participante_id": str(part["id"]),
            "valor": "150,00",
            "recado": "Primeira doação",
            "borda": "duplo",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    row = dbmod.get_hall_lenda(part["id"])
    assert row is not None
    assert row["valor_centavos"] == 15000
    assert row["recado"] == "Primeira doação"
    assert row["borda"] == "duplo"

    # Re-doar soma
    r = client.post(
        "/admin/hall-lendas/salvar",
        data={
            "modo": "doar",
            "participante_id": str(part["id"]),
            "valor": "50",
            "recado": "Segunda",
            "borda": "brilho",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    row = dbmod.get_hall_lenda(part["id"])
    assert row["valor_centavos"] == 20000
    assert row["recado"] == "Segunda"
    assert row["borda"] == "brilho"

    # Editar total
    r = client.post(
        "/admin/hall-lendas/salvar",
        data={
            "modo": "editar",
            "participante_id": str(part["id"]),
            "valor_total": "99,90",
            "recado": "Ajuste",
            "borda": "laurel",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    row = dbmod.get_hall_lenda(part["id"])
    assert row["valor_centavos"] == 9990
    assert row["borda"] == "laurel"

    r = client.post(
        "/admin/hall-lendas/apagar",
        data={"participante_id": str(part["id"])},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert dbmod.get_hall_lenda(part["id"]) is None


def test_admin_hall_exige_mazeta(client: TestClient):
    r = client.get("/admin/hall-lendas", follow_redirects=False)
    assert r.status_code in (302, 303)


def test_perfil_lenda_badge_e_borda(client: TestClient):
    alvo = _lenda("Perfil Lenda", "11990008005", valor="30,00")
    dbmod.set_hall_borda(alvo["id"], "laurel")
    viewer = dbmod.criar_participante("Viewer Lenda", status="liberado", celular="11990008006")
    dbmod.definir_credenciais(viewer["id"], "viewer.lenda", "senha12345")
    client.get(f"/p/{viewer['token']}")

    r = client.get(f"/perfil/{alvo['id']}")
    assert r.status_code == 200
    assert "proto-times-lenda" in r.text
    assert ">Lenda<" in r.text
    assert "proto-steam-avatar--laurel" in r.text
    assert "proto-steam-name-star" in r.text


def test_lenda_escolhe_moldura(client: TestClient):
    part = _lenda("Escolhe Borda", "11990008007", valor="40,00")
    dbmod.definir_credenciais(part["id"], "escolhe.borda", "senha12345")
    client.get(f"/p/{part['token']}")

    r = client.get("/meu-perfil/editar")
    assert r.status_code == 200
    assert "Moldura de Lenda" in r.text
    assert 'name="borda"' in r.text

    r = client.post(
        "/meu-perfil/hall-borda",
        data={"borda": "brilho"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert dbmod.get_hall_lenda(part["id"])["borda"] == "brilho"

    r = client.get("/meu-perfil")
    assert r.status_code == 200
    assert "proto-steam-avatar--brilho" in r.text
    assert "proto-times-lenda" in r.text


def test_paginacao_hall(client: TestClient):
    for i in range(12):
        _lenda(f"Lenda Pag {i:02d}", f"119900081{i:02d}", valor=f"{100 + i},00")
    r = client.get("/hall-lendas")
    assert r.status_code == 200
    assert "página 1 / 2" in r.text
    assert "Próxima" in r.text
    r2 = client.get("/hall-lendas?pagina=2")
    assert r2.status_code == 200
    assert "Anterior" in r2.text
