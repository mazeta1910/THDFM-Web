# Agent backlog

Dual source of truth:

1. **Markdown** here (`docs/backlog/*.md`) — local map the agent edits in PRs
2. **GitHub Issues** — official tracking; link the issue in the row when it exists

## Rules

- Agent **may add** suggested items
- Mark `feito` when the related PR **merges** (Mazeta prefers auto-merge; not when a PR merely opens or tests pass)
- Keep rows short: title, status, skill, issue, one-line acceptance
- Do not invent product work (portal reform, paid signup) without an explicit ask — those stay as `ideia` until prioritized
- Conta do site ≠ inscrição/PIX do bolão: canônico em `docs/conta-site.md`

## Statuses

| Status | Meaning |
|--------|---------|
| `agora` | Active / in flight |
| `depois` | Next, not blocking |
| `ideia` | Parked; align before coding |
| `feito` | Merged (auto-merge OK) |

## Admin UI

Read-only `/admin/backlog` (dense table + filters) is **prototyped** in Cursor Canvas. Implement in the repo only after explicit UI consensus.
