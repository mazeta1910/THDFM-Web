# THDFM Web — revisão do backlog (17 nov 2026)

> Análise do snapshot `backlog-thdfm-para-deepseek-2026-11-17.md`, para orientar o próximo sprint.
> Regra mantida: **nada de código antes de "pode implementar"**; tela nova → Canvas antes.
>
> Fonte: DeepSeek (arquivo 2/3 enviado por Mazeta).

---

## 1. Veredito

O snapshot está **acima da média**: tem taxonomia de status (`agora`/`depois`/`ideia`/`feito`), dívidas técnicas assumidas, "fora de escopo" explícito e uma seção "o que perguntar" que convida à revisão.

O que falta virar rotina: quase nenhum item tem **owner, esforço (S/M/L), dependência ou critério de pronto**. Sem isso não dá para sequenciar nem comprometer data.

**Pontos fortes** (não mexer):
- Separação honesta entre feito / em voo / estacionado.
- Dívida de CSS documentada sem maquiagem (`bundle` vs `partials`).
- Itens "fora de escopo" que evitam scope creep (OAuth, WhatsApp API, reforma unificada).
- Fontes canônicas listadas no topo.

**Pontos fracos** (corrigir):
- §3.1 é prosa, não um trabalho executável (sem critérios de aceite).
- Duas fontes de verdade (este snapshot vs `docs/backlog/*.md`) — risco de drift.
- Taxonomia inconsistente: §3 usa "Em voo", que não existe no conjunto de status.
- Nenhuma decisão tem dono nem prazo (ex.: reconciliação do doc de cadastro).

---

## 2. Respostas às perguntas em aberto (§6 do snapshot)

### Q1 — Ordem de implementação: conta no site vs reabrir bolão PIX?

**Recomendação: conta no site primeiro, isolada. Bolão PIX fica como está.**

| Argumento | Detalhe |
|---|---|
| Bolão PIX já funciona | Fluxo manual/admin atende; não é impedimento. |
| Conta é pré-requisito | Desbloqueia login no Grid, grupo WA, leitura de Listra/Bans/Copypastas. |
| Bolão tem timing de temporada | Não deve segurar o cadastro. |
| Os dois funis tocam a mesma tela | Inscrições acabou de ser limpa; paralelo sem isolamento = regressão no cleanup. |

Implementação: `feature_flags.conta_site` e `feature_flags.inscricao_bolao` separados. Conta nasce atrás da flag; bolão continua ligado até decisão por temporada.

### Q2 — Como modelar dois funis sem confundir o admin Inscrições?

Modele como **duas entidades, não uma tabela com dois significados**:

| Conceito | Entidade | Estado | Onde no admin |
|---|---|---|---|
| Conta no site | `usuario` | ativo / inativo / e-mail verificado | nova aba **"Contas"** |
| Participação no bolão | `participacao` (vínculo usuário↔edição) | aguardando PIX → confirmado | tela **Inscrições** (a que foi limpa) |

Regra dura: **nunca misturar estado de conta com estado de participação na mesma coluna**. A tela Inscrições continua mostrando *participação* (PIX).

As flags já existentes (`origem`, `pode_bolao`, `visivel_grupo_wa`, `pode_grid`) viram o **modelo de permissão/flags único** — documentar a matriz.

Fechar a dívida de reconciliação: criar `docs/backlog/conta-site.md` (1 página, "conta ≠ bolão") e marcar `docs/sprint-seguinte-cadastro-externo.md` como **legado/superseded** — senão o próximo dev lê o doc antigo e implementa o modelo errado.

> **Nota pós-#411:** canônico já em `docs/conta-site.md` (raiz de `docs/`, não só backlog); sprint PIX marcado superseded.

### Q3 — Unificar "Quem palpitou" (WhatsApp + e-mail) numa ação "Avisar"?

**Sim, em 2 passos.** Hoje há **3 caminhos divergentes** (e-mail automático #405, e-mail em lote manual, WhatsApp manual); o cadastro criaria um quarto.

1. **Passo 1:** extrair uma **abstração de notificação** — canal = `email | whatsapp`, preferência por usuário, cooldown, fallback.
2. **Passo 2:** botão **"Avisar"** único em Quem palpitou, respeitando a preferência, com fallback manual.

Condição: **nunca** disparar os dois canais por padrão. Respeitar consentimento (quem não optou por WhatsApp recebe e-mail, e vice-versa).

### Q4 — Priorizar a ressincronização de CSS antes ou depois do cadastro?

**Antes.** É "sprint curto" e é um bloqueador silencioso: com `test_css_build` falhando, **nenhum PR novo consegue rebuild seguro** — o cadastro nasceria em cima de um build quebrado.

Critério: `test_css_build` **verde e idempotente** (partials ← bundle, sem mudar visual), 1 PR isolado. Pode rodar **em paralelo com o Canvas do cadastro** — não bloqueia o design, só o código.

> **Nota pós-#408:** CSS sync já mergeado.

### Q5 — Anti-abuso no job de lembretes (14d/7d/24h)

Fechar antes do próximo sprint:

1. **Idempotência por chave no DB**: `constraint` único (marco×fase×perna×usuário), não só flag em memória — re-deploy/retry duplica.
2. **`CRON_SECRET` na query string** vai para logs de proxy. Mover para header + rate-limit no endpoint.
3. **Timezone do "jogo mais próximo"** definido; rodar 2x na mesma hora não pode disparar 2x.
4. **Suppression list de bounce**: e-mail inválido → bounce → reputação do domínio. Quem bounceou N vezes sai da fila (e cobre o caso "só tem WhatsApp").
5. **Opt-out (LGPD)**: usuário consegue parar de receber sem depender do admin.
6. **Volume**: N participantes × jogos pode estourar o SMTP — chunk + monitorar.
7. **DoD de deploy**: 1 e-mail real em staging antes de ligar na VPS.
8. **Cooldown 24h do botão lote**: confirmar que é **por lote**, não por usuário.

---

## 3. Correções estruturais do backlog

| # | Hoje | Mudança |
|---|---|---|
| 1 | Itens sem metadados | Adicionar colunas fixas: `Owner · Esforço (S/M/L) · Depende de · Pronto quando` |
| 2 | §3.1 é prosa | Promover a **item de backlog** com critérios de aceite (campos, multi-time, termos, opt-in WA, Turnstile, LGPD) |
| 3 | Duas fontes de verdade | Snapshot **gerado** do `docs/backlog/*.md` (com "gerado em") ou declarado canônico |
| 4 | "Em voo" fora da taxonomia | Adicionar `em_voo` ou mapear §3 para `agora` |
| 5 | Decisões sem dono/prazo | Criar **decision log** (data + decisão + status + owner) |
| 6 | Sem "porquê" por item | 1 frase de valor por item (o que desbloqueia) |
| 7 | Dívidas sem gatilho | Cada dívida com "atacar quando X" (ex.: CSS → antes da próxima UI nova) |

---

## 4. Gaps que o snapshot não cobre

- **LGPD** no cadastro e no job de e-mail: consentimento WA separado, minimização, retenção, opt-out.
- **"Externos podem ver Listra/Bans/Copypastas" é ambíguo**: é público *sem login* ou exige conta? Isso muda o escopo do cadastro — se for público, "ver" não justifica criar conta.
- **Multi-time = N:N** no modelo de dados; definir o que "time do coração" afeta (Grid? ranking?).
- **2FA / recovery**: reset de senha já existe via SMTP; registrar 2FA como `ideia`.
- **Política de auto-merge** (§5.4 "às vezes não está habilitado"): definir merge queue vs squash direto.

> **Nota:** Mazeta já fechou Listra/Bans/Copypastas **só com conta**; time do coração = só perfil, não Grid (`docs/conta-site.md`).

---

## 5. Plano de próximo passo

1. **Chore isolado de CSS** — 1 PR, `test_css_build` verde e idempotente, sem mudar visual.
2. **Fechar a decisão conta≠bolão** — `docs/backlog/conta-site.md`; marcar doc legado como superseded.
3. **Canvas do cadastro** (conta no site) com critérios de aceite — sem codar ainda.
4. **Ops da VPS** — `CRON_SECRET` + SMTP + cron, com smoke test de 1 e-mail.
5. **Implementar cadastro** atrás de feature flag `conta_site`, com a tela Inscrições intocada.

---

## 6. Briefing para o Cursor (ordem obrigatória)

1. Ressincronizar CSS (1 PR): `test_css_build` verde e idempotente, sem mudar visual. **Não** comece o cadastro antes.
2. Criar `docs/backlog/conta-site.md` (1 página: conta ≠ bolão) e marcar `docs/sprint-seguinte-cadastro-externo.md` como **legado/superseded**.
3. Modelo de dados em duas entidades (`usuario` vs `participacao`); nunca misturar estado de conta com estado de participação; flags existentes viram matriz de permissões documentada.
4. Fechar anti-abuso do job de lembretes: constraint único (marco×fase×perna×usuário), `CRON_SECRET` em header + rate-limit, timezone definido, suppression list de bounce, opt-out LGPD, chunk de volume, cooldown por lote.
5. Notificação: abstração de canal (`email | whatsapp`) com preferência por usuário e fallback manual; botão **"Avisar"** único; nunca disparar 2 canais por padrão.
6. Montar o **Canvas do cadastro** (conta site) com critérios de aceite antes de qualquer código.
7. Deploy ops na VPS com smoke test (1 e-mail real em staging).
8. Implementar cadastro atrás da flag `conta_site`; tela **Inscrições intocada**.
9. **Nada de UI nova sem "pode implementar".**

**Critérios de aceite do cadastro (conta no site):**
- Campos: nome, sobrenome, username, e-mail, senha + confirmar.
- Time do coração **multi** (N:N).
- Aceite de termos obrigatório; opt-in WhatsApp **separado**.
- Captcha (Turnstile).
- LGPD: consentimento, minimização, opt-out.

---

## 7. Adendo 17/11 (tarde) — revisão das rotas de admin

Depois de clonar o repo e ler os templates/handlers das telas, anexo os achados de **qualidade das telas existentes** (complementa o §6, que era o plano de *novas* telas). Detalhe completo com file:line em `revisao-rotas-admin-thdfm.md`.

| Rota | Achado principal | Tipo |
|---|---|---|
| `/admin?sec=resultados` | autosave perde edição ao trocar de fase <1,8s | bug |
| `/admin?sec=inscricoes` | "Inativar" usa `confirm()` nativo, "Excluir" usa modal | inconsistência |
| `/admin/palpites` | sem ordenar/filtrar/CSV; `<th>` vazio | melhoria/a11y |
| `/admin/cobranca` | "E-mail" em lote **sem confirmação**; cooldown invisível | bug |
| `/admin/credenciais` | falta link para auditoria do usuário | melhoria |
| `/admin/permissoes` | caps sem descrição; `sistema.*` omitido sem aviso | melhoria |

**Transversal:** (1) **CSRF sem token** — todos os POSTs de admin dependem só de `SameSite=Lax`; (2) `/admin` é monolítico (2 painéis + ~400 linhas de JS inline sempre renderizados).

**Entram no backlog com status `agora`:**
- Fix autosave × troca de fase (bug de perda de dado).
- Token CSRF nos POSTs de admin.
- Confirmação + "último envio" no e-mail em lote de Cobrança.

**Entram como `depois`:** separar `/admin/resultados` de `/admin/inscricoes`; contrato de tabela no Palpites; unificar padrão de confirmação; descrição dos caps.

---

*Revisão gerada em 17/11/2026 (America/Sao_Paulo), baseada no snapshot `backlog-thdfm-para-deepseek-2026-11-17.md` + leitura do código das rotas de admin (`src/app.py`, `templates/admin*.html`).*
