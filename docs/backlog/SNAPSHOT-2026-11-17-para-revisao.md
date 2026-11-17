# THDFM Web — snapshot de backlog (17 nov 2026, America/Sao_Paulo)

Documento para revisão externa (ex.: DeepSeek Harness). Produto: site THDFM (bolão Copa do Brasil, Grid, feed/grupo Zap). Stack: FastAPI + Jinja2 + SQLite + SMTP. Repo: `mazeta1910/THDFM-Web`.

**Objetivo deste arquivo:** deixar claro o que já entrou, o que está alinhado mas ainda não codado, e o que está estacionado — para sugerir próximo passo sem reinventar decisões já tomadas.

---

## 1. Contexto rápido do produto

- Bolão pago/gerido pelo admin (participantes liberados, palpites por fase/perna).
- Site também tem Grid, Hall, Listra, perfil, etc.
- Preferência de UI do dono (Mazeta): **densidade**, botões **compactos** (ícone SVG / 1–2 palavras), **nunca** full-width em ação secundária; tela nova → **protótipo Canvas antes** de implementar.
- Branches Cloud: `cursor/<desc>-0928` (ou `-0365` legado). Merge preferencial automático quando CI ok.

Fontes canônicas no repo: `docs/backlog/*.md`, `AGENTS.md`, `.cursorrules`, `docs/mapa-dominios.md`.

---

## 2. Feito recentemente (sessão / PRs ~#399–#405)

### Admin › Inscrições (limpeza do fluxo antigo de “liberar link”)

| PR | O quê |
|----|--------|
| #399 | Tags **Admin** e **Ok** alinhadas à **direita**; regra permanente em `.cursorrules` / card-status-tags |
| #400 | Removidas colunas legadas Liberado / Sem link / Link enviado / Inativos (inativos já têm lista própria) |
| #401 | Removidos cards “Inscrições” (taxa/PIX/link) e “Foto padrão” larga; **foto padrão** no card Cadastro manual |
| #404 | Limpeza residual: sem Aguardando liberação / Recusados / Já pagou / Liberar-Recusar; create manual já nasce `liberado` |

Decisão de produto por trás: **não precisamos mais “liberar link”** para o fluxo antigo; login externo e cadastro no site vêm a seguir. PIX+comprovante continua relevante para **entrar no bolão** nos próximos bolões — distinto de **criar conta no site**.

### UI / chrome

| PR | O quê |
|----|--------|
| #402 | `input[type=email]` e `url` no tema escuro global (não nativo “branco”) |
| #403 | Modal de feedback: **Ok à direita**; modais de sucesso **fecham sozinhos** (~2,2s); regra `modal-feedback.mdc` |

### Bolão / ops

| PR | O quê |
|----|--------|
| #405 | **E-mail automático a quem não palpitou** — faixas **14 dias / 7 dias / 24 h** antes do jogo mais próximo que falta; 1 envio por marco×fase×perna; botão **E-mail** no Admin › Quem palpitou (lote manual, cooldown 24h); cron `CRON_SECRET` + SMTP |

### Admin Sistema (antes desta leva)

- Fase B Access log — feito (#6 / merge)
- Fase C Atividade / auditoria admin — feito
- Agent kit (AGENTS + mapa + skills + backlog md) — feito
- Densificar cards Liberado/Inativos, hover foto, badge Ok — feito
- Desligar “Pedidos de link” (WhatsApp) — feito (coberto por Esqueci senha)
- Final = jogo único (`perna=unico`); oitavas/quartas/semis = ida/volta — feito
- Ranking resumo Semis Volta Pts — feito
- Layout chrome com testes pytest/Playwright — feito

---

## 3. Em voo / próximo óbvio

### 3.1 Cadastro / login para usuários do site (prioridade de produto alinhada, ainda não implementada)

Mazeta deixou claro na conversa:

1. **Cadastro no site** (conta para usar features existentes) ≠ inscrição no bolão com PIX.
2. PIX + comprovante + liberação admin permanece o modelo para **participar do bolão** nos próximos ciclos.
3. Escopo desejado do cadastro de conta (rascunho alinhado, **não codado**):
   - nome, sobrenome, username, e-mail, senha + confirmar
   - time do coração (permitir **mais de um**)
   - aceite de termos / avisos padrão de cadastro
   - tag/opção: “Quer entrar no grupo de WhatsApp da página?”
   - captcha (Turnstile etc.) considerado interessante
   - externos podem **ver** Listra / Bans / Copypastas (leitura ok)
4. Doc antigo `docs/sprint-seguinte-cadastro-externo.md` ainda fala em **externo = pagante PIX + liberação** como decisão recomendada para o **bolão**. Isso precisa ser **reconciliado** com o cadastro gratuito de conta do site (dois fluxos).

**Estado no backlog md:** item ainda como `ideia` / “depois dos lembretes”. Lembretes (#405) já mergearam → este vira o candidato natural a `agora`, **depois de alinhar o escopo em 1 página** (conta vs bolão).

### 3.2 Regras permanentes de UI (sempre `agora`)

- Controles compactos; protótipo antes de UI nova.
- Não iniciar reforma portal/feed/admin unificado sem pedido explícito.

### 3.3 Ops pós-#405 (não é feature, é deploy)

No `.env` de produção:

- `SMTP_*` (já usado em reset/verificação)
- `CRON_SECRET` + cron horário (`deploy/lembrete-palpites.sh`) se ainda não instalado na VPS

---

## 4. Depois / ideias estacionadas

| Status | Item | Notas |
|--------|------|--------|
| depois | `/admin/backlog` read-only | Dense table lendo `docs/backlog/*.md`; **só após Canvas** |
| depois | Favicon / deploy smoke | Favicon ok em prod; `/health` 200 |
| ideia | Reforma portal / feed / admin unificado | **Proibido** começar sem “pode implementar” explícito |
| ideia | Fine skill de Grid | Só quando o trabalho de Grid repetir o bastante |
| ideia | Bolão 100% gratuito sem fricção | Fora de escopo (sprint cadastro) |
| ideia | OAuth Google/Apple | Fora de escopo imediato |
| ideia | WhatsApp Business API automática | Fora de escopo imediato |

---

## 5. Dívidas / riscos técnicos conhecidos

1. **`static/style.css` vs `static/css/*.css`**: em `master` o bundle e os partials já estavam dessincronizados (PRs editaram o bundle direto). O teste `test_css_build` falha se alguém rodar rebuild cego. Sugestão: sprint curto de ressincronizar partials ← bundle (ou o contrário) sem mudar visual.
2. **Lembrete e-mail**: só envia a quem tem e-mail cadastrado; quem só tem WhatsApp continua no fluxo manual da tela Quem palpitou.
3. **Cadastro externo**: schema já tem `email`, `origem`, `pode_bolao`, `visivel_grupo_wa`, `pode_grid` — base pronta; falta fluxo UX + Turnstile + política de flags.
4. Auto-merge do GitHub às vezes não está habilitado no repo; merges recentes foram squash direto quando mergeable/CLEAN.

---

## 6. O que pedir ao DeepSeek (perguntas úteis)

1. Dado §3.1, qual a **ordem de implementação** mais segura: (A) só conta no site → (B) reabrir inscrição bolão PIX, ou os dois em paralelo com feature flags?
2. Como modelar **dois funis** (conta site vs inscrição bolão) sem confundir o admin Inscrições que acabamos de limpar?
3. Vale unificar “Quem palpitou” WhatsApp + e-mail numa única ação “Avisar” com preferência de canal, ou manter separado (como está)?
4. Priorizar a **ressincronização CSS** antes do cadastro, ou depois?
5. Algum gap de anti-abuso no job de lembretes (14d/7d/24h) que valha fechar antes do próximo sprint?

---

## 7. Mapa curto dos arquivos de backlog no repo

| Arquivo | Foco |
|---------|------|
| `docs/backlog/README.md` | Regras de status (`agora`/`depois`/`ideia`/`feito`) |
| `docs/backlog/bolao.md` | Fases, palpites, cadastro externo, lembretes |
| `docs/backlog/admin.md` | Painel, Inscrições, Sistema, agent kit |
| `docs/backlog/ui.md` | Compact controls, modais, reforma portal |
| `docs/backlog/ranking.md` | Resumo / classificação |
| `docs/backlog/grid.md` | Skill fina de Grid |
| `docs/sprint-seguinte-cadastro-externo.md` | Checklist legado (PIX) — reconciliar com conta site |

---

## 8. Resumo executivo (1 parágrafo)

Acabamos de limpar Inscrições do modelo “liberar link”, padronizar modais/inputs, e **ligar lembrete automático de palpites por e-mail (14d/7d/24h)** (#405). O próximo tema grande alinhado verbalmente é **cadastro/login de conta no site** (não confundir com PIX do bolão), ainda sem implementação e com o sprint doc antigo pedindo reconciliação. Estacionados de propósito: reforma portal unificado e `/admin/backlog` até consenso de Canvas. Ops: garantir `CRON_SECRET`+SMTP na VPS.
