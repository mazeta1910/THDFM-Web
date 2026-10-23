"""Importação de .txt para a Listra THDFM.

Lê um texto em blocos (nome do meliante seguido das frases dele) e ajuda a
classificar cada linha como ``frase``, ``nome`` (meliante) ou ``fora``. A
classificação final é sempre do usuário na tela de revisão — aqui só damos um
palpite para reduzir cliques.

As funções são puras (não tocam no banco) para facilitar os testes.
"""

from __future__ import annotations

from typing import Any, Iterable

TIPOS = ("frase", "nome", "fora")


def parse_linhas(texto: str) -> list[dict[str, Any]]:
    """Quebra o texto em linhas não vazias, preservando a ordem.

    Cada item traz ``texto`` (já sem espaços nas pontas) e ``inicio_bloco``
    (True quando a linha vem logo após uma linha em branco ou é a primeira),
    sinal usado pelo palpite de classificação.
    """
    out: list[dict[str, Any]] = []
    anterior_vazia = True  # a primeira linha de conteúdo começa um bloco
    for bruta in (texto or "").splitlines():
        limpa = bruta.strip()
        if not limpa:
            anterior_vazia = True
            continue
        out.append({"texto": limpa, "inicio_bloco": anterior_vazia})
        anterior_vazia = False
    return out


def classificar(
    linhas: list[dict[str, Any]], meliantes_conhecidos: Iterable[str] = ()
) -> list[dict[str, Any]]:
    """Adiciona um palpite de ``tipo`` (``frase``/``nome``) a cada linha.

    Palpite conservador: ``nome`` só quando a linha bate com um meliante já
    conhecido ou quando começa um bloco (primeira linha, ou logo após uma
    linha em branco). As demais ficam como ``frase`` — no acervo há muito mais
    frases que nomes, então errar para o lado de ``frase`` dá menos correções.
    """
    conhecidos = {str(n).strip().casefold() for n in meliantes_conhecidos if str(n).strip()}
    out: list[dict[str, Any]] = []
    for item in linhas:
        texto = item["texto"]
        if texto.casefold() in conhecidos or item.get("inicio_bloco"):
            tipo = "nome"
        else:
            tipo = "frase"
        out.append({"texto": texto, "tipo": tipo})
    return out


def resolver_importacao(
    itens_revisados: list[dict[str, Any]], meliante_padrao: str = ""
) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    """Resolve a cadeia de atribuição a partir das linhas já revisadas.

    Caminha na ordem: uma linha ``nome`` passa a valer como meliante das
    ``frase`` seguintes até o próximo ``nome``; frases antes do primeiro nome
    usam ``meliante_padrao``.

    Devolve ``(frases, avisos)`` onde ``frases`` é a lista pronta para criar
    (``texto`` + ``responsavel``) e ``avisos`` lista as frases incluídas que
    ficaram sem meliante (não entram).
    """
    atual = (meliante_padrao or "").strip()
    frases: list[dict[str, str]] = []
    avisos: list[dict[str, Any]] = []
    for pos, item in enumerate(itens_revisados):
        tipo = item.get("tipo")
        texto = (item.get("texto") or "").strip()
        if tipo == "nome":
            if texto:
                atual = texto
            continue
        if tipo == "fora" or not texto:
            continue
        # tipo == "frase": override explícito por linha vence a cadeia.
        override = (item.get("responsavel") or "").strip()
        responsavel = override or atual
        if not responsavel:
            avisos.append({"posicao": pos, "texto": texto})
            continue
        frases.append({"texto": texto, "responsavel": responsavel})
    return frases, avisos
