# app/security.py — Rate limiting + Security headers middleware
import time
import re
from collections import defaultdict
from threading import Lock
from fastapi import Request, HTTPException
from fastapi.responses import Response
from starlette.middleware.base import BaseHTTPMiddleware

# ── In-memory rate limiter ────────────────────────────────────────
# Estrutura: {chave: [(timestamp, ...), ...]}
_buckets: dict[str, list[float]] = defaultdict(list)
_lock = Lock()

def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"

def check_rate_limit(key: str, max_requests: int, window_seconds: int):
    """Lança HTTPException 429 se o limite foi atingido."""
    now = time.monotonic()
    with _lock:
        ts = _buckets[key]
        # Remove entradas fora da janela
        cutoff = now - window_seconds
        _buckets[key] = [t for t in ts if t > cutoff]
        if len(_buckets[key]) >= max_requests:
            raise HTTPException(
                status_code=429,
                detail="Muitas requisições. Aguarde e tente novamente."
            )
        _buckets[key].append(now)

def rate_limit(request: Request, max_requests: int, window_seconds: int, scope: str = ""):
    """Helper para usar diretamente em endpoints."""
    ip = _client_ip(request)
    key = f"{scope}:{ip}"
    check_rate_limit(key, max_requests, window_seconds)

# ── Security headers middleware ───────────────────────────────────
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "geolocation=(), microphone=(), camera=(), payment=()"
        )
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' cdn.jsdelivr.net fonts.googleapis.com; "
            "style-src 'self' 'unsafe-inline' fonts.googleapis.com cdn.jsdelivr.net; "
            "font-src 'self' fonts.gstatic.com; "
            "img-src 'self' data: blob:; "
            "connect-src 'self'; "
            "frame-ancestors 'none';"
        )
        # Remove headers que revelam stack
        for h in ("server", "x-powered-by"):
            try:
                del response.headers[h]
            except KeyError:
                pass
        return response

# ── Input validation helpers ──────────────────────────────────────
_EMAIL_RE = re.compile(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$')

def validar_email(email: str) -> str:
    email = email.strip().lower()
    if len(email) > 254:
        raise HTTPException(status_code=422, detail="Email inválido")
    if not _EMAIL_RE.match(email):
        raise HTTPException(status_code=422, detail="Email inválido")
    # Previne CRLF injection em headers de email
    if any(c in email for c in ['\r', '\n', '\0']):
        raise HTTPException(status_code=422, detail="Email inválido")
    return email

def sanitizar_texto(texto: str, max_len: int = 2000) -> str:
    """Remove caracteres de controle e limita tamanho."""
    texto = texto.strip()
    # Remove null bytes e outros caracteres de controle perigosos
    texto = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', texto)
    return texto[:max_len]

# ── Magic bytes para validar uploads de imagem ────────────────────
_MAGIC = {
    b'\x89PNG': 'image/png',
    b'\xff\xd8\xff': 'image/jpeg',
    b'GIF8': 'image/gif',
    b'<svg': 'image/svg+xml',
    b'<?xm': 'image/svg+xml',  # <?xml ... <svg
}

def validar_magic_bytes(conteudo: bytes, nome_arquivo: str) -> bool:
    """Verifica se o conteúdo bate com uma imagem real."""
    ext = nome_arquivo.rsplit('.', 1)[-1].lower() if '.' in nome_arquivo else ''
    if ext == 'svg':
        # SVG é XML: verifica se tem tag <svg ou <?xml
        head = conteudo[:512].lower()
        return b'<svg' in head or b'<?xml' in head
    for magic, mime in _MAGIC.items():
        if conteudo[:len(magic)] == magic and mime != 'image/svg+xml':
            return True
    return False
