"""Catálogo de capabilities do painel admin (além de dono/moderador no .env)."""

from __future__ import annotations

# id → rótulo para a UI
CAPABILITIES: dict[str, str] = {
    "bolao.resultados": "Bolão — resultados e confrontos",
    "bolao.inscricoes": "Bolão — inscrições e participantes",
    "bolao.credenciais": "Bolão — redefinir username/senha",
    "listra.gestir": "Listra — gestão",
    "xonhometro.gestir": "Xonhômetro — gestão",
    "acervo.gestir": "Acervo — CRUD",
    "hall.gestir": "Hall das Lendas — gestão",
    "grid.bugs": "Grid — reports de bugs",
    "usuarios.permissoes": "Usuários — editar permissões de operadores",
    # Só o Dono (não entra no DEFAULT_MODERADOR). Guard no backend em /admin/sistema/*.
    "sistema.ver": "Sistema — rotas, access log, atividade, assets, saúde",
}

# O que um moderador ganha por padrão (sem linha no DB).
DEFAULT_MODERADOR: frozenset[str] = frozenset(
    {
        "bolao.resultados",
        "bolao.inscricoes",
        "listra.gestir",
        "xonhometro.gestir",
    }
)

# Antes viviam atrás de is_mazeta — agora são flags no painel.
PREVIEW_CAPS: frozenset[str] = frozenset(
    {
        "acervo.gestir",
        "hall.gestir",
        "grid.bugs",
    }
)


def capability_ids() -> list[str]:
    return list(CAPABILITIES.keys())
