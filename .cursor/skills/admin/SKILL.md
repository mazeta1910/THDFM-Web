---
name: admin
description: Admin panel, permissions, credentials, agent backlog docs. Use for /admin routes, sidebar, capabilities, and agent kit backlog files.
---

# Admin

## When to use

Changes under `/admin`, permissions/credentials, admin sidebar, or the agent backlog markdown / future read-only backlog page.

## Key files

- `src/app.py` — `/admin*` routes, auth cookies, capability checks
- `src/admins.py`, `src/permissoes.py`
- `templates/admin.html`, `templates/admin_*.html`
- `templates/partials/admin_sidebar.html`
- Agent kit: `AGENTS.md`, `docs/mapa-dominios.md`, `docs/backlog/*.md`

## Suggested tests

```bash
.venv/bin/pytest tests/test_admin_roles.py tests/test_admin_participante.py tests/test_credenciais.py tests/test_health_reset_permissoes.py -q
```

## Backlog workflow

- Edit `docs/backlog/*.md` in the PR; link GitHub Issues when present
- Agent may **add** rows
- Set status `feito` only when Mazeta **asks to merge**
- `/admin/backlog` UI: prototype first, implement only after consensus

## Pitfalls

- Dense admin UI preferred (table/ficha), not chubby cards
- Compact controls; no full-width secondary actions
- Dono-only actions must stay gated
