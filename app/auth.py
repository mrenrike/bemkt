import os
from datetime import datetime, timedelta, timezone
from passlib.context import CryptContext
from jose import jwt, JWTError
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

_raw_secret = os.getenv("JWT_SECRET", "")
if not _raw_secret or _raw_secret == "dev-secret-change-in-production":
    import secrets as _secrets
    _raw_secret = _secrets.token_hex(32)
    import logging as _log
    _log.getLogger(__name__).warning(
        "JWT_SECRET não definido — usando chave aleatória (sessões serão perdidas ao reiniciar)"
    )
JWT_SECRET = _raw_secret
ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 24

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer = HTTPBearer()

def hash_senha(senha: str) -> str:
    return pwd_context.hash(senha)

def verificar_senha(senha: str, hash: str) -> bool:
    return pwd_context.verify(senha, hash)

def criar_token(data: dict) -> str:
    payload = data.copy()
    payload["exp"] = datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRE_HOURS)
    return jwt.encode(payload, JWT_SECRET, algorithm=ALGORITHM)

def verificar_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
    except JWTError:
        return None

def usuario_atual(credentials: HTTPAuthorizationCredentials = Depends(bearer)) -> int:
    payload = verificar_token(credentials.credentials)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")
    try:
        return int(sub)
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")

def admin_atual(credentials: HTTPAuthorizationCredentials = Depends(bearer)) -> int:
    from app.database import get_db
    user_id = usuario_atual(credentials)
    db = get_db()
    row = db.execute("SELECT is_admin FROM users WHERE id=?", (user_id,)).fetchone()
    db.close()
    if not row or not row["is_admin"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso negado")
    return user_id
