# Dados históricos do Grid — fontes locais em `data/torneios/`

Não usar scrape sob demanda: os dumps/CSV/XLSX desta pasta são a fonte.

## Fontes brutas (levantamento)

| Arquivo | Uso no Grid |
|---|---|
| `classificacoes_serie_a.csv` | Série A (já normalizado) |
| `artilheiros_serie_a.csv` | Artilheiros Série A |
| `Brasileirao Serie B.CSV` | Top 4 por edição (linhas `Detalhes`) |
| `Série C.xlsx` / `Serie C.CSV` | Classificações Série C |
| `Copa do Brasil.CSV` | Campeões / vices da Copa |
| `Goleadas.xlsx` | Goleadas Série A/B + Copa |

## Artefatos normalizados (gerados localmente)

`scripts/extract_torneios_locais.py` (e `extract_serie_c_classif.py`) produzem:

- `classificacoes_serie_b.csv` — só posições 1–4 (o dump B não traz tabela completa limpa)
- `classificacoes_serie_c.csv` — tabelas finais aproveitáveis do xlsx
- `campeoes_copa_do_brasil.csv`
- `goleadas_ligas.csv` / `goleadas_serie_a.csv` / `goleadas_copa_do_brasil.csv`

## Categorias

- **Série A:** conjunto completo (classificação + artilheiros + goleadas)
- **Série B:** campeão / vice / G4 + goleadas por edição
- **Série C:** espelho das categorias de classificação (+ rebaixamento)
- **Copa do Brasil:** campeão / vice + maiores goleadas históricas
- **Série D:** sem arquivo local nesta pasta — fora do pool por enquanto
