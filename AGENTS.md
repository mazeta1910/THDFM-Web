# THDFM Web — agent guide

English for agent docs. UI copy stays **pt-BR**. Product: THDFM (bolão, Grid, feed, Zap group).

## Before coding

1. Read `.cursorrules` (always-on UI + scope rules).
2. Open `docs/mapa-dominios.md` → pick the domain.
3. Open the matching skill under `.cursor/skills/<name>/SKILL.md`.
4. Touch only the paths listed in that skill unless the task clearly spans domains.
5. If a skill conflicts with `.cursorrules`, **ask Mazeta** — do not guess.

## Run locally (Cloud)

```bash
.venv/bin/uvicorn src.app:app --host 0.0.0.0 --port 8000 --reload
```

- App: `http://localhost:8000`
- Health: `GET /health`
- Swagger `/docs` exists but is **login-gated** (same auth middleware as the site). Do not “fix” access unless asked.

DB seeds on startup (`data/bolao.db`). Tests use an isolated temp DB via `tests/conftest.py`.

## Tests

Skills **suggest** pytest targets; the agent **decides** what to run.

```bash
.venv/bin/pytest tests/test_<area>.py -q
```

Prefer the narrowest suite that covers the change. Full `pytest -q` only when the change is cross-cutting or you are unsure.

## Git / Cloud branches

- Feature branches: `cursor/<kebab-description>-0365`
- Focused diffs; no opportunistic refactors
- Do **not** implement portal/feed/admin unification until Mazeta asks explicitly

## Backlog

- Source files: `docs/backlog/*.md` (by area)
- Tracking: GitHub Issues (link from the md row when an issue exists)
- Agent **may add** suggested items in PRs
- Mark status `feito` **only when Mazeta asks to merge** (not on open PR / green tests alone)
- Admin read-only page (`/admin/backlog`) is planned; ship only after Canvas prototype consensus

## New / redesigned UI

Prototype first (Cursor Canvas), wait for explicit go-ahead (“pode implementar”, “fecha nessa”). Tiny CSS/typo fixes pointed by Mazeta may go straight to code.

## Do not put here

Passwords, PC disk cleanup tips, personal prefs, or portal reform ideas until they are an explicit task.
