# Dados históricos do Grid — fontes locais em `data/torneios/`

Não usar scrape sob demanda: os dumps/CSV/XLSX desta pasta são a fonte.

## Fontes brutas (levantamento)

| Arquivo | Uso no Grid |
|---|---|
| `classificacoes_serie_a.csv` | Série A (já normalizado) |
| `artilheiros_serie_a.csv` | Artilheiros Série A |
| `Serie B.xlsx` | Tabelas completas Série B (aba `Brasileirao Serie B`) |
| `Brasileirao Serie B.CSV` | Dump wiki auxiliar (top 4 / histórico) |
| `Série C.xlsx` / `Serie C.CSV` | Classificações Série C |
| `Copa do Brasil.CSV` | Campeões / vices da Copa |
| `Goleadas.xlsx` | Goleadas Série A/B + Copa |

## Artefatos normalizados (gerados localmente)

`scripts/extract_torneios_locais.py` (via `extract_serie_b_from_xlsx.py` e `extract_serie_c_classif.py`) produzem:

- `classificacoes_serie_b.csv` — tabelas finais do `Serie B.xlsx`
- `classificacoes_serie_c.csv` — tabelas finais aproveitáveis do xlsx
- `campeoes_copa_do_brasil.csv`
- `goleadas_ligas.csv` / `goleadas_serie_a.csv` / `goleadas_copa_do_brasil.csv`

### Série B — anos sem disputa

Não houve Série B nestes anos (ausência esperada, não lacuna de export):

`1973, 1974, 1975, 1976, 1977, 1978, 1979, 1993, 2000`

## Categorias

- **Série A:** conjunto completo (classificação + artilheiros + goleadas)
- **Série B:** classificação completa (stats, rebaixamento, longevidade) + goleadas por edição
- **Série C:** espelho das categorias de classificação (+ rebaixamento)
- **Copa do Brasil:** campeão / vice + maiores goleadas históricas
- **Série D:** sem arquivo local nesta pasta — fora do pool por enquanto
