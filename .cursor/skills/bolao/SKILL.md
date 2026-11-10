---
name: bolao
description: Broad bolão domain — phases, brackets, scores admin, palpites UI. Use for Copa do Brasil pool work that is not only Final/legs or ranking summary.
---

# Bolão (broad)

## When to use

Any change to matches, brackets, participant guesses, admin resultados/árvore/janela, or scoring that is not narrowly covered by `bolao-fases` or `ranking-resumo`.

## Key files

- `src/config.py` — `FASES`, `FASES_JOGO_UNICO`, `fase_formato`, `JANELAS`
- `src/scoring.py` — points, single-leg winner helpers
- `src/db.py` — confrontos, palpites, meta janela/fase
- `src/app.py` — `/admin` resultados, árvore, janela, avancar-fase; `/bolao/*`
- `templates/admin.html`, `templates/palpites.html`
- `templates/partials/nav_pernas.html`, `templates/partials/admin_arvore_chave.html`
- `static/palpites.js`

## Suggested tests

```bash
.venv/bin/pytest tests/test_scoring.py tests/test_admin_resultados.py tests/test_meus_palpites_fase.py tests/test_janela_padrao_palpites.py -q
```

Add `tests/test_final_jogo_unico.py` / `tests/test_arvore_penaltis_rota.py` when phases or tree change.

## Pitfalls

- Only **Final** is single-match. Semis/oitavas/quartas stay ida+volta.
- Do not invent a second icon system; reuse `ico()` / inline SVG.
- Large open asks (“reformular bolão”) → align requirements first.
