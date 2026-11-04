# Sprint seguinte — cadastro para usuários externos

Pré-requisitos (sprint fundação do portal):

- [x] VPS 24/7 + `/health` + backup
- [x] Esqueci senha por e-mail
- [x] Homepage / nav portal vs Grupo WA
- [x] Capabilities no admin (`/admin/permissoes`)
- [x] Schema mínimo: `email`, `origem`, `pode_bolao`, `visivel_grupo_wa`, `pode_grid`

## Decisão de produto (recomendada)

**Externo = pagante com PIX + liberação admin** (não gratuito global).

- Mantém o bolão sustentável e evita abuso.
- `origem = 'externo'` vs `'grupo'`.
- Módulos do WhatsApp (`visivel_grupo_wa=0` por padrão para externos).

## Checklist de implementação

1. Reabrir/configurar janela de inscrição (`INSCRICAO_FECHA_EM` ou flag no admin).
2. Formulário de inscrição pedindo **e-mail** (obrigatório) + celular + comprovante.
3. Verificação leve de e-mail (link de confirmação) antes ou após liberação.
4. Captcha (Turnstile/hCaptcha) + rate limit persistente (não só memória do processo).
5. Após liberação: e-mail com link mágico + instrução para criar senha (em paralelo ao Zap).
6. Nav: ocultar Listra/Bans/Copypastas se `visivel_grupo_wa` for falso.
7. Flags `pode_bolao` / `pode_grid` respeitadas nas rotas de escrita.
8. Política de nome único e termos atualizados para público externo.

## Fora de escopo imediato

- OAuth Google / Apple
- WhatsApp Business API automática
- Bolão 100% gratuito sem fricção
