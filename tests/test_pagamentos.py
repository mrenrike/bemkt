# tests/test_pagamentos.py
import hmac, hashlib
from app.pagamentos import validar_assinatura_webhook

def test_assinatura_valida():
    secret = "meu-segredo"
    corpo = b'{"id":123}'
    sig = hmac.new(secret.encode(), corpo, hashlib.sha256).hexdigest()
    assert validar_assinatura_webhook(sig, corpo, secret)

def test_assinatura_invalida():
    assert not validar_assinatura_webhook("errada", b'{"id":1}', "segredo")
