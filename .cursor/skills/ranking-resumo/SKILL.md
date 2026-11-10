---
name: ranking-resumo
description: Profile “Resumo das rodadas” Pts per leg — especially Semis/Quartas Volta showing 0 while games scored. Use for _rod_para_resumo and related display.
---

# Ranking — round summary Pts

## When to use

Profile / resumo shows wrong Pts for a leg (classic: Semis Volta = 0 while match rows have points), or labels for unico phases (“Jogo” vs Ida/Volta).

## Key files

- `src/ranking.py` — `_rod_para_resumo`, `_pts_dos_jogos`, `_entrada_resumo_rodada`, `_jogos_detalhe_participante` (or equivalent detail builder)
- `templates/meu_perfil.html` (and any partial that renders resumo)

## Suggested tests

```bash
.venv/bin/pytest tests/test_final_jogo_unico.py tests/test_meu_perfil.py -q
```

## Known trap

When **Volta** already has scores and **Ida** is confirmed, Volta points land in the **baseline**. Live Volta then has snapshot `rod=0` even though each game has `pts`.

**Fix shape (current):** display-only in `_rod_para_resumo` — if `rod==0` and sum of game pts ≠ 0, show game pts, **unless** that `(fase, janela)` is already in confirmed legs for the live row (avoids double-counting archived legs).

## Do not

- Rewrite confirm-time rod storage just to fix the profile display without strong evidence.
- Remap early Semis/Quartas history aggressively — that broke round numbering before.
