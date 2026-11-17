# Backlog — admin / agent kit

| Status | Item | Skill | Issue | Accept |
|--------|------|-------|-------|--------|
| feito | Agent kit: AGENTS.md + domain map + hybrid skills + backlog md | admin | #379 | Repo docs/skills land; agent uses map instead of full scans |
| feito | Admin Sistema Fase B — Access log | admin | #6 | Middleware seletivo, IP truncado, retenção 14d + purge, filtros usuário/path/método/dia |
| feito | Admin Sistema Fase C — Atividade / auditoria | admin | — | `admin_audit` + tela Atividade; fora do access log; marcar feito no merge |
| feito | Menu lateral admin v2 (chrome) | admin, ui | #409 | Site no rodapé; Cobranças; badges; ícones; sem unificar portal |
| feito | Site sidebar alinhado ao chrome v2 | ui | #410 | Barra ativa / densidade / Sair neutro no menu público |
| feito | Inscrições: densificar cards Liberado/Inativos | admin, ui | — | Inativar à esq. do disquete; foto lápis/lixeira no hover; badge Ok |
| feito | Desligar Pedidos de link (WhatsApp) | admin | — | Fluxo coberto por Esqueci minha senha; caixa admin e /login legado removidos |
| feito | Inscrições: remover cols Liberado/Sem link/Inativos | admin, ui | — | Só gestão por cards; sem coluna duplicada de inativos; sem Sem link / Link enviado |
| feito | Inscrições: sem resumo; foto padrão no Cadastro | admin, ui | — | Remove card taxa/PIX/link e faixa Foto padrão; avatar do Cadastro define padrão |
| feito | Inscrições: limpeza residual liberação | admin, ui | — | Sem Aguardando/Recusados/Liberar/Já pagou; create manual já liberado |
| feito | CSRF token nos POSTs de admin | admin | #413 | Token + rejeição sem token; ver `docs/revisoes/deepseek-revisao-admin-rotas-2026-11-17.md` |
| feito | Autosave placares × troca de fase | admin | #413 | Trocar fase <1,8s não perde edição; teste de regressão |
| feito | Cobrança: confirm e-mail em lote + último envio | admin | #413 | Modal com contagem N; cooldown/último envio visível |
| feito | Visão geral v2 — popular `/admin/visao` | admin | #415 | KPIs reais + fase + acessos/atividade/sistema (cap); densos; links filtrados |
| depois | Separar `/admin/resultados` e `/admin/inscricoes` | admin | — | Rotas/templates próprios; `/admin` deixa de ser monolítico |
| depois | Palpites: ordenar/filtrar/CSV + a11y | admin | — | Contrato de tabela; sem `<th>` vazio; CSV do filtro |
| depois | Unificar confirmação (Inativar = modal, não `confirm()`) | admin, ui | — | Mesmo padrão dos outros modais de Inscrições |
| depois | Caps com descrição + aviso `sistema.*` não-delegável | admin | — | Tooltips/linhas em `/admin/permissoes` |
| depois | Credenciais → link auditoria do usuário | admin | — | Atalho para Sistema › Atividade filtrado |
| depois | Admin read-only backlog page `/admin/backlog` | admin, ui | — | Dense table reading `docs/backlog/*.md` + Issue links; only after Canvas go-ahead |
| depois | Favicon / deploy smoke | admin | — | Favicon OK in prod; `/health` 200 |
| depois | Ops VPS: SMTP + CRON_SECRET + smoke 1 e-mail | admin | — | Cron instalado; 1 e-mail real de smoke antes de ligar lote |
