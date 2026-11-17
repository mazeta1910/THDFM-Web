"""Admin › Inscrições: avatar grava no disco + DB e aparece após reload."""

from __future__ import annotations

import io
from pathlib import Path

from src import db
from src.config import ROOT_DIR
from tests.conftest import login_admin

# JPEG 1x1 mínimo
_JPEG = bytes.fromhex(
    "ffd8ffe000104a46494600010100000100010000ffdb004300080606070605080707"
    "070909080a0c140d0c0b0b0c1912130f141d1a1f1e1d1a1c1c20242e2720222c231c"
    "1c2837292c30313434341f27393d38323c2e333432ffdb0043010909090c0b0c180d"
    "0d1832211c2132323232323232323232323232323232323232323232323232323232"
    "323232323232323232323232323232323232323232ffc00011080001000103011100"
    "021100031101ffc40014000100000000000000000000000000000000ffc400141001"
    "00000000000000000000000000000000ffda000c0301000210031000003f00bf80ffd9"
)


def test_admin_atualizar_persiste_avatar(client, tmp_path, monkeypatch):
    av_dir = tmp_path / "avatars-persist"
    av_dir.mkdir()
    monkeypatch.setattr("src.config.AVATARES_DIR", av_dir)
    monkeypatch.setattr("src.app.AVATARES_DIR", av_dir)

    login_admin(client)
    part = db.criar_participante("Avatar Persist", status="liberado")

    files = {"avatar": ("avatar.jpg", io.BytesIO(_JPEG), "image/jpeg")}
    data = {
        "participante_id": str(part["id"]),
        "nome": "Avatar Persist",
        "celular": "",
        "remover_avatar": "",
    }
    r = client.post(
        "/admin/participante/atualizar",
        data=data,
        files=files,
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "Participante+atualizado" in (r.headers.get("location") or "")

    updated = db.get_participante(part["id"])
    assert updated is not None
    rel = (updated.get("avatar_path") or "").strip()
    assert rel.endswith(".jpg")
    assert (av_dir / rel).is_file()
    assert (av_dir / rel).stat().st_size > 0

    from src.app import avatar_url

    url = avatar_url(rel)
    assert url and url.startswith(f"/avatars/{rel}")
    assert "?v=" in url

    page = client.get("/admin?sec=inscricoes")
    assert page.status_code == 200
    assert f"/avatars/{rel}" in page.text


def test_admin_inscricoes_bind_autosubmit_avatar(client):
    """Contrato: crop dos cards de participante dispara submit do form."""
    login_admin(client)
    db.criar_participante("Bind Auto", status="liberado")
    page = client.get("/admin?sec=inscricoes")
    assert page.status_code == 200
    assert "autoSubmitForm: card || null" in page.text
    assert "autoSubmitForm: form" in page.text  # foto padrão também
