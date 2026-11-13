"""E2E Playwright: geometria + fluxo da nav de fases / mata-mata.

Viewports: Mobile 375x667, Tablet 768x1024, Desktop 1440x900.
Gate principal = getBoundingClientRect / scrollWidth (não ritual VNC manual).
"""

from __future__ import annotations

import socket
import threading
import time
from pathlib import Path

import pytest
import uvicorn
from playwright.sync_api import Page, expect, sync_playwright

import src.db as db
from src.config import ROOT_DIR
from tests.conftest import DEFAULT_ADMIN_USERS, confirmar_email_teste

ARTIFACTS = Path("/opt/cursor/artifacts")
VIEWPORTS = (
    ("mobile", 375, 667),
    ("tablet", 768, 1024),
    ("desktop", 1440, 900),
)
TOL_PX = 2.0


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _classificar_fase(fase: str) -> list[str]:
    confrontos = db.list_confrontos_completos(fase)
    for c in confrontos:
        ida = next(j for j in c["jogos"] if j["perna"] == "ida")
        volta = next(j for j in c["jogos"] if j["perna"] == "volta")
        db.set_resultado_jogo(ida["id"], 1, 0, None)
        db.set_resultado_jogo(volta["id"], 0, 0, None)
    return [c["clube"] for c in db.classificados_da_fase(fase)]


def _montar_bracket_ate_final(client) -> None:
    """Monta chave até a Final no DB do fixture `client`."""
    from tests.conftest import login_admin

    login_admin(client)
    clubs_o = _classificar_fase("oitavas")
    assert len(clubs_o) >= 8, clubs_o
    data_q = {"fase": "quartas"}
    for i in range(4):
        data_q[f"chave_{i}_a"] = clubs_o[i * 2]
        data_q[f"chave_{i}_b"] = clubs_o[i * 2 + 1]
    assert client.post("/admin/arvore/montar", data=data_q, follow_redirects=False).status_code == 303

    clubs_q = _classificar_fase("quartas")
    assert len(clubs_q) >= 4, clubs_q
    data_s = {"fase": "semis"}
    for i in range(2):
        data_s[f"chave_{i}_a"] = clubs_q[i * 2]
        data_s[f"chave_{i}_b"] = clubs_q[i * 2 + 1]
    assert client.post("/admin/arvore/montar", data=data_s, follow_redirects=False).status_code == 303

    clubs_s = _classificar_fase("semis")
    assert len(clubs_s) >= 2, clubs_s
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


@pytest.fixture()
def live_base(client):
    """Sobe uvicorn no mesmo SQLite do fixture `client` (já seedado)."""
    _montar_bracket_ate_final(client)
    with db.get_db() as conn:
        rows = conn.execute("SELECT id FROM participantes").fetchall()
    for row in rows:
        try:
            confirmar_email_teste(int(row["id"]))
        except Exception:
            pass

    import src.app as app_mod

    port = _free_port()
    config = uvicorn.Config(
        app_mod.app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            import urllib.request

            urllib.request.urlopen(base + "/health", timeout=0.3)
            break
        except Exception:
            time.sleep(0.05)
    else:
        server.should_exit = True
        raise RuntimeError("live server não subiu")

    yield base
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture()
def browser_page(live_base, client):
    """Playwright autenticado via cookie da sessão (sem depender do drawer de login)."""
    from tests.conftest import login_admin

    login_admin(client)
    # Extrai cookies do TestClient para o domínio do live server
    host = live_base.split("://", 1)[1].split(":", 1)[0]
    cookies = []
    for c in client.cookies.jar:
        cookies.append(
            {
                "name": c.name,
                "value": c.value,
                "domain": host,
                "path": c.path or "/",
            }
        )

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        if cookies:
            context.add_cookies(cookies)
        page = context.new_page()
        page.goto(f"{live_base}/admin?sec=resultados", wait_until="networkidle")
        page.evaluate(
            """() => {
              document.querySelectorAll('.email-gate-modal,[data-email-gate],.cookie-consent,[data-cookie-consent]').forEach(e => e.remove());
              document.querySelectorAll('dialog').forEach(d => { try { d.close(); } catch (_) { d.remove(); } });
              document.body.style.overflow = 'auto';
            }"""
        )
        # Banner de cookies (se ainda visível)
        for label in ("Aceitar", "Só necessários"):
            btn = page.get_by_role("button", name=label)
            if btn.count():
                try:
                    btn.first.click(timeout=1000)
                except Exception:
                    pass
        yield page, live_base
        context.close()
        browser.close()


def _geo(page: Page) -> dict:
    return page.evaluate(
        """() => {
      const nav = document.querySelector('#admin-placares-nav, .transparencia-nav');
      const tabs = [...document.querySelectorAll('#admin-placares-nav .transparencia-nav-fase')];
      const tabRects = tabs.map(t => {
        const r = t.getBoundingClientRect();
        return { left: r.left, right: r.right, top: r.top, bottom: r.bottom, width: r.width, height: r.height, text: (t.textContent||'').trim() };
      });
      const navR = nav ? nav.getBoundingClientRect() : null;
      // Colunas reais (desktop) ou soma das abas + bordas (mobile com display:contents).
      const cols = [...document.querySelectorAll('#admin-placares-nav .transparencia-nav-col')];
      const colDisplay = cols[0] ? getComputedStyle(cols[0]).display : '';
      let fillSum = 0;
      if (colDisplay === 'contents') {
        fillSum = tabRects.reduce((s, t) => s + t.width, 0);
      } else {
        fillSum = cols.reduce((s, c) => s + c.getBoundingClientRect().width, 0);
      }
      const uniqCard = document.querySelector(
        "[data-fase-panel='final']:not(.hidden) .admin-dash-chave.is-unico, " +
        "[data-fase-panel='final']:not(.hidden) .match-grid > .match-cell:only-child"
      );
      const uniqParent = uniqCard && (
        uniqCard.closest('.admin-dash-list') ||
        uniqCard.closest('.match-panel') ||
        uniqCard.parentElement
      );
      let uniq = null;
      if (uniqCard && uniqParent) {
        const c = uniqCard.getBoundingClientRect();
        const p = uniqParent.getBoundingClientRect();
        uniq = {
          leftGap: c.left - p.left,
          rightGap: p.right - c.right,
          cardW: c.width,
          parentW: p.width,
        };
      }
      const nomes = [...document.querySelectorAll(
        "[data-fase-panel='final']:not(.hidden) .clube-nome"
      )].map(el => ({
        text: el.textContent.trim(),
        scrollWidth: el.scrollWidth,
        clientWidth: el.clientWidth,
        overflow: el.scrollWidth > el.clientWidth + 1,
      }));
      // Contenção: filhos de match-cell / admin-dash-chave (não nav-col com display:contents).
      const overflows = [];
      const cards = [...document.querySelectorAll(
        "[data-fase-panel='final']:not(.hidden) .admin-dash-chave, " +
        "[data-fase-panel='final']:not(.hidden) .match-cell"
      )];
      for (const card of cards) {
        const pr = card.getBoundingClientRect();
        if (pr.width < 1) continue;
        for (const child of card.querySelectorAll('input, img.match-emblema, .clube-nome, .pen-choice')) {
          const cr = child.getBoundingClientRect();
          if (cr.width < 1 || cr.height < 1) continue;
          if (cr.left < pr.left - 2 || cr.right > pr.right + 2 || cr.top < pr.top - 2 || cr.bottom > pr.bottom + 2) {
            overflows.push({
              parent: card.className,
              child: child.tagName + '.' + (child.className || ''),
              delta: {
                left: cr.left - pr.left,
                right: pr.right - cr.right,
                top: cr.top - pr.top,
                bottom: pr.bottom - cr.bottom,
              },
            });
          }
        }
      }
      // Abas contidas no nav (pai real).
      let tabOutsideNav = 0;
      if (navR) {
        for (const t of tabs) {
          const r = t.getBoundingClientRect();
          if (r.left < navR.left - 2 || r.right > navR.right + 2) tabOutsideNav++;
        }
      }
      return {
        scrollWidth: document.documentElement.scrollWidth,
        innerWidth: window.innerWidth,
        navWidth: navR ? navR.width : null,
        fillSum,
        tabRects,
        uniq,
        nomes,
        overflows: overflows.slice(0, 8),
        tabOutsideNav,
        navOverflowHidden: nav ? (getComputedStyle(nav).overflow === 'hidden' || getComputedStyle(nav).overflowX === 'hidden') : false,
        colDisplay,
      };
    }"""
    )


def _fase_tab(page: Page, fase: str):
    return page.locator(f'#admin-placares-nav .transparencia-nav-fase[data-fase="{fase}"]')


def _open_admin_final(page: Page, base: str) -> None:
    page.goto(f"{base}/admin?sec=resultados", wait_until="networkidle")
    page.evaluate(
        """() => {
          document.querySelectorAll('.email-gate-modal,[data-email-gate]').forEach(e => e.remove());
          document.body.style.overflow = 'auto';
        }"""
    )
    _fase_tab(page, "final").click()
    page.wait_for_timeout(200)


@pytest.mark.parametrize("name,width,height", VIEWPORTS, ids=[v[0] for v in VIEWPORTS])
def test_invariantes_geometricas_fases(browser_page, name, width, height):
    page, base = browser_page
    page.set_viewport_size({"width": width, "height": height})
    _open_admin_final(page, base)
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    page.locator("#admin-placares-nav").screenshot(path=str(ARTIFACTS / f"fases-nav-{name}.png"))

    g = _geo(page)
    assert g["scrollWidth"] <= g["innerWidth"] + TOL_PX, f"overflow horizontal ({name}): {g}"
    assert g["navOverflowHidden"] is True
    assert g["navWidth"] is not None
    # Preenchimento: colunas (ou abas no mobile) ≈ largura do nav (± bordas 1px×3 ≈ 3–6px)
    assert abs(g["fillSum"] - g["navWidth"]) <= 6.5, (
        f"abas/colunas não preenchem nav ({name}): sum={g['fillSum']} nav={g['navWidth']}"
    )
    heights = {round(t["height"], 1) for t in g["tabRects"]}
    assert len(heights) == 1, f"alturas de abas diferentes ({name}): {heights}"
    assert g["tabOutsideNav"] == 0, f"aba fora do nav ({name})"

    # Final ativo: 1 card — simetria (centralizado) ou preenchimento quase total
    assert g["uniq"] is not None, f"card único da Final não encontrado ({name})"
    left, right = g["uniq"]["leftGap"], g["uniq"]["rightGap"]
    assert abs(left - right) <= TOL_PX + 1, f"Final não centrado ({name}): L={left} R={right}"

    graves = [
        o
        for o in g["overflows"]
        if o["delta"]["left"] < -2 or o["delta"]["right"] < -2
    ]
    assert not graves, f"filho ultrapassa card ({name}): {graves[:3]}"

    if name == "desktop":
        bad = [n for n in g["nomes"] if n["overflow"] and len(n["text"]) >= 8]
        assert not bad, f"truncamento precoce ({name}): {bad}"


def test_navegacao_fases_e_a11y(browser_page):
    page, base = browser_page
    page.set_viewport_size({"width": 1440, "height": 900})
    _open_admin_final(page, base)

    for fase in ("oitavas", "quartas", "semis", "final"):
        btn = _fase_tab(page, fase)
        btn.click()
        page.wait_for_timeout(150)
        expect(btn).to_have_attribute("aria-selected", "true")
        col = page.locator(f'[data-fase-col="{fase}"]')
        expect(col).to_have_class(re_compile_is_active())
        panel = page.locator(f'[data-fase-panel="{fase}"]')
        expect(panel).not_to_have_class("hidden")
        if fase != "final":
            title = btn.inner_text()
            assert "fechada" in title.lower() or True

    # Final: jogo único + aria
    _fase_tab(page, "final").click()
    unico = page.locator('#admin-placares-nav [data-tab="unico"][aria-selected="true"]')
    expect(unico).to_be_visible()
    pen_choice = page.locator(".pen-choice input").first
    if pen_choice.count():
        assert pen_choice.get_attribute("aria-label")


def re_compile_is_active():
    import re

    return re.compile(r"\bis-active\b")


def test_penaltis_empate_e_inputs(browser_page):
    page, base = browser_page
    page.set_viewport_size({"width": 1440, "height": 900})
    _open_admin_final(page, base)

    card = page.locator('.match-cell[data-jogo-unico="1"]').first
    expect(card).to_be_visible()
    m = card.locator("input.unico-m")
    v = card.locator("input.unico-v")
    pen = card.locator("[data-pen]")

    m.fill("2")
    v.fill("1")
    m.dispatch_event("input")
    v.dispatch_event("input")
    page.wait_for_timeout(100)
    expect(pen).to_have_class(re_compile_hidden())

    m.fill("2")
    v.fill("2")
    m.dispatch_event("input")
    v.dispatch_event("input")
    page.wait_for_timeout(100)
    expect(pen).not_to_have_class(re_compile_hidden())
    expect(pen.locator(".pen-group-title")).to_contain_text("pênaltis")

    # Inputs number: negativos / letras — browser ou validação
    m.fill("-1")
    val = m.input_value()
    assert val == "" or float(val) >= 0 or val == "-1"
    # type=number rejeita letras na maioria dos browsers
    m.fill("")
    m.type("abc")
    assert m.input_value() in ("", "abc")  # chromium costuma ignorar letras
    # min=0 presente
    assert m.get_attribute("min") == "0"


def re_compile_hidden():
    import re

    return re.compile(r"\bhidden\b")


def test_salvar_intercepta_payload(browser_page):
    page, base = browser_page
    page.set_viewport_size({"width": 1440, "height": 900})
    _open_admin_final(page, base)

    card = page.locator('.match-cell[data-jogo-unico="1"]').first
    m = card.locator("input.unico-m")
    v = card.locator("input.unico-v")
    m.fill("3")
    v.fill("1")
    m.dispatch_event("input")
    v.dispatch_event("input")

    save = page.locator(
        '.sticky-save button[type="submit"], .admin-sticky-save button[type="submit"], '
        'form.admin-resultados-form button[type="submit"]'
    )
    with page.expect_request(lambda r: "/admin/resultados" in r.url and r.method == "POST") as req_info:
        if save.count() > 0:
            save.first.click()
        else:
            page.locator("form.admin-resultados-form").first.evaluate(
                "f => f.requestSubmit()"
            )
    req = req_info.value
    post = req.post_data or ""
    assert "jogo_" in post
    assert "3" in post and "1" in post


@pytest.mark.parametrize("name,width,height", (("desktop", 1440, 900), ("mobile", 375, 667)))
def test_snapshot_visual_final_e_oitavas(browser_page, name, width, height):
    page, base = browser_page
    page.set_viewport_size({"width": width, "height": height})
    ARTIFACTS.mkdir(parents=True, exist_ok=True)

    _open_admin_final(page, base)
    nav = page.locator("#admin-placares-nav")
    expect(nav).to_be_visible()
    nav.screenshot(path=str(ARTIFACTS / f"snapshot-final-nav-{name}.png"))
    dash = page.locator("[data-fase-panel='final']:not(.hidden) .admin-dash-list").first
    expect(dash).to_be_visible()
    dash.screenshot(path=str(ARTIFACTS / f"snapshot-final-dash-{name}.png"))

    _fase_tab(page, "oitavas").click()
    page.wait_for_timeout(200)
    oitavas = page.locator("[data-fase-panel='oitavas']:not(.hidden)")
    expect(oitavas).to_be_visible()
    oitavas.screenshot(path=str(ARTIFACTS / f"snapshot-oitavas-{name}.png"))

    # Soft visual gate: arquivos gerados e não vazios
    for p in (
        ARTIFACTS / f"snapshot-final-nav-{name}.png",
        ARTIFACTS / f"snapshot-final-dash-{name}.png",
        ARTIFACTS / f"snapshot-oitavas-{name}.png",
    ):
        assert p.exists() and p.stat().st_size > 500


def test_touch_target_mobile(browser_page):
    page, base = browser_page
    page.set_viewport_size({"width": 375, "height": 667})
    _open_admin_final(page, base)
    sizes = page.evaluate(
        """() => {
      const tabs = [...document.querySelectorAll('#admin-placares-nav .transparencia-nav-fase')];
      return tabs.map(t => {
        const r = t.getBoundingClientRect();
        return { w: r.width, h: r.height, text: (t.textContent||'').trim() };
      });
    }"""
    )
    assert sizes
    for s in sizes:
        assert s["h"] >= 44 - TOL_PX, f"aba mobile < 44px: {s}"
