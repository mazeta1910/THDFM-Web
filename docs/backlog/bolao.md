# Backlog — bolão

| Status | Item | Skill | Issue | Accept |
|--------|------|-------|-------|--------|
| feito | Final = single match (`perna=unico`); oitavas/quartas/semis = ida/volta | bolao-fases | #378 | Final UI has no Ida/Volta; semis keep both legs |
| feito | E-mail automático a quem não palpitou (14d / 7d / 24h) | bolao / admin | #405 | Job cron + botão Admin › Quem palpitou; faixas anti-flood; SMTP + CRON_SECRET |
| feito | Docs: conta do site ≠ inscrição/PIX do bolão | bolao | — | Canônico `docs/conta-site.md`; sprint PIX marcado superseded para conta; campos fechados |
| agora | Cadastro / login conta no site | bolao, ui | — | Após Canvas `/cadastro` + “pode implementar”; `docs/conta-site.md`; flag `conta_site`; Inscrições intocada |
| agora | Hardening lembrete-palpites | bolao / admin | — | UNIQUE marco×fase×perna×user; secret em header; bounce; opt-out; chunk; cooldown por lote |
| depois | Notificação “Avisar” unificada (e-mail \| WhatsApp) | bolao / admin | — | Abstração de canal + preferência; nunca 2 canais por padrão; fallback manual |
| ideia | Inscrição bolão externo (PIX + liberação admin) | bolao | — | Próximos bolões; checklist em `docs/sprint-seguinte-cadastro-externo.md`; flag `inscricao_bolao` |
| ideia | 2FA na conta | bolao | — | Reset SMTP já existe; 2FA estacionado |
