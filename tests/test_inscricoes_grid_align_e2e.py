"""Gate: cabeçalho Inscrições alinhado às colunas das rows (desktop)."""

from __future__ import annotations

import socket
import threading
import time
from pathlib import Path

import pytest
import uvicorn
from playwright.sync_api import sync_playwright

import src.db as db
from tests.conftest import login_admin

ARTIFACTS = Path("/opt/cursor/artifacts")
TOL_PX = 2.0


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture()
def inscricoes_live(client):
    for i in range(12):
        p = db.criar_participante(f"Align {i:02d}", status="liberado", celular=f"1199000{i:04d}")
        db.definir_credenciais(p["id"], f"align{i:02d}", "senha1234")

    login_admin(client)
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

    yield base, client
    server.should_exit = True
    thread.join(timeout=5)


def test_inscricoes_header_alinha_com_rows(inscricoes_live):
    base, client = inscricoes_live
    host = base.split("://", 1)[1].split(":", 1)[0]
    cookies = [
        {
            "name": c.name,
            "value": c.value,
            "domain": host,
            "path": c.path or "/",
        }
        for c in client.cookies.jar
    ]

    ARTIFACTS.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        if cookies:
            context.add_cookies(cookies)
        page = context.new_page()
        page.goto(f"{base}/admin?sec=inscricoes", wait_until="networkidle")
        page.evaluate(
            """() => {
              document.querySelectorAll('.email-gate-modal,[data-email-gate],.cookie-consent,[data-cookie-consent]').forEach(e => e.remove());
              document.querySelectorAll('dialog').forEach(d => { try { d.close(); } catch (_) { d.remove(); } });
            }"""
        )

        lista = page.locator('[data-participantes-section="liberados"] [data-participantes-lista]')
        assert lista.count() == 1
        assert page.locator("[data-participantes-pager]:not([hidden])").count() >= 1

        metrics = page.evaluate(
            """() => {
              const lista = document.querySelector('[data-participantes-section="liberados"] [data-participantes-lista]');
              const head = lista.querySelector('.participante-row-head');
              const row = lista.querySelector('.participante-edit-wrap:not(.participante-create-wrap) .participante-row');
              if (!head || !row) return { ok: false, reason: 'missing head/row' };
              const hCols = [...head.querySelectorAll(':scope > .participante-col')];
              const rCols = [...row.querySelectorAll(':scope > .participante-col')];
              if (hCols.length !== rCols.length) {
                return { ok: false, reason: `col count ${hCols.length} vs ${rCols.length}` };
              }
              const deltas = hCols.map((h, i) => {
                const hr = h.getBoundingClientRect();
                const rr = rCols[i].getBoundingClientRect();
                return {
                  i,
                  left: Math.abs(hr.left - rr.left),
                  width: Math.abs(hr.width - rr.width),
                };
              });
              const visible = [...lista.querySelectorAll('.participante-edit-wrap:not(.participante-create-wrap)')]
                .filter((w) => !w.hidden).length;
              return { ok: true, deltas, visible, cols: hCols.length };
            }"""
        )
        assert metrics.get("ok"), metrics
        assert metrics["cols"] >= 5
        assert metrics["visible"] == 10, metrics
        for d in metrics["deltas"]:
            assert d["left"] <= TOL_PX, metrics
            assert d["width"] <= TOL_PX, metrics

        out = ARTIFACTS / "inscricoes-grid-align-desktop.png"
        lista.screenshot(path=str(out))
        browser.close()
