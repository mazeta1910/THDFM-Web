---
name: ranking
description: Broad ranking domain — snapshots, confirm round, classificação, transparência. Use when changing standings logic beyond the profile round summary.
---

# Ranking (broad)

## When to use

Confirming rounds, baselines, classificação table, transparência, or snapshot storage — not only the profile “Resumo das rodadas” display fix (that is `ranking-resumo`).

## Key files

- `src/ranking.py` — snapshots, `confirmar_rodada`, baseline, histórico
- `src/transparencia.py`
- `src/db.py` — rodada histórico / meta
- `templates/classificacao.html`, `templates/transparencia.html`, `templates/meu_perfil.html`

## Suggested tests

```bash
.venv/bin/pytest tests/test_classificacao_table.py tests/test_meu_perfil.py tests/test_final_jogo_unico.py -q
```

## Pitfalls

- `rod` in snapshots is `soma - baseline`, not raw match points.
- Undoing a confirmed round restores the previous baseline — test carefully.
- Prefer display-layer fixes for live-leg quirks before rewriting confirm-time storage.
