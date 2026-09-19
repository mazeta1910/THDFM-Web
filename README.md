# THDFM Web — FastAPI

Site da **THDFM** (Técnicos Horríveis do Futebol Mundial): bolão, Listra, Xonhômetro e outras páginas do grupo.

Stack: **FastAPI** (Python) sobre **Starlette** + **Pydantic**, servido por **Uvicorn**, com **SQLite** e templates **Jinja2**.

Repositório: [github.com/mazeta1910/THDFM-Web](https://github.com/mazeta1910/THDFM-Web)

> **Este README também é o entregável do trabalho.** Ele traz a apresentação do framework escolhido (FastAPI) e um tutorial de configuração com uma aplicação exemplo: um **CRUD de Clube** (cadastro de uma entidade), demonstrado com o código real deste repositório.

## Sumário

- [Parte 1 — Apresentação do FastAPI](#parte-1--apresentação-do-fastapi)
- [Parte 2 — Tutorial: configurar o FastAPI e criar um CRUD](#parte-2--tutorial-configurar-o-fastapi-e-criar-um-crud)
- [Parte 3 — Operação do THDFM Web](#parte-3--operação-do-thdfm-web)
- [Referências](#referências)

---

# Parte 1 — Apresentação do FastAPI

## O que é

**FastAPI** é um framework web para Python: ele é a "cola" que recebe os pedidos do navegador e devolve as respostas de uma aplicação ou API. Na prática, o FastAPI é uma **camada de conveniência** montada sobre duas peças já prontas e consagradas (LEAPCELL, 2025) — mais ou menos como uma montadora que junta um motor e um chassi testados, em vez de fabricar tudo do zero:

- **Starlette — a base web.** É quem faz o trabalho de servidor: cuida do roteamento, das requisições e respostas, dos WebSockets e dos **middlewares**. Um middleware é como um "porteiro" por onde todo pedido passa antes e depois de ser atendido (ex.: registro de logs, liberar *Cross-Origin Resource Sharing* (CORS)).
- **Pydantic — os dados.** Funciona como um "formulário com regras": você descreve os campos que espera (por exemplo, `nome` é texto e `preço` é número) e ele **lê, confere e organiza** os dados que chegam. Se vier algo errado, avisa com uma mensagem clara; se estiver tudo certo, entrega os dados validados e prontos para virar JSON.

**Como os dois se juntam:** o Starlette recebe e encaminha o pedido, o Pydantic valida e organiza os dados, e o FastAPI ainda monta **sozinho** uma documentação interativa (a página `/docs`), onde dá para testar tudo pelo navegador. É essa combinação que deixa o FastAPI produtivo e, ao mesmo tempo, rápido.

## Principais características

- **Validação automática com _type hints_.** Os _type hints_, ou "dicas de tipo", foram introduzidos no Python para permitir que os desenvolvedores indiquem explicitamente os tipos de dados das variáveis e dos retornos de funções (GOMES, 2024). A partir dessas anotações, o FastAPI valida e converte os dados de entrada e saída automaticamente, evitando muito _boilerplate_ (código repetitivo de configuração que apareceria em vários lugares).
- **Documentação automática (OpenAPI).** O FastAPI gera sozinho uma página interativa em `/docs` (e uma versão alternativa em `/redoc`) para testar a API pelo navegador. Ela segue o **OpenAPI** (ou _OpenAPI Specification_, OAS), um padrão universal para descrever e documentar APIs REST de forma que tanto humanos quanto máquinas consigam ler e entender (NOSOWITZ; GOODWIN, 2026).
- **Alto desempenho.** É construído para atender muitos pedidos ao mesmo tempo; entre os frameworks Python, está entre os mais rápidos.
- **Assíncrono (`async`/`await`).** Suporta o modelo assíncrono do Python, útil quando a aplicação fica "esperando" o banco de dados ou uma resposta externa — nesse meio-tempo ela consegue atender outros pedidos.
- **Injeção de dependências (`Depends`).** Mecanismo que entrega automaticamente "peças" prontas (login, sessão, acesso ao banco) às rotas que as declaram, sem repetir código.
- **Recursos web completos.** Formulários, upload de arquivos, cookies/sessões, tempo real (WebSockets), páginas HTML (via Jinja2) e arquivos estáticos.

## Linguagem, framework e plataforma — vantagens e desvantagens

| Camada | Vantagens | Desvantagens |
|--------|-----------|--------------|
| **Linguagem (Python)** | Código fácil de ler e escrever; enorme quantidade de bibliotecas prontas; roda em qualquer sistema; ótima para prototipar rápido e para dados/IA. | Em cálculos pesados é mais lenta que linguagens como Go/Rust; por causa do **GIL** (_Global Interpreter Lock_, uma trava interna do interpretador), cada processo executa só um trecho de código Python por vez. |
| **Framework (FastAPI)** | Pouco código repetitivo; validação e documentação automáticas; os _type hints_ ajudam a evitar erros; documentação oficial excelente. | É relativamente novo (2018); vem "sem muitos extras" — não traz banco de dados, painel de administração nem login prontos (você escolhe as bibliotecas para isso). |
| **Plataforma (ASGI)** | Atende muitas conexões ao mesmo tempo, tempo real (WebSockets) e streaming. | Exige um servidor no padrão **ASGI** (_Asynchronous Server Gateway Interface_); os servidores no padrão antigo, **WSGI** (_Web Server Gateway Interface_), não rodam sem adaptação. E, se o código assíncrono for mal escrito, ele pode bloquear o _event loop_ (o laço que processa um evento por vez) e "segurar a fila" dos demais pedidos. |

## Servidores web disponíveis

FastAPI é **ASGI**, então roda em servidores ASGI:

- **Uvicorn** — o mais usado (e o adotado neste projeto). Baseado em `uvloop`/`httptools`.
- **Hypercorn** — suporta HTTP/2 e HTTP/3.
- **Daphne** — servidor ASGI do projeto Django Channels.

Em **produção** o padrão é rodar o **Gunicorn** coordenando vários processos Uvicorn (`gunicorn -k uvicorn.workers.UvicornWorker`) atrás de um **proxy reverso** — um intermediário que fica na frente da aplicação, como o Nginx ou o Caddy — ou de um túnel/CDN (Cloudflare). Neste repositório usamos o Uvicorn diretamente e, para expor na internet, um **Cloudflare Tunnel** (ver Parte 3).

## Configuração necessária para rodar

- **Python 3.10+** (este projeto foi validado no **3.12**).
- Um **ambiente virtual** (`venv`).
- Dependências via `pip` (arquivo `requirements.txt`): `fastapi`, `uvicorn[standard]`, `jinja2`, `python-multipart` (formulários/upload), `itsdangerous` (sessões), `python-dotenv` (variáveis de ambiente) etc.
- Um arquivo **`.env`** com as variáveis (ex.: `SECRET_KEY`, `ADMIN_USERS`).
- Executar com o Uvicorn: `uvicorn src.app:app --reload`.

Não é necessário instalar banco separado: o **SQLite** é um arquivo (`data/bolao.db`) e já vem no Python (`sqlite3`).

## Licença

Todos os componentes principais são **open source e permissivos**:

| Componente | Licença | 
|-----------|---------|
| FastAPI | **MIT** |
| Starlette | **BSD-3-Clause** |
| Uvicorn | **BSD-3-Clause** |
| Pydantic | **MIT** |
| Python (CPython) | **PSF License** |

Licenças MIT/BSD/PSF permitem uso comercial, modificação e distribuição, exigindo basicamente a manutenção do aviso de copyright.

## Responsáveis pelo desenvolvimento

- **FastAPI** foi **criado e é mantido por Sebastián Ramírez (`@tiangolo`)** (RAMÍREZ, 2018), com uma **comunidade** open source ativa no GitHub.
- **Starlette** e **Uvicorn** são mantidos pela **Encode** (liderada por **Tom Christie**) e comunidade.
- **Pydantic** foi criado por **Samuel Colvin** e comunidade.

Ou seja: projeto de **comunidade** (não de uma única empresa proprietária), com mantenedores de referência bem definidos.

## Conclusões sobre o uso do framework

- **Documentação oficial excelente e didática**: o [tutorial oficial](https://fastapi.tiangolo.com/) é passo a passo e cobre praticamente tudo com exemplos.
- **Fácil achar material** (GitHub, Stack Overflow, cursos, vídeos) e a **qualidade** costuma ser boa por causa da tipagem e dos exemplos oficiais.
- **Configuração simples**: `pip install` + `uvicorn` e a aplicação já sobe; as **docs automáticas em `/docs`** aceleram muito os testes durante o desenvolvimento.
- **Pontos de atenção**: como não vem com banco de dados, login e painel de administração prontos, essas escolhas ficam com você (aqui usamos `sqlite3` puro + Jinja2). E o modelo assíncrono pede cuidado para que um pedido demorado não "segure a fila" dos demais.
- **Veredito**: ótima escolha para APIs e aplicações web modernas em Python — produtivo, rápido e com uma curva de aprendizado tranquila para quem já conhece Python.

---

# Parte 2 — Tutorial: configurar o FastAPI e criar um CRUD

Vamos configurar o FastAPI e implementar um **CRUD** (Create, Read, Update, Delete) simples para a entidade **Clube**. É exatamente o padrão usado neste repositório no **cadastro de Clubes do Acervo** — no fim mostramos onde ver o código real rodando.

**Entidade `Clube`:** `nome`, `nome_popular`, `uf`, `fm_unique_id`, `estadio`, `treinador`, `extinto`, `notas`.

## Pré-requisitos

- Python 3.10+ instalado (`python --version`).
- Noções de terminal.

## 1. Ambiente e instalação

Linux/macOS:

```bash
mkdir crud-clube && cd crud-clube
python -m venv .venv
source .venv/bin/activate
pip install fastapi "uvicorn[standard]" jinja2 python-multipart
```

Windows (PowerShell):

```powershell
mkdir crud-clube; cd crud-clube
py -m venv .venv
.venv\Scripts\activate
pip install fastapi "uvicorn[standard]" jinja2 python-multipart
```

> `python-multipart` é necessário para receber **formulários HTML** (`Form(...)`).

## 2. Estrutura do projeto

```
crud-clube/
├─ main.py            # app FastAPI + rotas
├─ db.py              # acesso ao SQLite
├─ templates/
│  └─ clubes.html     # lista + formulário (Jinja2)
└─ data/              # banco SQLite (criado em runtime)
```

## 3. Modelo de dados (SQLite) — tabela `clube`

O SQLite é um arquivo; a tabela é criada com um `CREATE TABLE IF NOT EXISTS`. Esquema (equivalente ao real em `src/db.py`, função `_migrate_acervo`):

```sql
CREATE TABLE IF NOT EXISTS clube (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  nome          TEXT NOT NULL,
  nome_popular  TEXT NOT NULL DEFAULT '',
  uf            TEXT NOT NULL DEFAULT '',
  fm_unique_id  TEXT,
  estadio       TEXT NOT NULL DEFAULT '',
  treinador     TEXT NOT NULL DEFAULT '',
  extinto       INTEGER NOT NULL DEFAULT 0,
  notas         TEXT NOT NULL DEFAULT '',
  criado_em     TEXT NOT NULL DEFAULT (datetime('now','localtime')),
  atualizado_em TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
```

## 4. Camada de dados (`db.py`) — funções CRUD

```python
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path("data/bolao.db")

@contextmanager
def get_db():
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row          # devolve linhas como dict-like
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS clube (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              nome TEXT NOT NULL,
              nome_popular TEXT NOT NULL DEFAULT '',
              uf TEXT NOT NULL DEFAULT '',
              fm_unique_id TEXT,
              estadio TEXT NOT NULL DEFAULT '',
              treinador TEXT NOT NULL DEFAULT '',
              extinto INTEGER NOT NULL DEFAULT 0,
              notas TEXT NOT NULL DEFAULT ''
            )
        """)

# READ (lista, com busca opcional por nome)
def list_clubes(q: str | None = None):
    with get_db() as conn:
        if q:
            rows = conn.execute(
                "SELECT * FROM clube WHERE nome LIKE ? ORDER BY nome COLLATE NOCASE",
                (f"%{q}%",),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM clube ORDER BY nome COLLATE NOCASE"
            ).fetchall()
    return [dict(r) for r in rows]

# READ (um registro)
def get_clube(clube_id: int):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM clube WHERE id = ?", (clube_id,)).fetchone()
    return dict(row) if row else None

# CREATE
def criar_clube(nome, nome_popular="", uf="", estadio="", treinador="", notas="", extinto=False):
    with get_db() as conn:
        cur = conn.execute(
            """INSERT INTO clube (nome, nome_popular, uf, estadio, treinador, notas, extinto)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (nome, nome_popular, uf, estadio, treinador, notas, int(extinto)),
        )
        return cur.lastrowid

# UPDATE
def atualizar_clube(clube_id, nome, nome_popular="", uf="", estadio="", treinador="", notas="", extinto=False):
    with get_db() as conn:
        conn.execute(
            """UPDATE clube
                  SET nome=?, nome_popular=?, uf=?, estadio=?, treinador=?, notas=?, extinto=?
                WHERE id=?""",
            (nome, nome_popular, uf, estadio, treinador, notas, int(extinto), clube_id),
        )

# DELETE
def apagar_clube(clube_id: int) -> bool:
    with get_db() as conn:
        cur = conn.execute("DELETE FROM clube WHERE id = ?", (clube_id,))
        return cur.rowcount > 0
```

> No repositório real essas funções ficam em `src/db.py` (`criar_acervo_clube`, `atualizar_acervo_clube`, `apagar_acervo_clube`, `list_acervo_clubes`, `get_acervo_clube`) e ainda **normalizam/validam** os campos (UF, nome, ID único do FM etc.).

## 5. Rotas CRUD (FastAPI)

Aqui usamos **páginas renderizadas com Jinja2** (formulários HTML), como o projeto faz. Note o padrão do repo: **uma rota `salvar`** cria (sem `id`) ou atualiza (com `id`).

```python
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import db

app = FastAPI(title="CRUD de Clube")
templates = Jinja2Templates(directory="templates")

@app.on_event("startup")
def _startup():
    db.init_db()

# READ — lista + busca
@app.get("/clubes", response_class=HTMLResponse)
def listar(request: Request, q: str | None = None, editar: int | None = None):
    return templates.TemplateResponse("clubes.html", {
        "request": request,
        "clubes": db.list_clubes(q),
        "q": q or "",
        "edit": db.get_clube(editar) if editar else None,
    })

# CREATE + UPDATE (mesma rota; tem id => update)
@app.post("/clubes/salvar")
def salvar(
    id: str = Form(""),
    nome: str = Form(...),
    nome_popular: str = Form(""),
    uf: str = Form(""),
    estadio: str = Form(""),
    treinador: str = Form(""),
    notas: str = Form(""),
    extinto: str = Form(""),
):
    is_extinto = extinto in ("1", "on", "true")
    if id.strip():
        db.atualizar_clube(int(id), nome, nome_popular, uf, estadio, treinador, notas, is_extinto)
    else:
        db.criar_clube(nome, nome_popular, uf, estadio, treinador, notas, is_extinto)
    return RedirectResponse("/clubes", status_code=303)

# DELETE
@app.post("/clubes/apagar")
def apagar(id: int = Form(...)):
    db.apagar_clube(id)
    return RedirectResponse("/clubes", status_code=303)
```

> **Bônus (o diferencial do FastAPI):** dá para expor uma **API JSON** com validação e docs automáticas usando Pydantic:
>
> ```python
> from pydantic import BaseModel
>
> class ClubeIn(BaseModel):
>     nome: str
>     uf: str = ""
>     estadio: str = ""
>     treinador: str = ""
>
> @app.post("/api/clubes")
> def api_criar(clube: ClubeIn):
>     cid = db.criar_clube(clube.nome, uf=clube.uf, estadio=clube.estadio, treinador=clube.treinador)
>     return {"id": cid, **clube.model_dump()}
> ```
>
> Abra **`/docs`** e teste esse endpoint pelo navegador — a documentação é gerada sozinha.

## 6. Templates (Jinja2)

`templates/clubes.html` — formulário (cria/edita) + tabela com ações:

```html
<!doctype html>
<html lang="pt-BR">
<head><meta charset="utf-8"><title>Clubes</title></head>
<body>
  <h1>Clubes</h1>

  <!-- Busca -->
  <form method="get" action="/clubes">
    <input name="q" value="{{ q }}" placeholder="Buscar por nome...">
    <button>Buscar</button>
  </form>

  <!-- Criar / Editar -->
  <form method="post" action="/clubes/salvar">
    <input type="hidden" name="id" value="{{ edit.id if edit else '' }}">
    <input name="nome" placeholder="Nome" required value="{{ edit.nome if edit else '' }}">
    <input name="uf" placeholder="UF" value="{{ edit.uf if edit else '' }}">
    <input name="estadio" placeholder="Estádio" value="{{ edit.estadio if edit else '' }}">
    <input name="treinador" placeholder="Treinador" value="{{ edit.treinador if edit else '' }}">
    <label><input type="checkbox" name="extinto" value="1" {{ 'checked' if edit and edit.extinto else '' }}> Extinto</label>
    <button>{{ 'Atualizar' if edit else 'Salvar' }}</button>
  </form>

  <!-- Lista -->
  <table border="1" cellpadding="6">
    <tr><th>Nome</th><th>UF</th><th>Estádio</th><th>Treinador</th><th></th></tr>
    {% for c in clubes %}
    <tr>
      <td>{{ c.nome }}</td><td>{{ c.uf }}</td><td>{{ c.estadio }}</td><td>{{ c.treinador }}</td>
      <td>
        <a href="/clubes?editar={{ c.id }}">editar</a>
        <form method="post" action="/clubes/apagar" style="display:inline"
              onsubmit="return confirm('Apagar {{ c.nome }}?')">
          <input type="hidden" name="id" value="{{ c.id }}">
          <button>apagar</button>
        </form>
      </td>
    </tr>
    {% endfor %}
  </table>
</body>
</html>
```

## 7. Rodar e testar

```bash
uvicorn main:app --reload
```

- Interface do CRUD: <http://127.0.0.1:8000/clubes>
- Documentação automática (API): <http://127.0.0.1:8000/docs>

Fluxo para demonstrar: **criar** um clube → **listar** → **editar** → **buscar** → **apagar**.

## 8. Onde ver o CRUD real neste repositório

O mesmo padrão está em produção no cadastro de **Clubes do Acervo**:

| Parte | Arquivo | Detalhe |
|------|---------|---------|
| Esquema (tabela) | `src/db.py` | função `_migrate_acervo` → `CREATE TABLE ... acervo_clubes` |
| Funções CRUD | `src/db.py` | `criar_acervo_clube`, `atualizar_acervo_clube`, `apagar_acervo_clube`, `list_acervo_clubes`, `get_acervo_clube` |
| Rotas | `src/app.py` | `admin_acervo` (GET, lista), `admin_acervo_clube_salvar` (POST, cria/atualiza), `admin_acervo_clube_apagar` (POST) |
| Template | `templates/admin_acervo.html` | seção **Clubes** (form + tabela + busca/paginação) |

Para ver rodando: suba o servidor (Parte 3), entre em `/admin/login` como `mazeta` e acesse **`/admin/acervo?sec=clubes`**. Lá há **busca, paginação, criar, editar e apagar** — o CRUD completo.

## Roteiro de apresentação (15–30 min)

1. **(3 min)** O que é o FastAPI + principais características — abrir `/docs` ao vivo.
2. **(3 min)** Vantagens/desvantagens, servidores web, licença e mantenedores.
3. **(3 min)** Configuração: `venv` → `pip install` → `uvicorn`.
4. **(10–15 min)** Tutorial do CRUD: mostrar o esquema, o `db.py`, as rotas e o template; depois demonstrar o **CRUD real de Clubes** em `/admin/acervo?sec=clubes` (criar/editar/buscar/apagar).
5. **(3 min)** Conclusões sobre o uso do framework.

---

# Parte 3 — Operação do THDFM Web

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
| Acervo (admin) | `/admin/acervo` |
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

1. Participantes se inscrevem em `/inscricao` (PIX + comprovante) **ou** você cadastra no admin (opção "já pagou").
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

---

# Referências

Referências no formato ABNT (NBR 6023). As datas de acesso devem ser ajustadas para a data de entrega do trabalho.

- ENCODE. **Starlette**. [S. l.], [entre 2018 e 2025]. Disponível em: https://www.starlette.io/. Acesso em: 19 set. 2026.
- ENCODE. **Uvicorn**. [S. l.], [entre 2017 e 2025]. Disponível em: https://www.uvicorn.org/. Acesso em: 19 set. 2026.
- GOMES, Ana Maria. **Type Hints em Python: Um Guia Completo**. Asimov Academy, 28 maio 2024. Disponível em: https://hub.asimov.academy/tutorial/type-hints-em-python-um-guia-completo/. Acesso em: 19 set. 2026.
- LEAPCELL. **FastAPI is Overkill: Starlette and Pydantic Are All You Really Need**. DEV Community, 12 abr. 2025. Disponível em: https://dev.to/leapcell/fastapi-is-overkill-starlette-and-pydantic-are-all-you-really-need-1inp. Acesso em: 19 set. 2026.
- NOSOWITZ, Dan; GOODWIN, Michael. **O que é OpenAPI?**. IBM Think, 24 fev. 2026. Disponível em: https://www.ibm.com/br-pt/think/topics/open-api. Acesso em: 19 set. 2026.
- PYDANTIC. **Pydantic Documentation**. [S. l.], [entre 2017 e 2025]. Disponível em: https://docs.pydantic.dev/. Acesso em: 19 set. 2026.
- PYTHON SOFTWARE FOUNDATION. **Python 3 Documentation**. [S. l.], [entre 2001 e 2025]. Disponível em: https://docs.python.org/3/. Acesso em: 19 set. 2026.
- RAMÍREZ, Sebastián. **FastAPI**. [S. l.], 2018. Disponível em: https://fastapi.tiangolo.com/. Acesso em: 19 set. 2026.
