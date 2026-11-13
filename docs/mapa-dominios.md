# Domain map

One page: domain → entry points → suggested tests. Prefer skills over full-repo scans.

| Domain | Skill(s) | Key paths | Suggested tests |
|--------|----------|-----------|-----------------|
| Bolão (phases, legs, tree) | `bolao`, `bolao-fases` | `src/config.py`, `src/scoring.py`, `src/db.py`, `src/app.py` (admin resultados/árvore/janela), `templates/admin.html`, `templates/partials/nav_pernas.html`, `templates/palpites.html`, `static/palpites.js` | `tests/test_final_jogo_unico.py`, `tests/test_nav_pernas_unico.py`, `tests/test_fases_layout_e2e.py`, `tests/test_janela_padrao_palpites.py`, `tests/test_scoring.py`, `tests/test_admin_resultados.py`, `tests/test_arvore_penaltis_rota.py`, `tests/test_meus_palpites_fase.py` |
| Ranking / profile rounds | `ranking`, `ranking-resumo` | `src/ranking.py`, `src/transparencia.py`, `templates/meu_perfil.html`, `templates/classificacao.html`, `templates/transparencia.html` | `tests/test_final_jogo_unico.py` (resumo), `tests/test_meu_perfil.py`, `tests/test_classificacao_table.py` |
| Admin (accounts, scores, ops) | `admin` | `src/app.py` (`/admin*`), `src/admins.py`, `src/permissoes.py`, `templates/admin*.html`, `templates/partials/admin_sidebar.html` | `tests/test_admin_*.py`, `tests/test_health_reset_permissoes.py`, `tests/test_credenciais.py` |
| UI chrome / compact controls | `ui` | `.cursorrules`, `.cursor/rules/*.mdc`, `static/style.css`, `templates/base.html`, `templates/partials/nav_icons.html`, `templates/partials/*sidebar*` | `tests/test_css_build.py`, `tests/test_base_chrome_modules.py`, `tests/test_sidebar_*.py` |
| Auth / email gate | (use `admin` + auth tests) | `src/app.py` (middleware, `/entrar`, email verify), `src/mail.py`, `src/db.py`, `templates/entrar.html`, `templates/partials/email_gate_modal.html` | `tests/test_email_verificacao.py`, `tests/test_home_login.py`, `tests/test_credenciais.py` |
| Grid | (broad: read Grid rules; fine skill TBD) | `src/grid_*.py`, `templates/grid*.html`, `static/grid*.js`, `.cursor/rules/compact-controls.mdc` | `tests/test_grid*.py` |
| Acervo / Hall / Listra / Xonha | — | `src/acervo*.py`, `src/hall_lendas.py`, `src/listra_*.py`, `src/xonhometro_*.py`, matching templates | matching `tests/test_*` |
| Deploy / ops | — | `deploy/`, `.cursor/environment.json`, `.cursor/install.sh` | `tests/test_producao_checklist.py`, `tests/test_health_reset_permissoes.py` |

## Backlog files

| Area | File |
|------|------|
| Index / rules | `docs/backlog/README.md` |
| Bolão | `docs/backlog/bolao.md` |
| Ranking | `docs/backlog/ranking.md` |
| Admin / kit | `docs/backlog/admin.md` |
| UI | `docs/backlog/ui.md` |
| Grid | `docs/backlog/grid.md` |

Statuses: `agora` | `depois` | `ideia` | `feito`. Dual tracking with GitHub Issues when linked.
