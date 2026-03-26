# app/pagamentos.py
import os, hmac, hashlib
import mercadopago

MP_ACCESS_TOKEN = os.getenv("MP_ACCESS_TOKEN", "")
MP_WEBHOOK_SECRET = os.getenv("MP_WEBHOOK_SECRET", "")
APP_URL = os.getenv("APP_URL", "http://localhost:8000")

PLANOS = {
    "avulso": {"nome": "1 Carrossel", "valor": 19.90, "creditos": 1},
    "pack5":  {"nome": "Pack 5 Carrosséis", "valor": 79.90, "creditos": 5},
    "pack15": {"nome": "Pack 15 Carrosséis", "valor": 197.00, "creditos": 15},
}

PLANOS_TEMPLATE = {
    "starter": {"nome": "Template Exclusivo Starter", "valor": 127.00},
    "pro":     {"nome": "Template Exclusivo Pro",     "valor": 247.00},
    "agency":  {"nome": "Template Exclusivo Agency",  "valor": 497.00},
}

def criar_preferencia_mp(pagamento_id: int, plano_key: str) -> str:
    plano = PLANOS[plano_key]
    sdk = mercadopago.SDK(MP_ACCESS_TOKEN)
    pref = {
        "items": [{"title": plano["nome"], "quantity": 1, "unit_price": float(plano["valor"])}],
        "external_reference": str(pagamento_id),
        "back_urls": {
            "success": f"{APP_URL}/static/chat.html",
            "failure": f"{APP_URL}/static/planos.html",
        },
        "notification_url": f"{APP_URL}/webhook/mercadopago",
    }
    result = sdk.preference().create(pref)
    return result["response"]["init_point"]

def criar_preferencia_template(pedido_id: int, plano_key: str) -> str:
    """Cria preferência MP para compra de template exclusivo."""
    plano = PLANOS_TEMPLATE[plano_key]
    sdk = mercadopago.SDK(MP_ACCESS_TOKEN)
    pref = {
        "items": [{"title": plano["nome"], "quantity": 1, "unit_price": float(plano["valor"])}],
        "external_reference": f"tpl_{pedido_id}",
        "back_urls": {
            "success": f"{APP_URL}/static/briefing.html?pedido={pedido_id}",
            "failure": f"{APP_URL}/static/exclusivo.html?erro=1",
        },
        "notification_url": f"{APP_URL}/webhook/mercadopago",
    }
    result = sdk.preference().create(pref)
    return result["response"]["init_point"]

def validar_assinatura_webhook(x_signature: str, corpo: bytes, secret: str) -> bool:
    esperado = hmac.new(secret.encode(), corpo, hashlib.sha256).hexdigest()
    return hmac.compare_digest(esperado, x_signature)
