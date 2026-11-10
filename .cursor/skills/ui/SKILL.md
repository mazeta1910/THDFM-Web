---
name: ui
description: THDFM UI rules — compact buttons, SVG icons, prototype-before-new-UI. Bridge to .cursorrules and .cursor/rules.
---

# UI (THDFM)

## When to use

Any template/CSS/JS chrome change, new screen/modal, buttons, sidebar, or visual density work.

## Always read first

- `.cursorrules` (buttons, prototype gate, density, icons)
- `.cursor/rules/ui-vetores-compactos.mdc`
- Grid-specific: `.cursor/rules/compact-controls.mdc`

If this skill conflicts with `.cursorrules`, **ask Mazeta**.

## Key files

- `static/style.css` — bump `?v=` in `templates/base.html` after CSS changes
- `templates/base.html`, `templates/partials/nav_icons.html`
- `templates/partials/site_sidebar.html`, `templates/partials/admin_sidebar.html`
- Feature templates under `templates/`

## Suggested tests

```bash
.venv/bin/pytest tests/test_css_build.py tests/test_base_chrome_modules.py tests/test_sidebar_ordem.py -q
```

## Hard rules (short)

1. Prototype **new/redesigned** UI in Canvas → wait for “pode implementar”
2. Buttons compact; max 1–2 words; prefer SVG-only with `title`/`aria-label`
3. Never restore global `button, .btn { width: 100%; }` — full-width is `.btn-block` opt-in
4. Form actions on the **right**; single-field forms keep button on the same row
5. Reuse `ico()` — do not add another icon library

## Pitfalls

- Landing first viewport: avoid stat strips / promo clutter
- Preserve existing THDFM visual language; do not invent a new design system
