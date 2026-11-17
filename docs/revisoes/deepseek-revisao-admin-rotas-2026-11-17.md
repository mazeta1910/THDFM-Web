# Revisão das rotas de admin — THDFM (17 nov 2026)

> Método: rotas auth-gated (todas `303 → /?acesso=entrar`), então a revisão é sobre **código** — template + handler de cada tela. Fonte: `src/app.py`, `templates/admin*.html`, `templates/partials/admin_sidebar.html`.
> Prioridade: `bug` = corrigir; `melhoria` = depois; `segurança` = antes de tudo.
>
> Fonte: DeepSeek (arquivo 1/3 enviado por Mazeta).

---

## 0. Resumo executivo

O painel tem **ótimas bases** (modais de confirmação com consequências explicadas, dirty-state + autosave, auditoria de ações, permissões por cap). Os problemas reais são: **um bug de perda de dado** (autosave × troca de fase), **uma defesa única de CSRF** (sem token), **uma ação em lote sem confirmação** (e-mail em massa), e **uma página monolítica de 1609 linhas** que carrega dois painéis inteiros sempre.

| # | Achado | Tipo | Onde |
|---|---|---|---|
| 1 | Autosave perde edição ao trocar de fase <1,8s | bug | `admin.html:1101-1111` + `:1011` |
| 2 | CSRF sem token (só `SameSite=Lax`) | segurança | `app.py:392`, `:779`, `:795` |
| 3 | "E-mail" em lote sem confirmação | bug | `admin_cobranca.html:61-71` |
| 4 | `/admin` monolítico (2 painéis + JS inline) | melhoria | `admin.html` (1609 linhas) |
| 5 | Listener duplicado | bug | `admin.html:786-800` |
| 6 | Palpites sem ordenar/filtrar/CSV | melhoria | `admin_palpites.html` |
| 7 | `aria-current` inconsistente + `<th>` vazio | a11y | vários |
| 8 | Cooldown do e-mail invisível | melhoria | `admin_cobranca.html` |

---

## 1. Palpites (`/admin/palpites`)

**O que está certo:** read-only (não edita), métricas com minimizar, export PNG, fase/perna com locked.

**Bugs**
- `—` duplicado: "sem palpite" ao lado do nome **e** `—` na célula de gols (`admin_palpites.html:246`). Duas sinalizações; `—` lê-se como "0 gols".
- `<th></th>` vazio na coluna do "x" (`:194`) — sem conteúdo acessível.

**Melhorias**
- Sem ordenação/busca/filtro; métrica "Sem palpite (n_sem)" sem link para filtrar. Aplicar contrato de tabela (ordenação por nome/acerto/total, filtro por nome, CSV).
- Perf: `montar_portal()` roda para a fase atual **e de novo para todas as fases** (`app.py:4121-4126`) só para `ranking_apostadores`. Cachear ou separar endpoint.
- Export só PNG; adicionar CSV.
- `role="tab"` sem `role="tablist"` no container.

---

## 2. Resultados (`/admin?sec=resultados`)

**O que está certo (não mexer):** modais de confirmação excelentes (Zerar/Fechar rodada/Avançar fase/Desfazer/janela/fase explicam consequências em bullets), dirty-state + autosave + sticky save, `save-ambas` (ida+volta juntas).

**Bugs**
1. **Autosave perde edição.** Debounce 1800ms (`admin.html:1105`); trocar de fase chama `syncZerarForm → refreshBaseline()` que faz `setDirty(false)` e re-snapshot da nova fase (`:1011`). Editar → trocar de fase <1,8s → edição perdida sem aviso. **Fix:** salvar (`salvarPlacaresAtivos`) o form atual antes de `showFasePerna`, ou cancelar o timer e salvar o antigo.
2. **Listener duplicado** (`:786-792` e `:793-800`): dois `forEach` idênticos em `.admin-side-link[data-sec]`; `showSection` roda 2×. Remover um.
3. **`postJson` com branch morto** (`:923-933`): os dois lados do `if/else` fazem o mesmo.

**Melhorias**
- `aria-current` mistura `"true"` e `"page"` (`:251`, `:1021` vs sidebar `"page"`). Padronizar `"page"`.
- "Abrir Meus Palpites em" (janela) vive dentro de Resultados, mas é controle de janela operacional do site — deslocado.
- **Monolítico:** `/admin` renderiza os 2 painéis + todas as fases + todos os participantes + ~400 linhas de JS inline. Separar `/admin/resultados` e `/admin/inscricoes` em rotas/templates próprios (o backend já computa `admin_sec`).

---

## 3. Inscrições (`/admin?sec=inscricoes`)

- Busca por nome/celular ok, mas não cobre username.
- **Confirmação inconsistente:** "Excluir" usa modal, "Inativar" usa `window.confirm()` (`admin.html:1217`). Unificar.
- Status "Ok" para liberado é vago → "Liberado".

---

## 4. Cobrança (`/admin/cobranca`)

1. **"E-mail" em lote sem confirmação** (`admin_cobranca.html:61-71`): `type=submit` direto, dispara e-mail real para todos os incompletos. Única ação em massa sem modal. Confirmar com contagem ("Enviar para N pessoas?").
2. **Cooldown invisível:** admin não sabe o último envio. Mostrar "último envio há Xh" / desabilitar com tooltip.
3. "Avisar" individual é `GET` (`app.py:4323`) — alinhar com o POST de celular.
4. Label `Quem palpitou` vs rota `/admin/cobranca` vs badge `cobranca_n` — renomear para "Cobranças" (já no menu v2).

---

## 5. Credenciais (`/admin/credenciais`)

- **Bom:** só Dono, busca + "ir para usuário" + flash, username/senha separados, "senha é hash" claro.
- Falta **link para auditoria** do usuário (trocar senha de outro é sensível; hoje o rastro fica só no Sistema→Atividade).

## 6. Permissões (`/admin/permissoes`)

- **Checkboxes flat sem descrição** (`admin_permissoes.html:23-38`): `grid.bugs`, `hall.gestir`, `acervo.gestir` sem explicar o que habilitam. Adicionar tooltip/descrição.
- **`sistema.*` omitido sem explicação** (`:24`): UI não diz que Sistema é não-delegável. Uma linha resolve.

---

## 7. Transversal / segurança

1. **CSRF sem token.** Nenhum form tem `csrf_token`; não há middleware de CSRF. A proteção é o cookie `samesite="lax"` (`app.py:779`, `:795`). Para POSTs de admin (apagar, zerar, redefinir senha, permissões, e-mail em lote), o padrão é token CSRF. `Lax` cobre a maioria, mas é **defesa única**. Adicionar token.
2. **`msg.replace('+', ' ')`** espalhado (`admin_permissoes.html:11-12`, `admin_credenciais.html:14-15`) — resíduo; FastAPI já decodifica o query param.
3. `admin_home` monta `confrontos_por_fase` para **todas** as fases (`app.py:6762-6765`) — mesmo peso da página monolítica.

---

## 8. Ordem sugerida

1. **CSRF token** nos POSTs de admin (segurança).
2. **Autosave × troca de fase** (bug de perda de dado).
3. **Confirm no e-mail em lote** (Cobrança).
4. **Separar `/admin/resultados` e `/admin/inscricoes`** (payload + IA + JS).
5. Contrato de tabela no Palpites; remover listener duplicado; padronizar `aria-current`; unificar confirmação.

## 9. Pronto quando (DoD)

- Trocar de fase durante edição **não** perde placar (teste de regressão do autosave).
- Todo POST de admin envia token CSRF e é rejeitado sem ele.
- "E-mail" em lote pede confirmação com contagem e mostra o último envio.
- Palpites ordena/filtra e exporta CSV do conjunto filtrado.
- Nenhum `<th>` vazio; `aria-current="page"` em todo item ativo.
