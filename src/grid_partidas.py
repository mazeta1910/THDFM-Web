"""Ciclo de vida das partidas do Grid (Raiz / Xonha) — lógica de serviço."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from src import db
from src.grid_score import pontos_partida

TZ_SP = ZoneInfo("America/Sao_Paulo")


def agora_iso() -> str:
    return datetime.now(TZ_SP).replace(microsecond=0).isoformat()


def tempo_decorrido_s(iniciado_em: str | None, *, ate: str | None = None) -> int | None:
    if not iniciado_em:
        return None
    try:
        ini = datetime.fromisoformat(str(iniciado_em))
    except ValueError:
        return None
    if ini.tzinfo is None:
        ini = ini.replace(tzinfo=TZ_SP)
    if ate:
        try:
            fim = datetime.fromisoformat(str(ate))
        except ValueError:
            fim = datetime.now(TZ_SP)
    else:
        fim = datetime.now(TZ_SP)
    if fim.tzinfo is None:
        fim = fim.replace(tzinfo=TZ_SP)
    return max(0, int((fim - ini).total_seconds()))


def _recalcular_pontos(partida: dict[str, Any]) -> int:
    return pontos_partida(
        partida.get("celulas"),
        finalizado=bool(partida.get("finalizado")),
        interrompido=bool(partida.get("interrompido")),
        tempo_segundos=partida.get("tempo_segundos"),
        dicas=partida.get("dicas") or [],
    )


def iniciar_raiz(participante_id: int, dia: str) -> dict[str, Any]:
    """Idempotente: devolve a partida Raiz do dia ou cria uma nova.

    O cronômetro (iniciado_em) só arranca no 1º clique numa célula.
    """
    existing = db.get_grid_partida_raiz(participante_id, dia)
    if existing:
        return existing
    return db.criar_grid_partida(
        participante_id,
        dia,
        modo="raiz",
        puzzle_salt="",
        iniciado_em=None,
    )


def garantir_inicio_partida(
    partida_id: int, *, participante_id: int
) -> dict[str, Any]:
    """Marca iniciado_em na 1ª interação com uma célula (idempotente)."""
    part = db.get_grid_partida(partida_id)
    if not part or int(part["participante_id"]) != int(participante_id):
        raise LookupError("partida não encontrada")
    if part.get("finalizado") or part.get("interrompido"):
        return part
    if part.get("iniciado_em"):
        return part
    return db.atualizar_grid_partida(partida_id, iniciado_em=agora_iso())


def interromper_partida(partida_id: int, *, participante_id: int) -> dict[str, Any]:
    part = db.get_grid_partida(partida_id)
    if not part or int(part["participante_id"]) != int(participante_id):
        raise LookupError("partida não encontrada")
    if part["modo"] != "raiz":
        raise ValueError("só o modo Raiz interrompe ao sair")
    if part.get("finalizado") or part.get("interrompido"):
        return part
    now = agora_iso()
    tempo = tempo_decorrido_s(part.get("iniciado_em"), ate=now)
    part = db.atualizar_grid_partida(
        partida_id,
        interrompido=True,
        encerrado_em=now,
        tempo_segundos=tempo,
    )
    pts = _recalcular_pontos(part)
    part = db.atualizar_grid_partida(partida_id, pontos=pts)
    # Espelha no progresso legado (ranking antigo) até a Fase 6.
    db.salvar_grid_progresso(
        participante_id,
        part["dia"],
        part.get("celulas") or [],
        finalizado=False,
    )
    return part


def aplicar_chute_partida(
    partida_id: int,
    *,
    participante_id: int,
    linha: int,
    coluna: int,
    resultado: dict[str, Any],
) -> dict[str, Any]:
    """Grava chute numa partida; levanta ValueError/LookupError/PermissionError."""
    from src.grid_game import celulas_completas, parse_celulas_progresso

    part = db.get_grid_partida(partida_id)
    if not part or int(part["participante_id"]) != int(participante_id):
        raise LookupError("partida não encontrada")
    if part.get("interrompido"):
        raise PermissionError("tentativa encerrada — células vazias bloqueadas")
    if part.get("finalizado"):
        raise PermissionError("partida já finalizada")

    if not part.get("iniciado_em"):
        part = garantir_inicio_partida(partida_id, participante_id=participante_id)

    celulas = parse_celulas_progresso(part.get("celulas"))
    if celulas[linha][coluna] is not None:
        raise ValueError("Célula já jogada")

    celulas[linha][coluna] = {
        "ok": resultado["ok"],
        "clube": resultado["clube"],
    }
    finalizado = celulas_completas(celulas)
    now = agora_iso()
    encerrado = now if finalizado else None
    tempo = tempo_decorrido_s(part.get("iniciado_em"), ate=now) if finalizado else None
    part = db.atualizar_grid_partida(
        partida_id,
        celulas=celulas,
        finalizado=finalizado,
        encerrado_em=encerrado,
        tempo_segundos=tempo if finalizado else part.get("tempo_segundos"),
    )
    pts = _recalcular_pontos(part)
    part = db.atualizar_grid_partida(partida_id, pontos=pts)
    if part["modo"] == "raiz":
        db.salvar_grid_progresso(
            participante_id,
            part["dia"],
            celulas,
            finalizado=finalizado,
        )
    return part


XONHA_LIVRE_POR_DIA = 3
MATRIZ_TAMANHO = 20
MATRIZ_VALIDOS = 2  # ~1 válido a cada 10 → 2 em 20


class CotaXonhaEsgotada(Exception):
    """Sem cota livre e sem passe Xonha."""


def pode_iniciar_xonha(participante_id: int, dia: str) -> tuple[bool, dict[str, Any]]:
    usados = db.contar_grid_partidas_dia(
        participante_id, dia, modo="xonha", so_encerradas=True
    )
    passe = db.grid_xonha_passe_ativo(participante_id, hoje=dia)
    info = {
        "usados": usados,
        "limite_livre": XONHA_LIVRE_POR_DIA,
        "passe_ativo": passe,
        "restantes": None if passe else max(0, XONHA_LIVRE_POR_DIA - usados),
    }
    ok = passe or usados < XONHA_LIVRE_POR_DIA
    return ok, info


def salt_xonha_indice(indice: int) -> str:
    return f"xonha-{max(1, int(indice))}"


def indice_proximo_xonha(participante_id: int, dia: str) -> int:
    return (
        db.contar_grid_partidas_dia(int(participante_id), str(dia), modo="xonha") + 1
    )


def _puzzle_xonha_publico(dia: str, salt: str) -> dict[str, Any]:
    from src.grid_game import (
        gerar_puzzle,
        get_virada_hm,
        ms_ate_proxima_virada,
        rotulo_dia,
        rotulo_hora_virada,
    )

    p = gerar_puzzle(dia, salt=str(salt))
    h, mi = get_virada_hm()
    return {
        **p,
        "rotulo": rotulo_dia(dia),
        "virada_em_ms": ms_ate_proxima_virada(),
        "virada_hora": h,
        "virada_minuto": mi,
        "virada_rotulo": rotulo_hora_virada(h, mi),
        "tz": "America/Sao_Paulo",
        "regenerado": True,
        "modo": "xonha",
    }


def salt_convidado_continuo() -> str:
    return salt_xonha_indice(1)


def puzzle_ssr_convidado(dia: str) -> dict[str, Any]:
    return _puzzle_xonha_publico(str(dia), salt_convidado_continuo())


def validar_chute_convidado(
    *,
    dia: str,
    linha: int,
    coluna: int,
    clube_id: str | None = None,
    nome: str | None = None,
) -> dict[str, Any]:
    from src.grid_game import (
        chute_nome_inexistente,
        resolver_clube_por_nome,
        validar_chute,
    )

    salt = salt_convidado_continuo()
    resultado = None
    cid = str(clube_id or "").strip()
    rotulo = str(nome or "").strip()
    if not cid and rotulo:
        try:
            cid = str(resolver_clube_por_nome(rotulo)["id"])
        except ValueError as exc:
            msg = str(exc)
            if "não encontrado" in msg.casefold():
                resultado = chute_nome_inexistente(
                    linha=linha, coluna=coluna, nome=rotulo
                )
            else:
                raise
    if resultado is None:
        if not cid:
            raise ValueError("Digite o nome do clube")
        resultado = validar_chute(
            dia=dia,
            linha=linha,
            coluna=coluna,
            clube_id=cid,
            salt=salt,
        )
    return resultado


def puzzle_ssr_continuo(
    participante_id: int, dia: str
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    aberta = db.get_grid_partida_aberta(int(participante_id), str(dia), modo="xonha")
    if aberta:
        part = anexar_indice_dia(aberta)
        return puzzle_da_partida(part), part
    indice = indice_proximo_xonha(participante_id, dia)
    salt = salt_xonha_indice(indice)
    return _puzzle_xonha_publico(dia, salt), None


def iniciar_xonha(participante_id: int, dia: str) -> dict[str, Any]:
    from src.grid_game import gerar_puzzle

    aberta = db.get_grid_partida_aberta(participante_id, dia, modo="xonha")
    if aberta:
        return aberta

    ok, _info = pode_iniciar_xonha(participante_id, dia)
    if not ok:
        raise CotaXonhaEsgotada(
            "Limite de 3 grids Contínuo por dia. Passe ilimitado: R$ 1,65 / 30 dias."
        )
    indice = indice_proximo_xonha(participante_id, dia)
    salt = salt_xonha_indice(indice)
    gerar_puzzle(dia, salt=salt)
    return db.criar_grid_partida(
        participante_id,
        dia,
        modo="xonha",
        puzzle_salt=salt,
        iniciado_em=None,
    )


def puzzle_da_partida(partida: dict[str, Any]) -> dict[str, Any]:
    from src.grid_game import puzzle_publico

    dia = partida["dia"]
    if partida.get("modo") == "xonha" and partida.get("puzzle_salt"):
        return _puzzle_xonha_publico(dia, str(partida["puzzle_salt"]))
    return {**puzzle_publico(dia), "modo": "raiz"}


def salt_da_partida(partida: dict[str, Any]) -> str | None:
    if partida.get("modo") == "xonha":
        return str(partida.get("puzzle_salt") or "") or None
    return None


def anexar_indice_dia(partida: dict[str, Any]) -> dict[str, Any]:
    """Inclui indice_dia (1-based) para rótulo do share Contínuo 1/2/3."""
    if not partida or partida.get("id") is None:
        return partida
    out = dict(partida)
    out["indice_dia"] = db.indice_grid_partida_dia(
        int(partida["participante_id"]),
        str(partida["dia"]),
        modo=str(partida.get("modo") or "raiz"),
        partida_id=int(partida["id"]),
    )
    return out


def modo_rotulo_partida(partida: dict[str, Any]) -> str:
    modo = str(partida.get("modo") or "")
    if modo == "raiz":
        return "Pro"
    if modo == "xonha":
        indice = partida.get("indice_dia")
        if indice is None and partida.get("id") is not None:
            part = anexar_indice_dia(partida)
            indice = part.get("indice_dia")
        if indice is not None and int(indice) > 0:
            return f"Contínuo {int(indice)}"
        return "Contínuo"
    return modo or "—"


def detalhe_partida_dono(partida: dict[str, Any]) -> dict[str, Any]:
    part = anexar_indice_dia(partida)
    part["modo_rotulo"] = modo_rotulo_partida(part)
    celulas = part.get("celulas") or []
    ok = 0
    filled = 0
    if isinstance(celulas, list):
        for row in celulas:
            if not isinstance(row, list):
                continue
            for cell in row:
                if isinstance(cell, dict) and cell.get("clube"):
                    filled += 1
                    if cell.get("ok"):
                        ok += 1
    part["celulas_ok"] = ok
    part["celulas_preenchidas"] = filled
    if part.get("interrompido"):
        part["status"] = "interrompido"
    elif part.get("finalizado"):
        part["status"] = "finalizado"
    else:
        part["status"] = "em andamento"
    puzzle = puzzle_da_partida(part)
    share = None
    if part.get("finalizado") or part.get("interrompido"):
        share = texto_share_partida(part)
    return {"partida": part, "puzzle": puzzle, "share": share}


def texto_share_partida(
    partida: dict[str, Any],
    *,
    celulas: list | None = None,
    pontos: int | None = None,
    ranking: int | None = None,
) -> str:
    """Monta texto de share WhatsApp a partir de uma partida (Pro / 1 / 2 / 3)."""
    from src.grid_game import parse_celulas_progresso, texto_share

    part = anexar_indice_dia(partida)
    cells = celulas if celulas is not None else parse_celulas_progresso(part.get("celulas"))
    modo = str(part.get("modo") or "")
    indice = int(part["indice_dia"]) if modo == "xonha" else None
    pts = pontos if pontos is not None else int(part.get("pontos") or 0)
    dicas = part.get("dicas") or []
    pos = ranking
    if pos is None and part.get("participante_id") is not None and modo in ("raiz", "xonha"):
        pos = db.posicao_ranking_grid_modo(int(part["participante_id"]), modo)
    tempo = part.get("tempo_segundos")
    if tempo is None and part.get("iniciado_em"):
        tempo = tempo_decorrido_s(part.get("iniciado_em"), ate=part.get("encerrado_em"))
    return texto_share(
        dia=str(part.get("dia") or ""),
        celulas=cells,
        modo=modo,
        indice=indice,
        pontos=pts,
        dicas_usadas=len(dicas) if isinstance(dicas, list) else 0,
        ranking=pos,
        tempo_segundos=int(tempo) if tempo is not None else None,
    )


def _celula_key(linha: int, coluna: int) -> str:
    return f"{int(linha)},{int(coluna)}"


def aplicar_dica_contagem(
    partida_id: int,
    *,
    participante_id: int,
    linha: int,
    coluna: int,
) -> dict[str, Any]:
    """Revela densidade da célula (−10). 1× por célula."""
    from src.grid_game import GRID_SIZE
    from src.grid_score import custo_dica_contagem

    part = db.get_grid_partida(partida_id)
    if not part or int(part["participante_id"]) != int(participante_id):
        raise LookupError("partida não encontrada")
    if part.get("modo") != "xonha":
        raise ValueError("dicas só no modo Xonha")
    if part.get("finalizado") or part.get("interrompido"):
        raise PermissionError("partida encerrada")
    if not (0 <= linha < GRID_SIZE and 0 <= coluna < GRID_SIZE):
        raise ValueError("célula inválida")

    dicas = list(part.get("dicas") or [])
    key = _celula_key(linha, coluna)
    if any(d.get("tipo") == "contagem" and d.get("celula") == key for d in dicas):
        raise ValueError("contagem já revelada nesta célula")

    puzzle = puzzle_da_partida(part)
    try:
        dens = int(puzzle["densidades"][linha][coluna])
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise ValueError("densidade indisponível") from exc

    custo = custo_dica_contagem()
    dicas.append(
        {
            "tipo": "contagem",
            "celula": key,
            "linha": linha,
            "coluna": coluna,
            "custo": custo,
            "payload": {"densidade": dens},
        }
    )
    part = db.atualizar_grid_partida(partida_id, dicas=dicas)
    pts = _recalcular_pontos(part)
    part = db.atualizar_grid_partida(partida_id, pontos=pts)
    return {
        "partida": part,
        "dica": dicas[-1],
        "score_parcial": pts,
    }


def aplicar_dica_matriz(
    partida_id: int,
    *,
    participante_id: int,
    linha: int,
    coluna: int,
) -> dict[str, Any]:
    """Matriz 20 clubes (2 válidos + 18 inválidos); custo linear ilimitado."""
    import random

    from src.grid_game import (
        GRID_SIZE,
        categoria_por_id,
        clubes_grid,
        clubes_por_id,
        pool_celula,
    )
    from src.grid_score import custo_dica_matriz

    part = db.get_grid_partida(partida_id)
    if not part or int(part["participante_id"]) != int(participante_id):
        raise LookupError("partida não encontrada")
    if part.get("modo") != "xonha":
        raise ValueError("dicas só no modo Xonha")
    if part.get("finalizado") or part.get("interrompido"):
        raise PermissionError("partida encerrada")
    if not (0 <= linha < GRID_SIZE and 0 <= coluna < GRID_SIZE):
        raise ValueError("célula inválida")

    puzzle = puzzle_da_partida(part)
    row = categoria_por_id(puzzle["linhas"][linha]["id"], part["dia"])
    col = categoria_por_id(puzzle["colunas"][coluna]["id"], part["dia"])
    if not row or not col:
        raise ValueError("categoria inválida")
    validos = pool_celula(row, col)
    if len(validos) < MATRIZ_VALIDOS:
        raise ValueError("pool insuficiente para matriz")

    ids_validos = {str(c["id"]) for c in validos}
    invalidos = [c for c in clubes_grid() if str(c["id"]) not in ids_validos]
    if len(invalidos) < MATRIZ_TAMANHO - MATRIZ_VALIDOS:
        raise ValueError("catálogo insuficiente para matriz")

    dicas = list(part.get("dicas") or [])
    usos_matriz = sum(1 for d in dicas if d.get("tipo") == "matriz")
    custo = custo_dica_matriz(usos_matriz)

    rng = random.Random(
        f"{part.get('puzzle_salt')}|{partida_id}|{linha}|{coluna}|{usos_matriz}"
    )
    escolhidos_v = rng.sample(validos, MATRIZ_VALIDOS)
    escolhidos_i = rng.sample(invalidos, MATRIZ_TAMANHO - MATRIZ_VALIDOS)
    misturados = escolhidos_v + escolhidos_i
    rng.shuffle(misturados)

    def _pub(c: dict[str, Any]) -> dict[str, Any]:
        full = clubes_por_id().get(str(c["id"])) or c
        return {
            "id": str(full.get("id") or c["id"]),
            "nome": full.get("nome") or c.get("nome") or "?",
            "emblema": full.get("emblema") or c.get("emblema") or "",
            "uf": full.get("uf") or c.get("uf") or "",
        }

    itens = [_pub(c) for c in misturados]
    key = _celula_key(linha, coluna)
    dicas.append(
        {
            "tipo": "matriz",
            "celula": key,
            "linha": linha,
            "coluna": coluna,
            "custo": custo,
            "indice_uso": usos_matriz,
            "payload": {"clubes": itens},
        }
    )
    part = db.atualizar_grid_partida(partida_id, dicas=dicas)
    pts = _recalcular_pontos(part)
    part = db.atualizar_grid_partida(partida_id, pontos=pts)
    return {
        "partida": part,
        "dica": dicas[-1],
        "score_parcial": pts,
        "proximo_custo_matriz": custo_dica_matriz(usos_matriz + 1),
    }


def override_celula_admin(
    partida_id: int,
    *,
    linha: int,
    coluna: int,
    ok: bool,
) -> dict[str, Any]:
    from src.grid_game import GRID_SIZE, parse_celulas_progresso

    part = db.get_grid_partida(int(partida_id))
    if not part:
        raise LookupError("partida não encontrada")
    if not (0 <= int(linha) < GRID_SIZE and 0 <= int(coluna) < GRID_SIZE):
        raise ValueError("célula inválida")
    celulas = parse_celulas_progresso(part.get("celulas"))
    cell = celulas[int(linha)][int(coluna)]
    if not cell or not cell.get("clube"):
        raise ValueError("célula vazia")
    cell = dict(cell)
    cell["ok"] = bool(ok)
    celulas[int(linha)][int(coluna)] = cell
    part = db.atualizar_grid_partida(int(partida_id), celulas=celulas)
    pts = _recalcular_pontos(part)
    part = db.atualizar_grid_partida(int(partida_id), pontos=pts)
    if part.get("modo") == "raiz":
        db.salvar_grid_progresso(
            int(part["participante_id"]),
            str(part["dia"]),
            celulas,
            finalizado=bool(part.get("finalizado")),
        )
    return part


def justificativa_celula(
    *,
    dia: str,
    salt: str | None,
    linha: int,
    coluna: int,
    clube_id: str,
) -> dict[str, Any]:
    from src.grid_game import (
        GRID_SIZE,
        categoria_por_id,
        clube_bate_categoria,
        clubes_por_id,
        gerar_puzzle,
    )

    if not (0 <= int(linha) < GRID_SIZE and 0 <= int(coluna) < GRID_SIZE):
        raise ValueError("célula inválida")
    puzzle = (
        gerar_puzzle(dia, salt=salt) if salt is not None else gerar_puzzle(dia)
    )
    row = categoria_por_id(puzzle["linhas"][int(linha)]["id"], dia)
    col = categoria_por_id(puzzle["colunas"][int(coluna)]["id"], dia)
    clube = clubes_por_id().get(str(clube_id))
    if not row or not col:
        raise ValueError("categoria inválida")
    if not clube:
        raise ValueError("clube inválido")
    ok_linha = clube_bate_categoria(clube, row)
    ok_coluna = clube_bate_categoria(clube, col)
    if ok_linha and ok_coluna:
        motivo = "bate nas duas categorias"
    elif not ok_linha and not ok_coluna:
        motivo = "falha na linha e na coluna"
    elif not ok_linha:
        motivo = "falha na linha"
    else:
        motivo = "falha na coluna"
    return {
        "ok_linha": ok_linha,
        "ok_coluna": ok_coluna,
        "ok": ok_linha and ok_coluna,
        "motivo": motivo,
        "linha": row.to_public(),
        "coluna": col.to_public(),
        "clube": {
            "id": clube["id"],
            "nome": clube["nome"],
            "uf": clube.get("uf") or "",
            "emblema": clube.get("emblema") or "",
            "rep": int(clube.get("rep") or 0),
        },
        "coord": f"{chr(65 + int(linha))}{int(coluna) + 1}",
    }
