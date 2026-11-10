---
name: bolao-fases
description: Phase format and legs — Final is jogo único (perna=unico); oitavas/quartas/semis are ida/volta. Use for nav pernas, janela meta, and phase UI.
---

# Bolão phases / legs

## When to use

Changing whether a phase is single-leg vs home/away, `perna` values, Ida/Volta/Jogo chrome, or default palpites window for a phase.

## Key files

- `src/config.py` — `FASES_JOGO_UNICO` (must stay `{"final"}`), `fase_formato()`
- `src/scoring.py` — helpers for `perna=unico`
- `src/db.py` / `src/app.py` — janela meta (`ida` | `volta` | `fechado`), admin forms
- `templates/partials/nav_pernas.html` — Ida/Volta vs single “Jogo”
- `templates/admin.html`, `templates/palpites.html`, `static/palpites.js`
- `src/ranking.py` — `janela_para_nova_rodada`, labels for unico

## Suggested tests

```bash
.venv/bin/pytest tests/test_final_jogo_unico.py tests/test_nav_pernas_unico.py tests/test_janela_padrao_palpites.py -q
```

Prefer these pytest contracts over browser/VNC walkthroughs for nav chrome (Final `is-unico`, full-width cells).

## Invariants

1. **Final** → formato `unico`, UI without Ida/Volta tabs.
2. **Oitavas / Quartas / Semis** → `ida_volta`. Never treat Semis as single-leg.
3. Product reminder: “SEMI É IDA E VOLTA. A final que não é.”
4. Nav CSS: `.transparencia-nav-pernas.is-unico` is `1fr`; fase/perna controls use `width: 100% !important` so admin `<button>`s do not shrink under the compact global button rule.

## Pitfalls

- Confirming Ida while Volta already has scores affects ranking baseline — see `ranking-resumo`.
- Do not “simplify” all knockout phases to unico without an explicit product ask.
- Do not re-introduce half-width “Jogo único” by dropping `is-unico` or the `!important` widths.
