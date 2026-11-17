# Agent backlog

Fonte canônica de itens: **`docs/backlog/*.md`**.

1. **Markdown** aqui — o agente edita em PRs
2. **GitHub Issues** — tracking oficial; link na coluna Issue quando existir
3. Snapshots / revisões externas são **apoio** (não substituem as tabelas): `docs/revisoes/`, `docs/backlog/SNAPSHOT-*`

## Rules

- Agent **may add** suggested items
- Mark `feito` when the related PR **merges** (Mazeta prefers auto-merge; not when a PR merely opens or tests pass)
- Keep rows short: title, status, skill, issue, one-line acceptance
- Do not invent product work (portal reform, paid signup) without an explicit ask — those stay as `ideia` until prioritized
- Conta do site ≠ inscrição/PIX do bolão: canônico em `docs/conta-site.md`
- Decision log: `docs/decisoes.md`

## Statuses

| Status | Meaning |
|--------|---------|
| `agora` | Active / in flight |
| `depois` | Next, not blocking |
| `ideia` | Parked; align before coding |
| `feito` | Merged (auto-merge OK) |

(`em_voo` do snapshot Harness = `agora`.)

## Incorporação DeepSeek (17 nov 2026)

Revisões em `docs/revisoes/`:

- `deepseek-revisao-backlog-2026-11-17.md` — ordem conta→Canvas→ops; hardening lembrete; Avisar
- `deepseek-revisao-admin-rotas-2026-11-17.md` — CSRF, autosave×fase, Cobrança, split admin

Itens `agora` / `depois` já espalhados em `admin.md`, `bolao.md`, `ui.md`.

## Admin UI

Read-only `/admin/backlog` (dense table + filters) is **prototyped** in Cursor Canvas. Implement in the repo only after explicit UI consensus.
