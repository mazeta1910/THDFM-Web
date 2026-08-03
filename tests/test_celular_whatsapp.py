"""Normalização de celular e links do WhatsApp."""

import pytest

from src import db


@pytest.mark.parametrize(
    "entrada,esperado",
    [
        ("11999887766", "5511999887766"),
        ("(11) 99988-7766", "5511999887766"),
        ("+55 11 99988-7766", "5511999887766"),
        ("5511999887766", "5511999887766"),
        ("011999887766", "5511999887766"),  # zero de tronco
        ("021988887777", "5521988887777"),
        ("05511999887766", "5511999887766"),
        ("555511999887766", "5511999887766"),  # 55 duplicado
        ("005511999887766", "5511999887766"),
        ("1198887766", "5511998887766"),  # sem 9º dígito → insere
        ("551198887766", "5511998887766"),  # 55 + sem 9º
        ("55119998887766", "5511998887766"),  # 9 duplicado
        ("1133334444", "551133334444"),  # fixo, não insere 9
    ],
)
def test_normalizar_celular_formatos_br(entrada, esperado):
    assert db.normalizar_celular(entrada) == esperado
    assert db.celular_whatsapp(entrada) == esperado


def test_diagnostico_celular_whatsapp():
    ok = db.diagnostico_celular_whatsapp("1198887766")
    assert ok["ok"] is True
    assert ok["digits"] == "5511998887766"
    bad = db.diagnostico_celular_whatsapp("")
    assert bad["ok"] is False
    assert bad["motivo"] == "sem_celular"


def test_celular_whatsapp_invalido_nao_manda_lixo():
    assert db.celular_whatsapp("123") is None
    assert db.celular_whatsapp("") is None
    assert db.celular_whatsapp(None) is None


def test_url_whatsapp_usa_api_send_phone():
    url = db.url_whatsapp_chat("011999887766", "Oi, teste!")
    assert url is not None
    assert url.startswith("https://api.whatsapp.com/send?phone=5511999887766")
    assert "text=" in url
    assert "Oi" in url or "Oi%2C" in url or "Oi," in url
