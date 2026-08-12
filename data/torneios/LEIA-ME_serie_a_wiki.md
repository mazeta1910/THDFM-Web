# Série A — classificações e artilheiros (Wikipedia)

Gerado por `scripts/scrape_serie_a_wiki.py` via API da pt.wikipedia.

## Arquivos

- `classificacoes_serie_a.csv` — tabelas finais **1959–2025** (1935 linhas), UTF-8 BOM, `;`
- `artilheiros_serie_a.csv` — artilheiros por edição (1937–2025), UTF-8 BOM, `;`
- `goleadas_serie_a.csv` — maiores goleadas por edição (export de `Goleadas.xlsx` aba Ligas), UTF-8 BOM, `;`

## Notas

- Classificações: prioriza seção **Classificação final** (depois geral). Inclui Taça Brasil / Robertão / mata-mata; posições refletem o desfecho do torneio, não só pontos.
- **1967–1968:** scrape usa o **Torneio Roberto Gomes Pedrosa** (há também Taça Brasil no Wiki).
- **1987:** a tabela capturada é a classificação do Módulo Verde (1º Flamengo). O título CBF é controverso (Sport).
- **Melhor ataque / mais gols por edição:** derivar do maior `gp` na classificação (não precisa de CSV extra).
- **Melhor/pior defesa, mais V/E/D:** derivar de `gc` / `v` / `e` / `d` por edição.
- **Rebaixado (Grid):** heurística — zona dos últimos 4 (n≥20) ou 2 (16≤n<20) a partir de 1988; edições mata-mata anteriores sem zona.
- **Goleadas:** por ano, maior `diff`; vencedor = aplicou, perdedor = sofreu, ambos = presente.
- Artilheiros (jogadores): lista agregada + override **2003–2025** pelas páginas anuais.
- Empates de artilharia: uma linha por jogador empatado no máximo de gols da edição.
- Nomes podem precisar de aliases no join FM.
- Dependência: `beautifulsoup4`.
- Erros do scrape de classificação: nenhum
- Divergências de campeão vs lista de checagem: nenhuma
