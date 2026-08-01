# THDFM Web

Site da **THDFM** (Técnicos Horríveis do Futebol Mundial): bolão, Listra, Xonhômetro e outras páginas do grupo.

Stack: **FastAPI** + **SQLite**. Roda no PC; dá para expor com Cloudflare Tunnel.

Repositório: [github.com/mazeta1910/THDFM-Web](https://github.com/mazeta1910/THDFM-Web)

## Subir local

```bash
cd THDFM-Web
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn src.app:app --host 0.0.0.0 --port 8000 --reload
```

Abra http://127.0.0.1:8000

### Rotas principais

| Área | Caminho |
|------|---------|
| Home | `/` · `/home` |
| Bolão — inscrição | `/inscricao` |
| Bolão — palpites / conta | `/p/{token}` |
| Bolão — classificação | `/classificacao` |
| Regras | `/regras` |
| Listra | `/grupo/listra` |
| Xonhômetro | `/xonhometro` |
| Banimentos | `/grupo/bans` |
| Transparência | `/transparencia` |
| Admin | `/admin/login` |

Banco: `data/bolao.db`. Comprovantes: `data/comprovantes/`. Avatares: `data/avatars/`. Emblemas: `data/emblemas/*.png`. Seeds da Listra: `data/listra/`.

## Túnel (link público)

1. Instale [cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation/).
2. Com o uvicorn rodando:

```bash
cloudflared tunnel --url http://127.0.0.1:8000
```

3. O cloudflared imprime uma URL tipo `https://xxxx.trycloudflare.com`.
4. Cole no `.env`:

```env
PUBLIC_BASE_URL=https://xxxx.trycloudflare.com
```

5. Reinicie o uvicorn. No admin, os links passam a usar essa URL (e não o IP da rede).

**O que mandar para quem:**

| Para quem | Link |
|-----------|------|
| Todo o grupo (inscrição no bolão) | `PUBLIC_BASE_URL/inscricao` |
| Cada pessoa (depois de liberar) | `PUBLIC_BASE_URL/p/{token}` no privado |
| Site em geral | `PUBLIC_BASE_URL/` |

PC ligado + uvicorn + túnel = site no ar. A cada reinício do túnel *rápido* (`trycloudflare`), a URL muda — atualize o `.env`.

## Header (rotas)

- Visitante: **Home**, páginas do grupo, **Inscrição**, **Regras**, **Admin**
- Com link de participante: **Palpites** / status, **Classificação** (se liberado), **Regras**, **Conta**
- Admin logado: **Admin** + nome na nav + **Sair**

## Acesso dos admins (Mazeta, Ramos, João JEC)

Cada um tem usuário e senha próprios no `.env`:

```env
ADMIN_USERS=mazeta=SENHA1=Mazeta:dono|ramos=SENHA2=Ramos:moderador|joaojec=SENHA3=João JEC:adminzinho
```

Formato: `login=senha=Nome[:papel]` separados por `|`.

Papéis:
- **Dono** (`dono` / `sagrado`) — Mazeta: tudo + painel `/admin/credenciais` (ver username e redefinir senha; senha antiga nunca aparece).
- **Moderador** (`moderador` / `adminzinho`) — Ramos e João JEC: inscrições, resultados, palpites, links. Sem apagar em massa nem credenciais.

1. Compartilhe a URL pública do túnel.
2. Cada um abre `/admin/login` com o **próprio** usuário/senha (isso ativa o botão Admin/Site).
3. A nav mostra o nome + papel + **Sair**.

## Bolão — fluxo admin

1. Participantes se inscrevem em `/inscricao` (PIX + comprovante) **ou** você cadastra no admin (opção “já pagou”).
2. Em **Inscrições**, abrir comprovante → **Liberar** (ou Recusar).
3. Janela **ida** → grupo palpita pelos links.
4. Lançar placares de ida → abrir janela **volta**.
5. Grupo palpita volta → lançar voltas / pênaltis → **fechado** → confirmar rodada.

## Testes

```bash
pytest -q
```

## Pontuação do bolão (resumo)

| Fase | Placar | Vencedor | Gols | Fid. máx. |
|------|--------|----------|------|-----------|
| Oitavas | 10 | 7 | 5 | 5 |
| Quartas | 14 | 10 | 7 | 7 |
| Semis | 18 | 13 | 9 | 9 |
| Final | 24 | 17 | 12 | 12 |

Pênaltis: mesma lógica do bolão da Copa do Mundo (quem você apontou para passar).
