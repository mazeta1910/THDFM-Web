#!/usr/bin/env python3
"""Baixa bandeiras das UFs brasileiras do Wikimedia Commons (SVG).

Não faz scrap de HTML: usa URLs estáveis de upload.wikimedia.org.
Requer rede. Uso:

    python scripts/baixar_bandeiras_uf.py
"""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "bandeiras-uf"
META_PATH = OUT_DIR / "ufs.json"

# Fonte: Wikimedia Commons (bandeiras oficiais / representações oficiais).
# Arquivos salvos como {UF}.svg
UFS: list[dict[str, str]] = [
    {"uf": "AC", "nome": "Acre", "regiao": "Norte", "arquivo": "Bandeira_do_Acre.svg"},
    {"uf": "AL", "nome": "Alagoas", "regiao": "Nordeste", "arquivo": "Bandeira_de_Alagoas.svg"},
    {"uf": "AP", "nome": "Amapá", "regiao": "Norte", "arquivo": "Bandeira_do_Amapá.svg"},
    {"uf": "AM", "nome": "Amazonas", "regiao": "Norte", "arquivo": "Bandeira_do_Amazonas.svg"},
    {"uf": "BA", "nome": "Bahia", "regiao": "Nordeste", "arquivo": "Bandeira_da_Bahia.svg"},
    {"uf": "CE", "nome": "Ceará", "regiao": "Nordeste", "arquivo": "Bandeira_do_Ceará.svg"},
    {
        "uf": "DF",
        "nome": "Distrito Federal",
        "regiao": "Centro-Oeste",
        "arquivo": "Bandeira_do_Distrito_Federal_(Brasil).svg",
    },
    {
        "uf": "ES",
        "nome": "Espírito Santo",
        "regiao": "Sudeste",
        "arquivo": "Bandeira_do_Espírito_Santo.svg",
    },
    {"uf": "GO", "nome": "Goiás", "regiao": "Centro-Oeste", "arquivo": "Bandeira_de_Goiás.svg"},
    {"uf": "MA", "nome": "Maranhão", "regiao": "Nordeste", "arquivo": "Bandeira_do_Maranhão.svg"},
    {
        "uf": "MT",
        "nome": "Mato Grosso",
        "regiao": "Centro-Oeste",
        "arquivo": "Bandeira_de_Mato_Grosso.svg",
    },
    {
        "uf": "MS",
        "nome": "Mato Grosso do Sul",
        "regiao": "Centro-Oeste",
        "arquivo": "Bandeira_de_Mato_Grosso_do_Sul.svg",
    },
    {
        "uf": "MG",
        "nome": "Minas Gerais",
        "regiao": "Sudeste",
        "arquivo": "Bandeira_de_Minas_Gerais.svg",
    },
    {"uf": "PA", "nome": "Pará", "regiao": "Norte", "arquivo": "Bandeira_do_Pará.svg"},
    {"uf": "PB", "nome": "Paraíba", "regiao": "Nordeste", "arquivo": "Bandeira_da_Paraíba.svg"},
    {"uf": "PR", "nome": "Paraná", "regiao": "Sul", "arquivo": "Bandeira_do_Paraná.svg"},
    {"uf": "PE", "nome": "Pernambuco", "regiao": "Nordeste", "arquivo": "Bandeira_de_Pernambuco.svg"},
    {"uf": "PI", "nome": "Piauí", "regiao": "Nordeste", "arquivo": "Bandeira_do_Piauí.svg"},
    {
        "uf": "RJ",
        "nome": "Rio de Janeiro",
        "regiao": "Sudeste",
        "arquivo": "Bandeira_do_estado_do_Rio_de_Janeiro.svg",
    },
    {
        "uf": "RN",
        "nome": "Rio Grande do Norte",
        "regiao": "Nordeste",
        "arquivo": "Bandeira_do_Rio_Grande_do_Norte.svg",
    },
    {
        "uf": "RS",
        "nome": "Rio Grande do Sul",
        "regiao": "Sul",
        "arquivo": "Bandeira_do_Rio_Grande_do_Sul.svg",
    },
    {"uf": "RO", "nome": "Rondônia", "regiao": "Norte", "arquivo": "Bandeira_de_Rondônia.svg"},
    {"uf": "RR", "nome": "Roraima", "regiao": "Norte", "arquivo": "Bandeira_de_Roraima.svg"},
    {
        "uf": "SC",
        "nome": "Santa Catarina",
        "regiao": "Sul",
        "arquivo": "Bandeira_de_Santa_Catarina.svg",
    },
    {
        "uf": "SP",
        "nome": "São Paulo",
        "regiao": "Sudeste",
        "arquivo": "Bandeira_do_estado_de_São_Paulo.svg",
    },
    {"uf": "SE", "nome": "Sergipe", "regiao": "Nordeste", "arquivo": "Bandeira_de_Sergipe.svg"},
    {"uf": "TO", "nome": "Tocantins", "regiao": "Norte", "arquivo": "Bandeira_do_Tocantins.svg"},
]

UA = "THDFM-Web/1.0 (bandeiras-uf; +https://github.com/mazeta1910/THDFM-Web)"


def url_commons(arquivo: str) -> str:
    # Special:FilePath redireciona para o binário atual.
    from urllib.parse import quote

    return f"https://commons.wikimedia.org/wiki/Special:FilePath/{quote(arquivo)}"


def baixar(uf: str, arquivo: str, dest: Path) -> None:
    req = urllib.request.Request(url_commons(arquivo), headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = resp.read()
    if len(data) < 200:
        raise RuntimeError(f"{uf}: arquivo muito pequeno ({len(data)} bytes)")
    # SVG costuma ter <?xml / <svg (às vezes com BOM UTF-8).
    raw = data[3:] if data.startswith(b"\xef\xbb\xbf") else data
    amostra = raw[:800].lower()
    if b"<svg" not in amostra and b"<!doctype svg" not in amostra:
        raise RuntimeError(f"{uf}: resposta não parece SVG ({raw[:40]!r})")
    dest.write_bytes(data)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ok: list[dict[str, str]] = []
    erros: list[str] = []
    for item in UFS:
        uf = item["uf"]
        dest = OUT_DIR / f"{uf}.svg"
        try:
            baixar(uf, item["arquivo"], dest)
            ok.append(
                {
                    "uf": uf,
                    "nome": item["nome"],
                    "regiao": item["regiao"],
                    "arquivo": f"{uf}.svg",
                    "fonte": item["arquivo"],
                }
            )
            print(f"OK  {uf} → {dest.name} ({dest.stat().st_size} bytes)")
        except Exception as exc:  # noqa: BLE001 — script one-shot
            erros.append(f"{uf}: {exc}")
            print(f"ERRO {uf}: {exc}")

    META_PATH.write_text(
        json.dumps(
            {
                "fonte": "Wikimedia Commons",
                "licenca_nota": (
                    "Bandeiras oficiais de UFs brasileiras; ver página de cada "
                    "arquivo no Commons para atribuição/licença."
                ),
                "ufs": ok,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"\nMeta: {META_PATH} ({len(ok)} UFs)")
    if erros:
        print("Falhas:")
        for e in erros:
            print(" -", e)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
