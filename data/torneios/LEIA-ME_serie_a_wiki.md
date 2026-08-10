# Série A — classificações e artilheiros (Wikipedia)

Gerado por `scripts/scrape_serie_a_wiki.py` via API da pt.wikipedia.

## Arquivos

- `classificacoes_serie_a.csv` — tabelas finais **2003–2025** (pontos corridos), UTF-8 BOM, `;`
- `artilheiros_serie_a.csv` — artilheiros por edição (1937–2025), UTF-8 BOM, `;`

## Notas

- Classificações: era pontos corridos; anos pré-2003 não inclusos neste scrape.
- Artilheiros: base na lista agregada da Wikipedia; **2003–2025** sobrescritos pelas páginas anuais (a lista agregada tem erros pontuais, ex. 2016).
- Empates de artilharia: uma linha por jogador empatado no máximo de gols da edição.
- Nomes podem precisar de aliases no join FM (`Atlético-MG` vs `Atlético Mineiro`, etc.).
- Dependência: `beautifulsoup4` (rowspan nas tabelas).
- Erros do scrape de classificação: nenhum
