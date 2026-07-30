"""Vínculo estável admin ↔ participante (não cria duplicata ao renomear)."""

from __future__ import annotations

import os
from pathlib import Path

import src.db as db
from src.config import ROOT_DIR


def _use_tmp_db(tmp_path: Path):
    db.DB_PATH = tmp_path / "test.db"
    (tmp_path / "avatars").mkdir(exist_ok=True)
    db.init_db()


def test_renomear_admin_nao_cria_duplicata(tmp_path, monkeypatch):
    monkeypatch.chdir(ROOT_DIR)
    _use_tmp_db(tmp_path)

    part = db.garantir_participante_admin("mazeta", "Mazeta")
    assert part["nome"] == "Mazeta"
    assert part["admin_login"] == "mazeta"
    pid = part["id"]
    token = part["token"]

    db.atualizar_nome_participante(pid, "Mazetinha")

    de_novo = db.garantir_participante_admin(
        "mazeta", "Mazeta", token_preferido=token
    )
    assert de_novo["id"] == pid
    assert de_novo["nome"] == "Mazetinha"
    assert de_novo["admin_login"] == "mazeta"

    liberados = [p for p in db.list_participantes() if p["status"] == "liberado"]
    assert len(liberados) == 1


def test_garantir_por_login_apos_rename_sem_token(tmp_path, monkeypatch):
    monkeypatch.chdir(ROOT_DIR)
    _use_tmp_db(tmp_path)

    part = db.garantir_participante_admin("mazeta", "Mazeta")
    db.atualizar_nome_participante(part["id"], "Mazetinha")
    # Sem token, ainda acha pelo admin_login
    de_novo = db.garantir_participante_admin("mazeta", "Mazeta")
    assert de_novo["id"] == part["id"]
    assert de_novo["nome"] == "Mazetinha"
    assert len(db.list_participantes()) == 1
