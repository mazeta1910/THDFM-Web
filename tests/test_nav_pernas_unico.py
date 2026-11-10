"""Nav de fases: Final = Jogo único em coluna cheia (contrato HTML + CSS).

Substitui ritual de browser/VNC para regressão de alinhamento: se o grid
voltar a `1fr 1fr` sem `is-unico`, ou o `width: auto` compacto encolher os
botões `<button>` do admin, estes asserts falham.
"""

from __future__ import annotations

import src.db as db
from src.config import ROOT_DIR
from tests.conftest import login_admin

CSS = ROOT_DIR / "static" / "style.css"
PARTIAL = ROOT_DIR / "static" / "css" / "03-portal-da-transparencia-planilha.css"


def _classificar_fase(fase: str) -> list[str]:
    confrontos = db.list_confrontos_completos(fase)
    for c in confrontos:
        ida = next(j for j in c["jogos"] if j["perna"] == "ida")
        volta = next(j for j in c["jogos"] if j["perna"] == "volta")
        db.set_resultado_jogo(ida["id"], 1, 0, None)
        db.set_resultado_jogo(volta["id"], 0, 0, None)
    return [c["clube"] for c in db.classificados_da_fase(fase)]


def _montar_final(client) -> None:
    login_admin(client)
    clubs_o = _classificar_fase("oitavas")
    data_q = {"fase": "quartas"}
    for i in range(4):
        data_q[f"chave_{i}_a"] = clubs_o[i * 2]
        data_q[f"chave_{i}_b"] = clubs_o[i * 2 + 1]
    assert client.post("/admin/arvore/montar", data=data_q, follow_redirects=False).status_code == 303
    clubs_q = _classificar_fase("quartas")
    data_s = {"fase": "semis"}
    for i in range(2):
        data_s[f"chave_{i}_a"] = clubs_q[i * 2]
        data_s[f"chave_{i}_b"] = clubs_q[i * 2 + 1]
    assert client.post("/admin/arvore/montar", data=data_s, follow_redirects=False).status_code == 303
    clubs_s = _classificar_fase("semis")
    assert (
        client.post(
            "/admin/arvore/montar",
            data={
                "fase": "final",
                "chave_0_a": clubs_s[0],
                "chave_0_b": clubs_s[1],
                "chave_0_unico": "2026-12-01T21:00",
            },
            follow_redirects=False,
        ).status_code
        == 303
    )
    db.set_fase_atual("final")
    db.set_janela("ida")


def _trecho(css: str, ancora: str, antes: int = 80, depois: int = 280) -> str:
    """Janela em torno de um marcador único (evita pegar outra regra homônima no bundle)."""
    idx = css.find(ancora)
    assert idx >= 0, f"Âncora {ancora!r} ausente em CSS"
    return css[max(0, idx - antes) : idx + depois]


def test_css_nav_unico_coluna_cheia_e_anti_encolhimento():
    """Contrato visual sem browser: grid 1fr + width 100% !important."""
    for path in (PARTIAL, CSS):
        css = path.read_text(encoding="utf-8")
        bloco_unico = _trecho(css, ".transparencia-nav-pernas.is-unico", 0, 120)
        assert "grid-template-columns: 1fr" in bloco_unico
        assert "1fr 1fr" not in bloco_unico

        # Comentários âncora amarram a regra certa (há outro `.transparencia-nav-fase` no bundle).
        bloco_fase = _trecho(
            css,
            "Sobrescreve button { width:auto; max-width:max-content }",
            120,
            200,
        )
        assert ".transparencia-nav-fase" in bloco_fase
        assert "width: 100% !important" in bloco_fase
        assert "max-width: none !important" in bloco_fase

        bloco_pernas = _trecho(
            css,
            "Célula do grid 1fr/1fr (ou 1fr no is-unico)",
            220,
            160,
        )
        assert ".transparencia-nav-pernas button," in bloco_pernas
        assert "width: 100% !important" in bloco_pernas
        assert "max-width: none !important" in bloco_pernas


def test_html_nav_final_is_unico_nas_rotas_admin_e_transparencia(client):
    _montar_final(client)

    rotas = (
        "/admin?sec=resultados",
        "/admin/palpites?fase=final&perna=unico",
        "/transparencia?fase=final&perna=unico",
    )
    for url in rotas:
        r = client.get(url)
        assert r.status_code == 200, url
        assert "transparencia-nav-pernas is-unico" in r.text, url
        assert 'data-tab="unico"' in r.text or 'perna=unico"' in r.text, url
        # Final não deve listar Ida/Volta na própria coluna unica
        # (outras fases ainda têm ida/volta na mesma página).
        assert "Jogo único" in r.text or 'nav-perna-short">Jogo</span>' in r.text, url

    # Semis na mesma página admin: pernas ida/volta, sem is-unico na coluna
    r_admin = client.get("/admin?sec=resultados")
    assert r_admin.status_code == 200
    assert 'data-fase="semis"' in r_admin.text
    assert 'data-tab="ida"' in r_admin.text
    assert 'data-tab="volta"' in r_admin.text
    # Quantidade: só a Final deve carregar is-unico (uma ocorrência na nav)
    assert r_admin.text.count("transparencia-nav-pernas is-unico") == 1
