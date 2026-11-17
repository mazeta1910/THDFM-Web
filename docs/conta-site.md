# Conta do site ≠ inscrição no bolão

Doc canônico (produto). **Só documentação** — cadastro ainda não implementado; UI nova exige Canvas + “pode implementar”.

## Dois funis

| Funil | Para quê | Dinheiro | Resultado |
|-------|----------|----------|-----------|
| **Conta do site** | Login no THDFM: perfil, Grid, Hall, Listra, Bans, Copypastas, etc. | Grátis (cadastro) | Conta autenticada |
| **Inscrição no bolão** | Entrar no bolão CdB do ciclo | PIX + comprovante + liberação admin | `pode_bolao` / participante liberado |

Não misturar no admin Inscrições: aquele painel é do **bolão** (cadastro manual / comprovante). Contas do site terão gestão própria quando existirem (ex.: Contas / Pessoas) — **não** reabrir o fluxo antigo de “liberar link” de inscrição pública.

## Conta do site (fechado — campos)

Cadastro `/cadastro` (futuro) pede:

1. **Nome**
2. **Sobrenome**
3. **Username**
4. **E-mail**
5. **Senha** + **confirmar senha**
6. **Time(s) do coração** — um ou mais; ficam no **perfil**; **não** alimentam o Grid
7. **Aceite de termos** / avisos padrão de cadastro
8. **Tag Zap** — opção do tipo “Quer entrar no grupo de WhatsApp da página?”
9. **Captcha** (Turnstile / hCaptcha ou equivalente)

Login: mesmo Entrar da home (já unificado com o painel).

### Features que exigem conta

- **Listra**, **Bans**, **Copypastas**: só com conta logada (não anônimo).
- Demais áreas públicas de leitura (ex.: Classificação, Regras) continuam conforme o produto atual; escrita / participação em módulos de grupo seguem a conta + flags futuras (`visivel_grupo_wa`, etc.).

### Fora deste funil

- PIX, comprovante, taxa, liberação de participante do bolão
- OAuth Google/Apple
- WhatsApp Business API automática
- Bolão 100% gratuito sem fricção

## Inscrição no bolão (próximos ciclos)

Modelo mantido: **PIX + comprovante + liberação admin**. Detalhe operacional legado (janela, e-mail, flags) em `docs/sprint-seguinte-cadastro-externo.md` — aquele arquivo descreve o funil **bolão**, não o cadastro gratuito de conta.

Ordem sugerida de implementação (produto):

1. Docs + Canvas `/cadastro` → consenso → implementar **conta do site**
2. Depois (ou em paralelo com flags): reabrir inscrição **bolão** PIX sem confundir Inscrições

## Relacionados

- Backlog: `docs/backlog/bolao.md`
- Snapshot Harness: `docs/backlog/SNAPSHOT-2026-11-17-para-revisao.md` §3.1
- Sprint legado (bolão PIX): `docs/sprint-seguinte-cadastro-externo.md` (**superseded** para “conta do site”; ainda válido como checklist do funil PIX)
