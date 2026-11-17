# Sprint seguinte — inscrição bolão (PIX / externo)

> **Superseded para “conta do site”.**  
> Cadastro/login gratuito de conta no THDFM está documentado em [`docs/conta-site.md`](conta-site.md) (dois funis).  
> Este arquivo permanece como checklist do funil **inscrição no bolão** (PIX + liberação), não do cadastro de conta.

Pré-requisitos (sprint fundação do portal):

- [x] VPS 24/7 + `/health` + backup
- [x] Esqueci senha por e-mail
- [x] Homepage / nav portal vs Grupo WA
- [x] Capabilities no admin (`/admin/permissoes`)
- [x] Schema mínimo: `email`, `origem`, `pode_bolao`, `visivel_grupo_wa`, `pode_grid`

## Decisão de produto (funil bolão)

**Participar do bolão = pagante com PIX + liberação admin** (não gratuito global).

- Mantém o bolão sustentável e evita abuso.
- `origem = 'externo'` vs `'grupo'`.
- Conta do site pode existir **sem** `pode_bolao` até o PIX ser liberado.
- Módulos do WhatsApp: flags (`visivel_grupo_wa`, etc.) — leitura de Listra/Bans/Copypastas exige **conta logada** (ver `conta-site.md`).

## Checklist de implementação (bolão)

1. Reabrir/configurar janela de inscrição (`INSCRICAO_FECHA_EM` ou flag no admin).
2. Formulário de inscrição pedindo **e-mail** (obrigatório) + celular + comprovante.
3. Verificação leve de e-mail (link de confirmação) antes ou após liberação.
4. Captcha (Turnstile/hCaptcha) + rate limit persistente (não só memória do processo).
5. Após liberação: e-mail com link mágico + instrução para criar senha (em paralelo ao Zap).
6. Respeitar conta logada + flags nas rotas de escrita do bolão / grupo.
7. Flags `pode_bolao` / `pode_grid` respeitadas nas rotas de escrita.
8. Política de nome único e termos atualizados para público externo.

## Fora de escopo imediato

- OAuth Google / Apple
- WhatsApp Business API automática
- Bolão 100% gratuito sem fricção
- Implementar `/cadastro` de conta aqui (usar `conta-site.md` + Canvas)
