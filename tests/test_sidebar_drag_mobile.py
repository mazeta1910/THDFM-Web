"""Smoke Playwright: reordenar menu lateral com Pointer Events (mobile)."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.config import ROOT_DIR

playwright = pytest.importorskip("playwright.sync_api")


@pytest.fixture(scope="module")
def browser_page():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 390, "height": 844},
            has_touch=True,
            is_mobile=True,
        )
        page = context.new_page()
        yield page
        browser.close()


def test_sidebar_pointer_drag_reordena_grupos(browser_page, tmp_path: Path):
    """Garante que toque no ⋮⋮ move o submenu (HTML5 DnD não basta no mobile)."""
    page = browser_page
    css = (ROOT_DIR / "static" / "style.css").read_text(encoding="utf-8")
    js = (ROOT_DIR / "static" / "site-chrome.js").read_text(encoding="utf-8")
    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/>
<style>
{css}
body {{ margin: 0; }}
.site-sidebar {{ display:flex !important; position:static !important; transform:none !important; width:240px; height:100vh; }}
</style></head>
<body class="site-body site-sidebar-open">
<aside id="site-sidebar" class="site-sidebar" data-menu-scope="site" data-user-id="" data-sidebar-ordem="">
  <nav class="site-side-nav"><div class="site-side-nav-scroll">
    <div class="site-menu-sortable" data-menu-sortable>
      <details class="site-menu-group" data-group="alpha" open>
        <summary class="site-menu-summary"><span class="site-menu-drag" draggable="false">⋮⋮</span><span>Alpha</span></summary>
      </details>
      <details class="site-menu-group" data-group="beta" open>
        <summary class="site-menu-summary"><span class="site-menu-drag" draggable="false">⋮⋮</span><span>Beta</span></summary>
      </details>
      <details class="site-menu-group" data-group="gamma" open>
        <summary class="site-menu-summary"><span class="site-menu-drag" draggable="false">⋮⋮</span><span>Gamma</span></summary>
      </details>
    </div>
  </div></nav>
</aside>
<script>{js}</script>
</body></html>"""
    page.set_content(html, wait_until="load")
    page.wait_for_selector("[data-menu-sortable] > [data-group]")

    def ordem():
        return page.eval_on_selector_all(
            "[data-menu-sortable] > [data-group]",
            "els => els.map(e => e.getAttribute('data-group'))",
        )

    assert ordem() == ["alpha", "beta", "gamma"]

    # Arrasta Alpha até abaixo de Gamma via PointerEvent (touch)
    page.evaluate(
        """() => {
          const groups = [...document.querySelectorAll('[data-menu-sortable] > [data-group]')];
          const handle = groups[0].querySelector('.site-menu-drag');
          const target = groups[2].getBoundingClientRect();
          const start = handle.getBoundingClientRect();
          const sx = start.left + start.width / 2;
          const sy = start.top + start.height / 2;
          const ex = target.left + 16;
          const ey = target.top + target.height * 0.8;
          const fire = (type, x, y) => handle.dispatchEvent(new PointerEvent(type, {
            bubbles: true, cancelable: true, pointerId: 7, pointerType: 'touch',
            clientX: x, clientY: y, buttons: type === 'pointerup' ? 0 : 1,
          }));
          fire('pointerdown', sx, sy);
          for (let i = 1; i <= 16; i++) {
            const t = i / 16;
            fire('pointermove', sx + (ex - sx) * t, sy + (ey - sy) * t);
          }
          fire('pointerup', ex, ey);
        }"""
    )

    after = ordem()
    assert after == ["beta", "gamma", "alpha"], after

    # Arrasta Beta para o fim
    page.evaluate(
        """() => {
          const groups = [...document.querySelectorAll('[data-menu-sortable] > [data-group]')];
          const handle = groups[0].querySelector('.site-menu-drag'); // beta
          const target = groups[2].getBoundingClientRect();
          const start = handle.getBoundingClientRect();
          const sx = start.left + start.width / 2;
          const sy = start.top + start.height / 2;
          const ex = target.left + 16;
          const ey = target.top + target.height * 0.85;
          const fire = (type, x, y) => handle.dispatchEvent(new PointerEvent(type, {
            bubbles: true, cancelable: true, pointerId: 8, pointerType: 'touch',
            clientX: x, clientY: y, buttons: type === 'pointerup' ? 0 : 1,
          }));
          fire('pointerdown', sx, sy);
          for (let i = 1; i <= 16; i++) {
            const t = i / 16;
            fire('pointermove', sx + (ex - sx) * t, sy + (ey - sy) * t);
          }
          fire('pointerup', ex, ey);
        }"""
    )
    assert ordem() == ["gamma", "alpha", "beta"]

    out = Path("/opt/cursor/artifacts/screenshots/sidebar-drag-mobile-playwright.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out))
